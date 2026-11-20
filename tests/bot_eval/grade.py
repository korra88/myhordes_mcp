"""Deterministic grader of bot-eval run files: checks D1-D13 of docs/bot-eval-plan.md section 4.1.
No model call, no network. The LLM judge (J1-J6, the 4.3 score) is tests/bot_eval/judge.py; its verdicts are merged into the same graded file.

    .venv/bin/python tests/bot_eval/grade.py RUN.json [--out FILE] [--ground FILE,FILE] [--quiet]
or `make bot-eval-grade RUN=towns/_eval/runs/<run>.json`.

Input: a run file written by run.py. Output: `<run>.graded.json` (the run file is never modified)
= the run document + `grades` on every scenario (D1-D5, D9-D13 over all its turns) and on every
turn (D6-D8, on that turn's answer) + `grader` metadata. The 6.4 summary goes to stdout.

Result of a check: {"status": "pass" | "fail" | "n.a.", "evidence": str, "subs": {name: bool}}.
`subs` are the named parts of a composite check (D8: table/narration/slash/tool_names, D12:
calls/repeats, D11: one per invariant); a scenario's `hard_checks` may name a whole check ("D3")
or a part ("D12:calls"). A scenario is a hard fail when one of its hard checks fails.

Which turn / which calls: tool checks (D1-D5, D9-D13) look at every turn of the scenario together;
answer checks (D6-D8) at one turn. Tool calls = tools of the myhordes server (`main.py`'s 28);
`ToolSearch` (the CLI loading a deferred tool schema) and every other harness tool are reported
(`harness_calls`) and left out of D12 and of repeat counts. Skill / Write / Edit / Bash /
NotebookEdit calls fail D2.
"""

import argparse
import ast
import fnmatch
import gzip
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tests" / "bot_eval"))
sys.path.insert(0, str(ROOT / "src"))
import scenario as scn   # noqa: E402
from scenario import FIXTURES, INVARIANT_NAMES   # noqa: E402

GRADER_VERSION = 1
PASS, FAIL, NA = "pass", "fail", "n.a."
DEFAULT_MAX_CALLS = 6
MIN_WORDS = 30                     # D7: under this many words the judge decides
SYNTH_USER = "100000000000000001"  # server.SYNTH_USER (kept here: server imports the whole offline harness)
DISCORD_LIMIT = 2000
# Files whose text the model had besides tool outputs (D6). The listener loads persona.md and
# prompts/discord.md; the game primer is read from the example toml / terminal, so it is always added.
DEFAULT_GROUND = ["persona.md", "prompts/discord.md", "prompts/discord-feedback.md", "prompts/game-primer.md"]
HARNESS_FORBIDDEN = ("Skill", "Write", "Edit", "Bash", "NotebookEdit")   # D2: no skill, no file or shell access
WRITE_TOOLS = ("remember", "forget")                                      # D2: not in a thread


def res(status: str, evidence: str = "", subs: dict | None = None) -> dict:
    out = {"status": status, "evidence": evidence}
    if subs is not None:
        out["subs"] = subs
    return out


# ── tool names from main.py (the model's tool list), once ───────────────────

_TOOLS: tuple[list[str], list[str]] | None = None


def server_tools() -> tuple[list[str], list[str]]:
    """(tool names, parameter names containing '_') of the @mcp.tool functions in main.py."""
    global _TOOLS
    if _TOOLS is None:
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        names, params = [], set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                    "mcp.tool" in ast.unparse(d) for d in n.decorator_list):
                names.append(n.name)
                params.update(a.arg for a in n.args.args + n.args.kwonlyargs if "_" in a.arg)
        if not names:
            raise RuntimeError("no @mcp.tool function found in main.py")
        _TOOLS = (sorted(names), sorted(params))
    return _TOOLS


# ── text helpers ────────────────────────────────────────────────────────────

def norm(text: str) -> str:
    """Thousands separators out: 4,377 / 4 377 / 4<nbsp>377 -> 4377 (port of the old grade.py)."""
    return re.sub(r"(\d)[,   ](\d{3})\b", r"\1\2", text)


def norm_text(text: str) -> str:
    """norm + decimal comma -> point ("4,88" -> "4.88"), for matching facts."""
    return re.sub(r"(\d),(\d{1,2})(?!\d)", r"\1.\2", norm(text))


def unwrap(out) -> str:
    """The MCP text of a trace output: the CLI wraps it as {"result": "..."}."""
    if isinstance(out, str):
        s = out.strip()
        if s.startswith("{") and '"result"' in s[:20]:
            try:
                d = json.loads(s)
                if isinstance(d, dict) and isinstance(d.get("result"), str):
                    return d["result"]
            except json.JSONDecodeError:
                pass
        return out
    return json.dumps(out, ensure_ascii=False)


def strip_code(text: str) -> str:
    return re.sub(r"```.*?```", " ", text, flags=re.S)


def words(text: str) -> list[str]:
    return re.findall(r"[a-zàâçéèêëîïôûùüÿñæœäöß]+", text.lower())


def num_tokens(text: str) -> set[str]:
    return set(re.findall(r"\d+", norm(text)))


def coord_set(text: str) -> set[tuple[int, int]]:
    return {(int(a), int(b)) for a, b in re.findall(r"\[\s*(-?\d+)\s*[|/]\s*(-?\d+)\s*\]", text)}


# ── fixture knowledge: citizens, catalogue ──────────────────────────────────

class Fixture:
    """What a fixture's /towndata says: citizen names, town name and ids, item / building names."""
    def __init__(self, fid: str):
        self.id = fid
        self.citizens: list[str] = []
        self.town_names: list[str] = []
        self.town_ids: set[int] = set()
        self.names: set[str] = set()        # item / building / construction names (name_en)
        self.heavy: set[str] = set()        # lower-case names of heavy items
        base = FIXTURES / fid / "towns"
        if not base.is_dir():
            return
        for d in sorted(base.iterdir()):
            meta = d / "cache" / "_meta.json"
            if not meta.exists():
                continue
            m = json.loads(meta.read_text())
            self.town_ids.add(m["town_id"])
            day = m["current_day"]
            for name in (f"day-{day:02d}.towndata.json.gz", f"day-{day:02d}.towndata.live.json.gz"):
                f = d / "cache" / name
                if f.exists():
                    data = json.loads(gzip.decompress(f.read_bytes()))
                    self.citizens += [c["name"] for c in data.get("town_citizens", []) if c.get("name")]
                    if (data.get("town_info") or {}).get("name"):
                        self.town_names.append(data["town_info"]["name"])
                    for key in ("item_data", "building_data", "construction_data"):
                        for e in data.get(key) or []:
                            if e.get("name_en"):
                                self.names.add(e["name_en"])
                    for e in data.get("item_data") or []:
                        if e.get("heavy") and e.get("name_en"):
                            self.heavy.add(e["name_en"].lower())
                    break

    def catalogue_names(self) -> list[str]:
        """Names worth grounding: several words (any case) or one word of 7+ letters; single
        common words ("Water", "Door") would match ordinary prose."""
        return sorted((n for n in self.names if len(n.split()) >= 2 or len(n) >= 7 and n.isalpha()),
                      key=len, reverse=True)


# ── D7: language ────────────────────────────────────────────────────────────

_STOP = {
    "it": "il lo la le gli un una di del della dei delle che è e per con non sono come da al alla nel nella più ma se "
          "anche questo questa hai ho ha hanno puoi può solo tutti tutto sul sulla quando dove cosa ci si mi ti "
          "sia essere molto ogni però quindi già ancora dopo prima".split(),
    "en": "the and of to you your that this for with it as be not have can will at by from or if but we our they "
          "there what which when how does was than then its are is an on an any only also more each into".split(),
    "fr": "le la les un une des du de et est sont que qui pour avec pas vous tu je il elle nous ils dans sur au aux ce "
          "cette ces mais ou où comme plus par sans avez as ont peut faut fait être très si en très aussi chaque "
          "donc alors avant après".split(),
    "es": "el los las un una unos del de y que es son para con no por en se su sus como pero más este esta esto muy "
          "hay está están puede tiene si al lo le te también cada entonces antes después".split(),
    "nl": "de het een en van is dat niet op voor met zijn er maar ook als aan bij je jij we wij ze ik naar nog wel "
          "geen dit deze die heb hebt heeft kan kun wordt worden om dan door uit over tot zo daar hier nu".split(),
    "de": "der die das den dem des ein eine einen und ist sind nicht mit für auf von zu im dass es sie du ich wir ihr "
          "aber auch wie oder wenn bei nach aus nur noch kann wird werden hat haben zum zur".split(),
}
# a word listed for two languages counts for neither
_ALL = [w for ws in _STOP.values() for w in set(ws)]
STOPWORDS = {lang: {w for w in set(ws) if _ALL.count(w) == 1} for lang, ws in _STOP.items()}
OTHER_LANGS = ("nl", "de", "es")


def lang_counts(text: str) -> dict[str, int]:
    toks = words(text)
    return {lang: sum(1 for t in toks if t in sw) for lang, sw in STOPWORDS.items()}


def clean_for_language(text: str, fx: Fixture | None, extra: list[str] = ()) -> str:
    """Answer text without what is not prose: code blocks, quoted tool lines (`>`), inline code,
    mentions, citizen / town / catalogue names, URLs."""
    t = strip_code(text)
    t = "\n".join(l for l in t.splitlines() if not l.lstrip().startswith(">"))
    t = re.sub(r"`[^`]*`", " ", t)
    t = re.sub(r"<@[!&]?\d+>|@\w+|https?://\S+", " ", t)
    drop = list(extra)
    if fx:
        drop += fx.citizens + fx.town_names + fx.catalogue_names()
    for n in sorted(set(drop), key=len, reverse=True):
        if n:
            t = re.sub(r"(?<!\w)" + re.escape(n) + r"(?!\w)", " ", t, flags=re.I if len(n.split()) > 1 else 0)
    return t


def detect_language(text: str) -> tuple[str, dict[str, int], int]:
    """(language of the text: it/en/fr/other:xx, counts, number of words)."""
    c = lang_counts(text)
    n = len(words(text))
    best = max(c, key=lambda k: c[k])
    if c[best] == 0:
        return "?", c, n
    return (best if best in ("it", "en", "fr") else f"other:{best}"), c, n


def check_d7(turn: dict, answer: str, fx: Fixture | None, user_names: list[str]) -> dict:
    expected = turn.get("lang", "")
    if expected not in ("it", "en", "fr"):
        return res(NA, f"expected language '{expected}' is not it/en/fr")
    text = clean_for_language(answer, fx, user_names)
    lang, c, n = detect_language(text)
    counts = " ".join(f"{k}={v}" for k, v in c.items())
    if n < MIN_WORDS:
        return res(NA, f"{n} words (< {MIN_WORDS}): left to the judge; stop-words {counts}")
    if lang == "?":
        return res(NA, f"no stop-word found in {n} words")
    top = max(c.values())
    if c[expected] >= top:
        others = [f"{k}={v}" for k, v in c.items() if k != expected and v >= 4 and v * 6 >= c[expected]]
        first = next((l for l in text.splitlines() if len(words(l)) >= 5), "")
        fl, fc, _ = detect_language(first) if first else ("?", {}, 0)
        opening = f"; opening line is {fl}" if fl not in ("?", expected) and fc.get(fl, 0) >= 2 else ""
        return res(PASS, f"{expected} ({counts})" + (f"; mixed with {' '.join(others)}" if others else "") + opening)
    return res(FAIL, f"expected {expected}, text is {lang} ({counts}; {n} words)")


# ── D8: Discord format ──────────────────────────────────────────────────────

TERMINAL_SKILLS = ("inspect-town", "build-plan", "close-day", "building-report", "expedition-report",
                   "update-garbage-dump-list", "review-bot-feedback")
DISCORD_COMMANDS = ("help", "set-my-town", "new")
NARRATION = re.compile(
    r"\b(let me (check|look|fetch|pull|see|run)|i'?ll (now )?(check|look|fetch|pull|run|keep|monitor|let you know|notify|remind|re-?check)\b(?! again)"
    r"|i will (now )?(check|look|fetch|let you know|notify|remind)|i('?m| am) going to|let'?s (check|look)"
    r"|one moment|just a moment|hold on while|checking now|looking (it )?up now"
    r"|(ora|adesso|ecco che) (controllo|verifico|guardo|cerco)|fammi (controllare|vedere|verificare)|vediamo (subito|cosa)|un attimo che"
    r"|sto (controllando|verificando|cercando|guardando)|ti avviso|ti faccio sapere|ti avvertir[òo]|ricontroll(o|er[òo])"
    r"|domani (mattina )?(controllo|verifico|ricontrollo)"
    r"|je vais (v[ée]rifier|regarder|consulter|chercher|voir)|laissez-moi|laisse-moi|un instant|je (v[ée]rifie|regarde|consulte) maintenant"
    r"|je (te|vous) pr[ée]viendrai|je (re)?v[ée]rifierai)\b", re.I)
TOOL_PHRASES = re.compile(
    r"\b(the|this|that|a) tools?\b|\btools? (says|says|shows|flags|counts|reports|returned|output)\b|\bil tool\b|\bi tool\b"
    r"|\bquel tool\b|\bl['’]outil\b|\bles outils\b|\bcet outil\b|\bMCP\b", re.I)


def tool_name_hits(text: str) -> list[str]:
    """Tool / parameter names or 'the tool' phrases in the prose (code blocks included: the reader sees them)."""
    names, params = server_tools()
    hits = [n for n in names + params if "_" in n and re.search(r"(?<![\w])" + re.escape(n) + r"(?![\w])", text)]
    hits += [m.group(0) for m in re.finditer(r"\b(detail|mode|slots|pickups|waypoints|available|town_id|step_table)\s*=", text)]
    hits += [m.group(0) for m in TOOL_PHRASES.finditer(text)]
    return sorted(set(hits))


def check_d8(answer: str) -> dict:
    outside = strip_code(answer)
    subs, ev = {}, []
    rows = [l.strip() for l in outside.splitlines() if re.match(r"^\s*\|.*\|\s*$", l)]
    subs["table"] = not rows
    if rows:
        ev.append(f"table row outside a code block: {rows[0][:60]!r} ({len(rows)} row(s))")
    m = NARRATION.search(outside)
    subs["narration"] = not m
    if m:
        ev.append(f"narration / promise: {m.group(0)!r}")
    slash = [s for s in re.findall(r"(?<![\w/.:])/([a-z][a-z-]{2,})\b(?!/)", outside) if s not in DISCORD_COMMANDS]
    subs["slash"] = not slash
    if slash:
        ev.append(f"slash command(s): {sorted(set('/' + s for s in slash))}")
    hits = tool_name_hits(answer)
    subs["tool_names"] = not hits
    if hits:
        ev.append(f"tool / parameter names: {hits[:8]}")
    chars = len(answer)
    chunks = max(1, math.ceil(chars / DISCORD_LIMIT))
    ev.append(f"length {chars} chars, {chunks} chunk(s) of {DISCORD_LIMIT}")
    return res(PASS if all(subs.values()) else FAIL, "; ".join(ev), subs)


# ── D6: grounding ───────────────────────────────────────────────────────────

DATE_TIME = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?\b|\b\d{1,2}:\d{2}(?::\d{2})?\b")
ARITHMETIC = re.compile(r"\d\s*(?:[+×*/÷=]|\sx\s|\s[-−–]\s)\s*\d|=\s*\d|calculation|arithmetic|remaining|short by|"
                        r"calcolo|rimanent|mancano|calcul|reste", re.I)


def check_d6(answer: str, corpus: str, fx: Fixture | None) -> dict:
    text = re.sub(r"<@[!&]?\d+>|https?://\S+", " ", answer)
    cnorm = norm(corpus)
    cnums = num_tokens(corpus)
    ccoords = coord_set(corpus)
    clow = corpus.lower()
    ung_num, ung_coord, ung_name, derived = set(), set(), set(), set()
    for line in text.splitlines():
        scan = DATE_TIME.sub(" ", line)
        scan = re.sub(r"\[\s*-?\d+\s*[|/]\s*-?\d+\s*\]", " ", scan)
        is_derived = bool(ARITHMETIC.search(scan))
        for n in re.findall(r"\b\d{2,6}\b", norm(scan)):
            if n.lstrip("0") in ("",) or n in cnums or str(int(n)) in cnums:
                continue
            (derived if is_derived else ung_num).add(n)
    for a, b in coord_set(text):
        if (a, b) not in ccoords:
            ung_coord.add(f"[{a}|{b}]")
    if fx:
        for name in fx.catalogue_names():
            if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.I if len(name.split()) > 1 else 0) \
                    and name.lower() not in clow:
                ung_name.add(name)
        # a name that contains another ("Water Ration" / "Ration") is reported once
        ung_name = {n for n in ung_name if not any(n != m and n in m for m in ung_name)}
    ev = (f"ungrounded numbers {len(ung_num)} {sorted(ung_num, key=int)[:12]}; "
          f"coordinates {len(ung_coord)} {sorted(ung_coord)[:8]}; names {len(ung_name)} {sorted(ung_name)[:8]}; "
          f"exempt (arithmetic shown) {len(derived)}")
    bad = len(ung_num) + len(ung_coord) + len(ung_name)
    out = res(FAIL if bad else PASS, ev)
    out["counts"] = {"numbers": len(ung_num), "coordinates": len(ung_coord), "names": len(ung_name),
                     "derived": len(derived)}
    out["ungrounded"] = {"numbers": sorted(ung_num, key=int), "coordinates": sorted(ung_coord),
                         "names": sorted(ung_name)}
    return out


# ── tool-call helpers ───────────────────────────────────────────────────────

def is_game_tool(name: str) -> bool:
    return name in server_tools()[0]


def split_calls(turns: list[dict]) -> tuple[list[dict], list[dict]]:
    """(game calls, harness calls) over every turn, in order; each call gets its turn index."""
    game, harness = [], []
    for i, t in enumerate(turns):
        for c in t.get("trace") or []:
            c = {**c, "turn": i}
            (game if is_game_tool(c["tool"]) else harness).append(c)
    return game, harness


def match_arg(value, spec) -> bool:
    """One argument against an expectation: a literal (equal after str/lower), or {op: x} with op in
    ge le gt lt in contains present absent available_ge (water=1, food7=1 style text)."""
    if isinstance(spec, dict):
        (op, x), = spec.items()
        if op == "absent":
            return value is None
        if op == "present":
            return (value not in (None, "", [], {})) == bool(x)
        if value is None:
            return False
        if op in ("ge", "le", "gt", "lt"):
            try:
                v = float(value)
            except (TypeError, ValueError):
                return False
            return {"ge": v >= x, "le": v <= x, "gt": v > x, "lt": v < x}[op]
        if op == "in":
            return any(str(value).strip().lower() == str(y).lower() for y in x)
        if op == "contains":
            return str(x).lower() in str(value).lower()
        if op == "available_ge":
            from myhordes_mcp.fata.supplies import parse_available
            have = parse_available(str(value))
            return isinstance(have, dict) and all(have.get(k, 0) >= n for k, n in
                                                  parse_available(str(x)).items())
        raise ValueError(f"unknown argument predicate '{op}'")
    if value is None:
        return False
    return str(value).strip().lower() == str(spec).strip().lower()


def call_matches(call: dict, want: dict) -> bool:
    return call["tool"] == want["tool"] and all(match_arg(call["args"].get(k), v)
                                                for k, v in (want.get("args") or {}).items())


def fmt_call(c: dict) -> str:
    return f"{c['tool']}({', '.join(f'{k}={v!r}' for k, v in c['args'].items())})"


# ── D1-D5, D10, D12, D13 ────────────────────────────────────────────────────

def tool_groups(tools_any: list) -> list[list[str]]:
    """tools_any: a list of names = one group (any of them); a list of lists = every group needs a hit."""
    if all(isinstance(x, str) for x in tools_any):
        return [list(tools_any)] if tools_any else []
    return [[g] if isinstance(g, str) else list(g) for g in tools_any]


def check_d1(s: dict, game: list[dict]) -> dict:
    groups = tool_groups(s["tools_any"])
    if not groups:
        return res(NA, "no tools_any in the scenario")
    called = {c["tool"] for c in game}
    missing = [g for g in groups if not called & set(g)]
    ev = f"called {sorted(called) or 'nothing'}"
    return res(FAIL, f"{ev}; no hit for {missing}") if missing else res(PASS, ev)


def check_d2(s: dict, game: list[dict], harness: list[dict], rec: dict) -> dict:
    bad = []
    for c in game:
        if c["tool"] in s["tools_forbidden"]:
            bad.append(f"forbidden tool {fmt_call(c)}")
        if c["tool"] in WRITE_TOOLS and rec.get("context") == "thread":
            bad.append(f"{c['tool']} in a thread")
    for c in harness:
        if c["tool"] in HARNESS_FORBIDDEN:
            bad.append(f"harness tool {c['tool']} {json.dumps(c['args'], ensure_ascii=False)[:80]}")
    denied = [d for t in rec["turns"] for d in t.get("permission_denials") or []]
    for d in denied:
        bad.append(f"permission denied: {json.dumps(d, ensure_ascii=False)[:100]}")
    return res(FAIL, "; ".join(bad)) if bad else res(PASS, "no forbidden tool, skill or write attempt")


ASKED_FULL = re.compile(r"\b(full|complete|everything|in detail|detailed|all items|tutt[oi]|complet\w*|dettagli\w*|"
                        r"int[ée]gral\w*|d[ée]tail\w*|tout)\b", re.I)
DICE_CARDS = re.compile(r"\b(dice|dadi?|d[ée]s?|cards?|carte|cartes)\b", re.I)
# Tools whose start_ap is AP at departure; each refuses a day budget (> 12) with this error.
START_AP_TOOLS = ("plan_expedition_supplies", "find_expedition_path", "plan_kill_route")
REFUSED_BUDGET = "Error: start_ap="


def refused_budget(c: dict) -> bool:
    """The tool refused the call because start_ap was a day budget: nothing was planned from it.
    Baseline 2026-11-20: every model (Opus too) tries start_ap=N first and redoes the call after
    this refusal; only a start_ap the tool accepted can reach the answer (maintainer, option a)."""
    return REFUSED_BUDGET in (c.get("out") or "")[:200]


def check_d3(s: dict, game: list[dict], user_text: str, fx: Fixture) -> dict:
    if not game:
        return res(NA, "no game tool call")
    bad, refused = [], []
    for c in game:
        a = c["args"]
        if c["tool"] in START_AP_TOOLS and a.get("start_ap") not in (None, "", 6, "6"):
            try:
                over = float(a["start_ap"]) > 6
            except (TypeError, ValueError):
                over = True
            if over and not DICE_CARDS.search(user_text):
                (refused if refused_budget(c) else bad).append(f"start_ap={a['start_ap']} ({fmt_call(c)[:60]})")
        if c["tool"] == "plan_kill_route" and str(a.get("available", "")).strip():
            bad.append(f"plan_kill_route available={a['available']!r}")
        if str(a.get("detail", "")).lower() == "full" and not ASKED_FULL.search(user_text):
            bad.append(f"{c['tool']} detail='full'")
        if a.get("include_all") in (True, "true", "True", 1) and not ASKED_FULL.search(user_text):
            bad.append(f"{c['tool']} include_all")
        if a.get("town_id") not in (None, "", 0) and fx.town_ids and str(a["town_id"]).isdigit() \
                and int(a["town_id"]) not in fx.town_ids and not re.search(r"\b" + str(a["town_id"]) + r"\b", user_text):
            bad.append(f"{c['tool']} town_id={a['town_id']} (not in the fixture {sorted(fx.town_ids)}, not in the question)")
    for want in s["args_forbidden"]:
        for c in game:
            if call_matches(c, want):
                bad.append(f"forbidden arguments: {fmt_call(c)[:90]}")
    note = f"; refused by the tool and not counted: {', '.join(refused)}" if refused else ""
    return (res(FAIL, "; ".join(dict.fromkeys(bad)) + note) if bad
            else res(PASS, f"{len(game)} call(s), no forbidden argument{note}"))


def check_d4(s: dict, game: list[dict]) -> dict:
    if not s["args_required"]:
        return res(NA, "no args_required in the scenario")
    miss = []
    for want in s["args_required"]:
        if not any(call_matches(c, want) for c in game):
            same = [fmt_call(c)[:90] for c in game if c["tool"] == want["tool"]]
            miss.append(f"{want['tool']} {json.dumps(want.get('args') or {}, ensure_ascii=False)}: "
                        + (f"calls were {same}" if same else "tool not called"))
    return res(FAIL, "; ".join(miss)) if miss else res(PASS, f"{len(s['args_required'])} required argument set(s) found")


def fact_in(fact: str, text_n: str) -> bool:
    f = norm_text(str(fact)).strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", f):
        variants = {f}
        if "." in f:
            variants.add(f.rstrip("0").rstrip("."))
        return any(re.search(r"(?<![\d.])" + re.escape(v) + r"(?!\d|\.\d)", text_n) for v in variants)
    return re.search(r"(?<!\w)" + re.escape(f) + r"(?!\w)", text_n, re.I) is not None


def check_d5(s: dict, expected: list | None, answer: str) -> dict:
    if not s["facts_from"]:
        return res(NA, "no facts_from in the scenario")
    if expected is None:
        return res(NA, "no entry in the fixture's expected.json (run `make bot-eval-expect`)")
    facts = [g for e in expected for grp in (e.get("groups") or []) if grp for g in grp if g not in (None, "")]
    if not facts:
        return res(NA, "expected.json holds no captured fact")
    text_n = norm_text(answer)
    missing = [f for f in facts if not fact_in(f, text_n)]
    ev = f"{len(facts) - len(missing)}/{len(facts)} facts present"
    return res(FAIL, f"{ev}; missing {missing}") if missing else res(PASS, ev)


# D9 ---------------------------------------------------------------------------

def name_hits(answer: str, names: list[str], exclude: str = "") -> tuple[list[str], list[str]]:
    """(citizen names found, ambiguous names skipped). Whole word, case-sensitive, not inside a
    hyphenated word. A short lower-case name or one that is an ordinary word counts only when it is
    marked as a name (bold, code, quotes, @)."""
    stop = {w for ws in _STOP.values() for w in ws}
    found, skipped = [], []
    for n in sorted(set(names), key=len, reverse=True):
        if not n or re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", exclude):
            continue
        pat = r"(?<![\w-])" + re.escape(n) + r"(?![\w-])"
        ambiguous = n.lower() in stop or (n.islower() and len(n) <= 5)
        if ambiguous:
            if re.search(r"(\*\*|`|@|\"|“|«)" + re.escape(n) + r"(\*\*|`|\"|”|»)?(?!\w)", answer):
                found.append(n)
            elif re.search(pat, answer):
                skipped.append(n)
        elif re.search(pat, answer):
            found.append(n)
    return found, skipped


def check_d9(s: dict, answer: str, fx: Fixture, user_text: str, exclude_names: list[str]) -> dict:
    found, skipped = name_hits(answer, [n for n in fx.citizens if n not in exclude_names], user_text)
    note = f"; ambiguous words skipped {skipped}" if skipped else ""
    if s["names_max"] < 0 and not s["names_expected"]:
        return res(NA, f"no names rule in the scenario ({len(found)} citizen name(s) in the answer, not scored){note}")
    bad = []
    if 0 <= s["names_max"] < len(found):
        bad.append(f"{len(found)} citizen name(s), at most {s['names_max']}: {found[:16]}")
    missing = [n for n in s["names_expected"] if not re.search(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", answer, re.I)]
    if missing:
        bad.append(f"expected name(s) missing: {missing}")
    return res(FAIL, "; ".join(bad) + note) if bad else res(PASS, f"{len(found)} citizen name(s){note}")


# D10 ---------------------------------------------------------------------------

def tool_itineraries(game: list[dict]) -> list[list[tuple[int, int]]]:
    """The coordinates, in order, of each **Itinerary** block of a route tool output."""
    out = []
    for c in game:
        if c["tool"] not in ("plan_expedition_supplies", "plan_kill_route", "find_expedition_path"):
            continue
        text = unwrap(c.get("out", ""))
        m = re.search(r"\*\*Itinerary\*\*(.*?)(?:\n\s*\n|\Z)", text, re.S)
        if not m:
            continue
        seq = []
        for a, b in re.findall(r"\[\s*(-?\d+)\s*[|/]\s*(-?\d+)\s*\]", m.group(1)):
            p = (int(a), int(b))
            if not seq or seq[-1] != p:
                seq.append(p)
        out.append(seq)
    return out


def is_subsequence(small: list, big: list) -> bool:
    it = iter(big)
    return all(x in it for x in small)


def answer_itinerary(answer: str) -> list[tuple[int, int]]:
    seq = []
    for line in strip_code(answer).splitlines():
        if re.match(r"^\s*(\d+[.)]|[-*•])\s", line):
            for a, b in re.findall(r"\[\s*(-?\d+)\s*[|/]\s*(-?\d+)\s*\]", line):
                p = (int(a), int(b))
                if not seq or seq[-1] != p:
                    seq.append(p)
    return seq


def check_d10(game: list[dict], answer: str) -> dict:
    its = tool_itineraries(game)
    if not its:
        return res(NA, "no tool Itinerary in the session")
    mine = answer_itinerary(answer)
    if len(mine) < 2:
        return res(NA, "the answer has no list of coordinates to compare")
    if any(is_subsequence(mine, it) for it in its):
        return res(PASS, f"{len(mine)} answer coordinates are in the tool Itinerary, in order")
    best = max(its, key=lambda it: sum(1 for p in mine if p in it))
    off = [f"[{a}|{b}]" for a, b in mine if (a, b) not in best]
    return res(FAIL, f"answer coordinates not an ordered subsequence of the tool Itinerary; not in it: {off[:8]}")


# D11 ---------------------------------------------------------------------------

def inv_no_tool_names(ctx):
    """prompts/discord.md (never name your tools): same detector as D8 tool_names. Source: F19."""
    hits = tool_name_hits(ctx["answer"])
    return (FAIL, f"names: {hits[:8]}") if hits else (PASS, "no tool or parameter name")


def inv_start_ap_6(ctx):
    """prompts/game-primer.md 'N AP is the day budget' + fata/expedition.py:37 guard: start_ap is 6 (F1)."""
    calls = [c for c in ctx["game"] if c["tool"] == "plan_expedition_supplies"]
    if not calls:
        return NA, "no plan_expedition_supplies call"
    off = [c for c in calls if c["args"].get("start_ap") not in (None, "", 6, "6")]
    bad = [fmt_call(c)[:70] for c in off if not refused_budget(c)]
    refused = [fmt_call(c)[:70] for c in off if refused_budget(c)]
    note = f"; refused by the tool and not counted: {refused}" if refused else ""
    return (FAIL, f"start_ap: {bad}{note}") if bad else (PASS, f"start_ap 6 / default on every accepted call{note}")


def inv_camping_one_call_until_day(ctx):
    """main.py plan_group_camping docstring, game-primer.md:178: several nights = ONE call with until_day,
    never one per night (each call restarts from today's bonus). Source: F18, C3."""
    calls = [c for c in ctx["game"] if c["tool"] == "plan_group_camping"]
    if not calls:
        return NA, "no plan_group_camping call"
    zones = {}
    for c in calls:
        zones.setdefault((c["args"].get("x"), c["args"].get("y")), []).append(c)
    bad = [f"{len(v)} calls for zone {k}: {[fmt_call(c)[:70] for c in v]}" for k, v in zones.items() if len(v) > 1]
    odds = [c for c in ctx["game"] if c["tool"] == "get_camping_odds"]
    if odds:
        bad.append(f"{len(odds)} get_camping_odds call(s) next to the group plan")
    return (FAIL, "; ".join(bad)) if bad else (PASS, f"{len(calls)} call(s), one per zone")


UPGRADE = re.compile(r"upgrade|improv|migliori|potenzi|am[ée]lior|amelior", re.I)
HIDING = re.compile(r"hiding order|hide first|hides first|who hides|ordine (di|per|in cui) (nascond|entr)|ordine di nascondi|"
                    r"nascond\w+ (per primo|prima)|chi si nasconde|ordre (de|pour) (se )?cach|se cache en premier|"
                    r"\b1st\b|1[°º]\b", re.I)
NIGHT_HEAD = re.compile(r"(?im)^\W*(?:night|notte|nuit)\s+\d+")


def inv_upgrades_before_hiding_order(ctx):
    """Odds freeze when each camper hides, so upgrades, graves and camp items come first (94d5058, F20, C4).
    Heuristic on the text: in each night block (or the whole answer) the first upgrade word precedes the first
    hiding-order word. A hiding order with no upgrade word at all fails when the tool output has an upgrade line."""
    ans = ctx["answer"]
    heads = [m.start() for m in NIGHT_HEAD.finditer(ans)]
    blocks = [ans[a:b] for a, b in zip(heads, heads[1:] + [len(ans)])] if len(heads) >= 2 else [ans]
    tool_text = " ".join(unwrap(c.get("out", "")) for c in ctx["game"] if c["tool"] == "plan_group_camping")
    bad, seen = [], 0
    for b in blocks:
        h = HIDING.search(b)
        if not h:
            continue
        seen += 1
        u = UPGRADE.search(b)
        if u and u.start() < h.start():
            continue
        if not u and not UPGRADE.search(tool_text):
            continue
        bad.append(f"hiding order at {h.start()} {'before upgrades at ' + str(u.start()) if u else 'with no upgrade word'}"
                   f" in {b.strip()[:40]!r}")
    if not seen:
        return NA, "no hiding order in the answer"
    return (FAIL, "; ".join(bad)) if bad else (PASS, f"upgrades before the hiding order ({seen} block(s))")


def _days_in(text: str) -> int | None:
    m = re.search(r"\b(\d{1,2})\s*(?:days?|nights?|giorn\w*|nott\w*|jours?|nuits?)\b", text, re.I)
    return int(m.group(1)) if m else None


def inv_water_rations_ceil_half_days(ctx):
    """Camping water = ceil(days / 2) rations, one every two days (NightlyHandler.php:1203-1205 per the 2026-11-13
    review; game-primer.md 'Days outside'). From the reader's 'N days' and the ration counts in the answer."""
    days = _days_in(ctx["user_text"])
    if not days:
        return NA, "no 'N days' in the question"
    need = math.ceil(days / 2)
    vals = {int(m.group(1)) for m in re.finditer(
        r"\b(\d{1,2})\s*(?:×\s*)?(?:water\s+)?(?:rations?|razion\w*|rations?\s+d)", ctx["answer"], re.I)}
    if not vals:
        return NA, "no ration count in the answer"
    if any(v > need for v in vals):
        return FAIL, f"{days} days need {need} ration(s); answer says {sorted(vals)}"
    return (PASS, f"{need} ration(s) for {days} days") if need in vals else (NA, f"counts {sorted(vals)}, none equal {need}")


def inv_heavy_items_max(ctx):
    """One heavy item per citizen, two for a Guardian (fata/game.py heavy_cap, game-primer.md heavy items): the
    heavy items in `pickups` of plan_expedition_supplies, by the fixture's catalogue `heavy` flag (F7)."""
    from myhordes_mcp.fata.game import heavy_cap
    calls = [c for c in ctx["game"] if c["tool"] == "plan_expedition_supplies" and c["args"].get("pickups")]
    if not calls:
        return NA, "no pickups argument"
    bad = []
    for c in calls:
        items = [i.strip().lower() for part in str(c["args"]["pickups"]).split(";")
                 for i in part.split(":", 1)[-1].split(",")]
        n = sum(1 for i in items if i in ctx["fx"].heavy)
        cap = heavy_cap(str(c["args"].get("guardian", "")).lower() in ("true", "1"))
        if n > cap:
            bad.append(f"{n} heavy pickups, cap {cap}: {fmt_call(c)[:70]}")
    return (FAIL, "; ".join(bad)) if bad else (PASS, "heavy pickups within the cap")


def inv_drugs_max_one(ctx):
    """One drug per day, alcohol is not a drug (game-primer.md AP section; a second drug makes an addict, F1/F7):
    steroid + twinoid in `available` of a supplies / kill call add up to at most 1."""
    from myhordes_mcp.fata.supplies import parse_available
    calls = [c for c in ctx["game"] if c["tool"] in ("plan_expedition_supplies", "plan_kill_route")
             and str(c["args"].get("available", "")).strip()]
    if not calls:
        return NA, "no available argument"
    bad = []
    for c in calls:
        have = parse_available(str(c["args"]["available"]))
        if isinstance(have, dict) and have.get("steroid", 0) + have.get("twinoid", 0) > 1:
            bad.append(fmt_call(c)[:80])
    return (FAIL, f"two drugs: {bad}") if bad else (PASS, "at most one drug in available")


INVARIANTS = {
    "no_tool_names": inv_no_tool_names,
    "start_ap_6": inv_start_ap_6,
    "camping_one_call_until_day": inv_camping_one_call_until_day,
    "upgrades_before_hiding_order": inv_upgrades_before_hiding_order,
    "water_rations_ceil_half_days": inv_water_rations_ceil_half_days,
    "heavy_items_max": inv_heavy_items_max,
    "drugs_max_one": inv_drugs_max_one,
}
assert set(INVARIANTS) == set(INVARIANT_NAMES), "scenario.INVARIANT_NAMES and grade.INVARIANTS differ"


def check_d11(s: dict, ctx: dict) -> dict:
    if not s["invariants"]:
        return res(NA, "no invariants in the scenario")
    subs, ev, na = {}, [], 0
    for name in s["invariants"]:
        status, e = INVARIANTS[name](ctx)
        if status == NA:
            na += 1
        else:
            subs[name] = status == PASS
        ev.append(f"{name}: {status} ({e})")
    if not subs:
        return res(NA, "; ".join(ev), subs)
    return res(PASS if all(subs.values()) else FAIL, "; ".join(ev), subs)


# D12 / D13 ---------------------------------------------------------------------

def check_d12(s: dict, game: list[dict], harness: list[dict], turns: list[dict]) -> dict:
    cap = s["max_calls"] or DEFAULT_MAX_CALLS
    seen, repeats = set(), []
    for c in game:
        k = (c["tool"], json.dumps(c["args"], sort_keys=True))
        if k in seen:
            repeats.append(fmt_call(c)[:70])
        seen.add(k)
    secs = round(sum(t.get("secs") or 0 for t in turns), 1)
    u = [t.get("usage") or {} for t in turns]
    tok = {"in": sum(x.get("input_tokens") or 0 for x in u), "out": sum(x.get("output_tokens") or 0 for x in u),
           "cache": sum((x.get("cache_read") or 0) + (x.get("cache_created") or 0) for x in u)}
    ts = sum(1 for c in harness if c["tool"] == "ToolSearch")
    other = sorted({c["tool"] for c in harness if c["tool"] != "ToolSearch"})
    subs = {"calls": len(game) <= cap, "repeats": not repeats}
    ev = (f"{len(game)} call(s) (cap {cap}), {len(repeats)} repeated; ToolSearch {ts}"
          + (f", other harness tools {other}" if other else "")
          + f"; {secs}s, tokens in/out/cache {tok['in']}/{tok['out']}/{tok['cache']}")
    if repeats:
        ev += f"; repeats {repeats}"
    return res(PASS if all(subs.values()) else FAIL, ev, subs)


def parse_manifest(text: str | None) -> dict[str, str] | None:
    if text is None:
        return None
    out = {}
    for line in text.splitlines():
        if line.strip():
            path, _, h = line.rpartition("  ")
            out[path] = h
    return out


def baseline_manifest(s: dict, fx_id: str) -> dict[str, str]:
    """Paths and hashes of the temporary towns/ before the first call: the fixture's towns/ (offline.manifest
    format: sha1[:12] of the decompressed content), `_current_town`, and the scenario's memory / user_town files."""
    base = FIXTURES / fx_id / "towns"
    out = {}
    for f in sorted(p for p in base.rglob("*") if p.is_file()):
        data = f.read_bytes()
        if f.suffix == ".gz":
            data = gzip.decompress(data)
        out[str(f.relative_to(base))] = hashlib.sha1(data).hexdigest()[:12]
    if s.get("memory"):
        out[f"_bot/memory/{SYNTH_USER}.md"] = hashlib.sha1(s["memory"].encode()).hexdigest()[:12]
    if s.get("user_town"):
        out[f"_user_towns/{SYNTH_USER}"] = hashlib.sha1(str(s["user_town"]).encode()).hexdigest()[:12]
    return out


# written by the tools on a live fetch, expected in every run (the CP log, intraday snapshots)
ALLOWED_WRITES = ("_current_town", "*/cache/snapshots/*", "*/citizens-cp.json")


def check_d13(s: dict, rec: dict, guard: dict | None) -> dict:
    ev, bad = [], []
    if guard is None:
        ev.append("run file has no real_towns_guard")
    elif not guard.get("ok"):
        bad.append(f"real towns/ changed during the run: {guard.get('changed', [])[:5]}")
    else:
        ev.append("real towns/ unchanged")
    base = baseline_manifest(s, rec["fixture"])
    allowed = ALLOWED_WRITES + tuple(s.get("writes_allowed") or ())
    checked = 0
    for i, t in enumerate(rec["turns"]):
        mf = parse_manifest(t.get("manifest"))
        if mf is None:
            ev.append(f"turn {i + 1}: no manifest recorded")
            continue
        checked += 1
        diffs = [f"{'new' if p not in base else 'removed' if p not in mf else 'changed'} {p}"
                 for p in sorted(set(base) | set(mf)) if base.get(p) != mf.get(p)]
        diffs = [d for d in diffs if not any(fnmatch.fnmatch(d.split(" ", 1)[1], a) for a in allowed)]
        if diffs:
            bad.append(f"turn {i + 1}: {diffs[:6]}")
    if checked:
        ev.append(f"{checked} manifest(s) compared with the fixture, only expected writes")
    if bad:
        return res(FAIL, "; ".join(bad))
    if not checked and guard is None:
        return res(NA, "; ".join(ev))
    return res(PASS, "; ".join(ev))


# ── a scenario ──────────────────────────────────────────────────────────────

_FIXTURES: dict[str, Fixture] = {}


def fixture_of(fid: str) -> Fixture:
    if fid not in _FIXTURES:
        _FIXTURES[fid] = Fixture(fid)
    return _FIXTURES[fid]


def ground_text(files: list[str]) -> str:
    out = []
    for f in files:
        p = Path(f) if Path(f).is_absolute() else ROOT / f
        if p.is_file():
            out.append(p.read_text(encoding="utf-8"))
    return "\n".join(out)


def author_names(rec: dict) -> list[str]:
    """Names of the asker, in the prompt's '@name:' line (not a citizen in the sense of D9)."""
    names = set()
    for t in rec["turns"]:
        names.update(re.findall(r"\]\s*\d{4}-[^\n]*?@([^:\n]+):", t.get("prompt", "")))
    return sorted(names)


def grade_scenario(s: dict, rec: dict, expected: list | None, ground: str,
                   guard: dict | None, fx: Fixture | None = None) -> dict:
    """Grades of one scenario record. Returns {"scenario": {check: result}, "turns": [{D6, D7, D8}],
    "harness_calls": [...], "hard": [failed hard checks], "det": [passed, applicable]}."""
    fx = fx or fixture_of(rec["fixture"])
    turns = rec["turns"]
    game, harness = split_calls(turns)
    answers = [t.get("answer", "") for t in turns]
    answer = "\n\n".join(answers)
    user_text = "\n".join(t.get("user_text", "") for t in turns)
    asker = author_names(rec)
    ctx = {"s": s, "rec": rec, "game": game, "answer": answer, "user_text": user_text, "fx": fx}

    sc = {
        "D1": check_d1(s, game),
        "D2": check_d2(s, game, harness, rec),
        "D3": check_d3(s, game, user_text, fx),
        "D4": check_d4(s, game),
        "D5": check_d5(s, expected, answer),
        "D9": check_d9(s, answer, fx, user_text, asker),
        "D10": check_d10(game, answer),
        "D11": check_d11(s, ctx),
        "D12": check_d12(s, game, harness, turns),
        "D13": check_d13(s, rec, guard),
    }
    per_turn, seen_out = [], []
    for i, t in enumerate(turns):
        seen_out += [unwrap(c.get("out", "")) for c in t.get("trace") or []]
        corpus = "\n".join([ground] + [x.get("prompt", "") for x in turns[:i + 1]]
                           + [a for a in answers[:i]] + seen_out)
        ans = t.get("answer", "")
        per_turn.append({"D6": check_d6(ans, corpus, fx), "D7": check_d7(t, ans, fx, asker),
                         "D8": check_d8(ans)})
    hard = []
    for h in s["hard_checks"]:
        cid, _, sub = h.partition(":")
        for r in ([sc[cid]] if cid in sc else [pt[cid] for pt in per_turn]):
            if r["status"] != FAIL:
                continue
            if not sub or r.get("subs", {}).get(sub) is False:
                hard.append(h)
                break
    allres = list(sc.values()) + [r for pt in per_turn for r in pt.values()]
    applicable = [r for r in allres if r["status"] != NA]
    return {"scenario": sc, "turns": per_turn, "hard": hard,
            "det": [sum(1 for r in applicable if r["status"] == PASS), len(applicable)],
            "harness_calls": [{"tool": c["tool"], "args": c["args"]} for c in harness]}


# ── a run file ──────────────────────────────────────────────────────────────

def load_scenarios() -> dict[str, dict]:
    return {s["id"]: s for s in scn.load_all()}


def expected_for(fixture: str, sid: str) -> list | None:
    p = FIXTURES / fixture / "expected.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8")).get(sid)


def grade_run(doc: dict, scenarios: dict[str, dict], ground_files: list[str] | None = None) -> dict:
    """The run document with `grades` added (the input is not modified)."""
    ground = ground_text(ground_files or DEFAULT_GROUND)
    guard = doc.get("real_towns_guard")
    out = json.loads(json.dumps(doc))
    for rec in out["scenarios"]:
        s = scenarios.get(rec["id"])
        if s is None:
            raise SystemExit(f"scenario {rec['id']} of the run is not in {scn.SCENARIOS}")
        g = grade_scenario(s, rec, expected_for(rec["fixture"], rec["id"]), ground, guard)
        rec["grades"] = {"checks": g["scenario"], "hard_checks": s["hard_checks"], "hard_failed": g["hard"],
                         "det_passed": g["det"][0], "det_applicable": g["det"][1],
                         "harness_calls": g["harness_calls"]}
        for t, tg in zip(rec["turns"], g["turns"]):
            t["grades"] = tg
    out["grader"] = {"version": GRADER_VERSION, "ground_files": ground_files or DEFAULT_GROUND,
                     "scenario_sha256": {i: hashlib.sha256(json.dumps(s, sort_keys=True).encode()).hexdigest()
                                         for i, s in scenarios.items() if any(r["id"] == i for r in out["scenarios"])}}
    return out


def failures(rec: dict) -> list[tuple[str, str, str]]:
    """(check, scope, evidence) of every failed check of a graded scenario record."""
    g = rec["grades"]["checks"]
    out = [(k, "scenario", v["evidence"]) for k, v in g.items() if v["status"] == FAIL]
    for i, t in enumerate(rec["turns"]):
        out += [(k, f"turn {i + 1}", v["evidence"]) for k, v in t["grades"].items() if v["status"] == FAIL]
    return out


def judge_hits(rec: dict) -> list[int]:
    """Numbers of the HARD_FAIL items the judge marked as triggered (J2 = 1)."""
    return [x["item"] for x in (rec.get("judge") or {}).get("j2", []) if x.get("v") == 1]


def j1_stats(rec: dict) -> tuple[int, int, int] | None:
    """(satisfied, decided, total) over the MUST items, None without a judge verdict or without MUST items."""
    j = rec.get("judge")
    if not j or not j.get("j1"):
        return None
    vals = [x.get("v") for x in j["j1"]]
    decided = [v for v in vals if v is not None]
    return sum(1 for v in decided if v == 1), len(decided), len(vals)


def score_of(rec: dict) -> float | None:
    """Section 4.3. 0 on a hard fail (a hard D-check failed or any J2 = 1); else 0.5 x det pass rate + 0.5 x J1 mean;
    the det rate alone when there is no decided J1 item. None when the scenario has not been judged."""
    if not rec.get("judge"):
        return None
    g = rec["grades"]
    if g["hard_failed"] or judge_hits(rec):
        return 0.0
    det = g["det_passed"] / g["det_applicable"] if g["det_applicable"] else 1.0
    st = j1_stats(rec)
    if st is None or st[1] == 0:
        return det
    return 0.5 * det + 0.5 * st[0] / st[1]


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def summary(doc: dict) -> str:
    m = doc["meta"]
    lines = [f"suite={m['suite']} model={m['model_requested']} tier={m.get('tier_override') or 'per scenario'} "
             f"label={m['label']} sha={m['git_sha'][:7]}"]
    lines.append(f"{'ID':<5}{'lang':<7}{'HF':<4}{'det':<7}{'J1':<7}{'score':<7}{'calls':<7}{'secs':<7}{'out_chars':<11}note")
    hf = wrong = 0
    ung_ids, dets, scores, judged, j2_ids = [], [], [], 0, []
    jx = {k: [] for k in ("j3", "j4", "j5", "j6")}
    for rec in doc["scenarios"]:
        g = rec["grades"]
        turns = rec["turns"]
        calls = sum(1 for t in turns for c in t.get("trace", []) if is_game_tool(c["tool"]))
        secs = round(sum(t.get("secs") or 0 for t in turns), 1)
        chars = len(turns[-1].get("answer", ""))
        langs = ",".join(t.get("lang", "") for t in turns)
        hits = judge_hits(rec)
        is_hf = bool(g["hard_failed"] or hits)
        flag = "HF" if is_hf else "-"
        hf += is_hf
        fails = failures(rec)
        wrong += sum(1 for k, sc, _ in fails if k == "D7")
        if any(k == "D6" for k, _, _ in fails):
            ung_ids.append(rec["id"])
        dets.append(g["det_passed"] / g["det_applicable"] if g["det_applicable"] else 1.0)
        note = "; ".join(f"{k}{'*' if k in g['hard_failed'] or any(h.startswith(k + ':') for h in g['hard_failed']) else ''}"
                         for k, _, _ in fails)
        st, sc_ = j1_stats(rec), score_of(rec)
        if rec.get("judge"):
            judged += 1
            for k in jx:
                jx[k].append((rec["judge"].get(k) or {}).get("v"))
        if hits:
            j2_ids.append(rec["id"])
            note += ("; " if note else "") + "J2*" + ",".join(map(str, hits))
        if st:
            j1s = f"{st[0]}/{st[1]}" + ("?" if st[1] < st[2] else "")
        else:
            j1s = "-"
        if sc_ is not None:
            scores.append(sc_)
        lines.append(f"{rec['id']:<5}{langs:<7}{flag:<4}{str(g['det_passed']) + '/' + str(g['det_applicable']):<7}"
                     f"{j1s:<7}{('%.2f' % sc_) if sc_ is not None else '-':<7}"
                     f"{calls:<7}{secs:<7}{chars:<11}{note}")
    n = len(doc["scenarios"])
    ung_count = sum(t["grades"]["D6"]["counts"]["numbers"] for r in doc["scenarios"] for t in r["turns"])
    tail = (f"hard fails {hf}/{n} · mean det {sum(dets) / n:.2f} · wrong language {wrong} · "
            f"ungrounded numbers {ung_count}" + (f" ({', '.join(ung_ids)})" if ung_ids else ""))
    if judged:
        tail += f" · judged {judged}/{n} · mean score {sum(scores) / len(scores):.2f}"
        extra = []
        for k in jx:
            mv = _mean(jx[k])
            extra.append(f"{k.upper()} " + (f"{mv:.2f}" if mv is not None else "n/a"))
        tail += " · " + " ".join(extra)
    else:
        tail += " · judge: not run (make bot-eval-judge)"
    lines.append(tail)
    jm = doc.get("judge_meta")
    if jm:
        lines.append(f"judge {jm['model']} prompt {jm['prompt_sha256'][:12]} · {jm['calls']} call(s) · CLI cost ${jm['cli_cost_usd']:.4f}")
    tot = doc.get("totals") or {}
    if tot:
        lines.append(f"tokens by model {json.dumps(tot.get('per_model'))} · CLI cost ${tot.get('cli_cost_usd')} · wall {tot.get('secs')}s")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", help="run file written by run.py")
    ap.add_argument("--out", default="", help="default: <run>.graded.json")
    ap.add_argument("--ground", default="", help="comma-separated files that count as the system prompt (D6)")
    ap.add_argument("--quiet", action="store_true", help="summary only, no evidence of failed checks")
    args = ap.parse_args()
    path = Path(args.run)
    doc = json.loads(path.read_text(encoding="utf-8"))
    try:
        scenarios = load_scenarios()
    except scn.ScenarioError as exc:
        sys.exit(str(exc))
    graded = grade_run(doc, scenarios, [f for f in args.ground.split(",") if f] or None)
    out = Path(args.out) if args.out else path.with_name(path.stem + ".graded.json")
    if out.is_file():   # keep the judge verdicts (paid calls) of an earlier judge.py run on the same run file
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
            kept = {r["id"]: r["judge"] for r in prev.get("scenarios", []) if r.get("judge")}
            for r in graded["scenarios"]:
                if r["id"] in kept:
                    r["judge"] = kept[r["id"]]
            if kept and prev.get("judge_meta"):
                graded["judge_meta"] = prev["judge_meta"]
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    out.write_text(json.dumps(graded, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(summary(graded))
    if not args.quiet:
        for rec in graded["scenarios"]:
            for k, scope, ev in failures(rec):
                hard = " [HARD]" if k in rec["grades"]["hard_failed"] else ""
                print(f"  {rec['id']} {k} ({scope}){hard}: {ev}")
    print(f"graded file: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
