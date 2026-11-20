"""LLM judge of bot-eval run files (J1-J6 of docs/bot-eval-plan.md section 4.2, score of 4.3).

    .venv/bin/python tests/bot_eval/judge.py RUN.json [--only I1,C4] [--force] [--dry-run] [--model ID]
or `make bot-eval-judge RUN=towns/_eval/runs/<run>.json`.

Costs model calls (one `claude -p` call per scenario turn, opus by default): a person runs it, never cron, a
timer or CI. It grades nothing the deterministic grader (grade.py) decides: the D-checks are read from
`<run>.graded.json` (made on the fly when missing) and the judge verdicts are merged into that same file,
under `judge` on each scenario and `judge_meta` on the document.

The judge runs with NO tools, NO MCP servers, no skills, no settings, no CLAUDE.md, from an empty directory;
its system prompt is tests/bot_eval/judge_prompt.md. It is shown the conversation, the final answer, the tool
trace (output cut to 3000 chars), the scenario's `must` / `hard_fail` and the persona text. It is NOT shown the
model id, the tier, the run label or any deterministic grade.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tests" / "bot_eval"))
import grade as G   # noqa: E402

JUDGE_MODEL = "claude-opus-5-5"
PROMPT_FILE = ROOT / "tests" / "bot_eval" / "judge_prompt.md"
PERSONA_FILE = ROOT / "persona.md"
OUT_CUT = 3000
TIMEOUT = 600
MAX_BUDGET = "1.5"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── input of the judge ──────────────────────────────────────────────────────

def trace_text(trace: list[dict]) -> str:
    """Name, args and output (cut to OUT_CUT chars) of every call but ToolSearch."""
    lines = []
    for c in trace or []:
        if c.get("tool") == "ToolSearch":
            continue
        out = G.unwrap(c.get("out", ""))
        cut = len(out) > OUT_CUT
        lines.append(f"- {c['tool']}({json.dumps(c.get('args') or {}, ensure_ascii=False)})"
                     + (" [tool error]" if c.get("is_error") else ""))
        lines.append("  output: " + (out[:OUT_CUT] + f" [... cut, {len(out)} chars in all]" if cut else out).replace("\n", "\n    "))
    return "\n".join(lines) if lines else "(no tool was called)"


def numbered(items: list[str]) -> str:
    return "\n".join(f"{i}. {x}" for i, x in enumerate(items, 1)) if items else "(none)"


def build_input(must: list[str], hard_fail: list[str], history: list[tuple[str, str]], user_text: str,
                lang: str, answer: str, trace: list[dict], persona: str) -> str:
    earlier = "\n\n".join(f"[user] {u}\n[answer] {a}" for u, a in history) or "none"
    return "\n\n".join([
        "## EARLIER TURNS\n" + earlier,
        f"## LAST USER MESSAGE (language: {lang or 'unknown'})\n{user_text}",
        "## FINAL ANSWER\n" + (answer or "(empty answer)"),
        "## TOOL TRACE\n" + trace_text(trace),
        "## MUST\n" + numbered(must),
        "## HARD_FAIL\n" + numbered(hard_fail),
        "## PERSONA\n" + (persona.strip() or "not available"),
    ]) + "\n"


# ── the call ────────────────────────────────────────────────────────────────

def claude_argv(model: str, system: str) -> list[str]:
    """No tools, no MCP, no skills, no settings sources (so no CLAUDE.md / hooks / plugins), no session file."""
    return ["claude", "-p", "--model", model, "--system-prompt", system, "--tools", "",
            "--strict-mcp-config", "--disable-slash-commands", "--setting-sources", "",
            "--no-session-persistence", "--output-format", "json", "--max-budget-usd", MAX_BUDGET]


def call_claude(user: str, system: str, model: str) -> dict:
    """{result, cost_usd, usage, model_usage, secs, error}; the prompt goes through stdin, cwd is an empty temp dir."""
    with tempfile.TemporaryDirectory(prefix="judge-") as cwd:
        try:
            p = subprocess.run(claude_argv(model, system), input=user, capture_output=True, text=True,
                               cwd=cwd, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return {"result": "", "error": f"timeout after {TIMEOUT}s", "cost_usd": 0.0, "usage": {}, "model_usage": {}}
    try:
        d = json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"result": "", "error": f"claude exit {p.returncode}, stdout not JSON: {p.stdout[:200]!r} {p.stderr[-200:]!r}",
                "cost_usd": 0.0, "usage": {}, "model_usage": {}}
    return {"result": d.get("result") or "", "error": "" if not d.get("is_error") else str(d.get("result"))[:300],
            "cost_usd": d.get("total_cost_usd") or 0.0, "usage": d.get("usage") or {},
            "model_usage": d.get("modelUsage") or {}, "secs": round((d.get("duration_ms") or 0) / 1000, 1)}


# ── strict parse ────────────────────────────────────────────────────────────

class BadVerdict(ValueError):
    pass


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", G.norm_text(s)).strip().lower()


def parse_verdict(text: str, n_must: int, n_hard: int) -> dict:
    """The judge's JSON checked against the schema of judge_prompt.md; BadVerdict on any deviation.
    One ```json fence around the object is tolerated (and nothing else)."""
    t = text.strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", t, flags=re.S)
    if m:
        t = m.group(1)
    repaired = False
    try:
        d = json.loads(t)
    except json.JSONDecodeError as exc:
        # Opus sometimes closes the root object one brace early and goes on with `,"notes": ...}`
        # (4 times on 2026-11-20). Only that shape is repaired: drop the early brace, and the
        # schema check below still applies to the result.
        head = t[:exc.pos].rstrip()
        if exc.msg == "Extra data" and head.endswith("}") and re.match(r'\s*,\s*"\w+"\s*:', t[exc.pos:]):
            try:
                d, repaired = json.loads(head[:-1] + t[exc.pos:]), True
            except json.JSONDecodeError:
                d = None
        if not repaired:
            raise BadVerdict(f"not JSON: {exc}; around it: {t[max(0, exc.pos - 80):exc.pos + 220]!r}")
    if not isinstance(d, dict):
        raise BadVerdict("not an object")

    def item_list(key: str, n: int) -> list[dict]:
        v = d.get(key)
        if not isinstance(v, list) or len(v) != n:
            raise BadVerdict(f"{key}: expected a list of {n}")
        out = []
        for i, x in enumerate(v, 1):
            if not isinstance(x, dict) or x.get("item") != i:
                raise BadVerdict(f"{key}[{i}]: bad or misnumbered entry")
            if x.get("v") not in (0, 1, None) or isinstance(x.get("v"), bool):
                raise BadVerdict(f"{key}[{i}]: v must be 0, 1 or null")
            if not isinstance(x.get("span", ""), str) or x.get("src", "none") not in ("answer", "trace", "none"):
                raise BadVerdict(f"{key}[{i}]: bad span / src")
            out.append({"item": i, "v": x["v"], "src": x.get("src", "none"), "span": x.get("span", "")})
        return out

    def scalar(key: str, allowed: tuple) -> dict:
        x = d.get(key)
        if not isinstance(x, dict) or x.get("v") not in allowed or isinstance(x.get("v"), bool):
            raise BadVerdict(f"{key}: v must be one of {allowed}")
        out = {"v": x["v"], "why": str(x.get("why", ""))}
        if "span" in x:
            out["span"] = str(x["span"])
        if key == "j6":
            sp = x.get("spans", [])
            if not isinstance(sp, list) or not all(isinstance(s, str) for s in sp):
                raise BadVerdict("j6: spans must be a list of strings")
            out["spans"] = sp
        return out

    return {"j1": item_list("j1", n_must), "j2": item_list("j2", n_hard),
            "j3": scalar("j3", (0, 1, None)), "j4": scalar("j4", (0, 1, None)),
            "j5": scalar("j5", (0, 1, 2, None)), "j6": scalar("j6", (0, 1, 2, None)),
            "notes": str(d.get("notes", "")) + (" [parser: early root brace repaired]" if repaired else "")}


def check_spans(v: dict, answer: str, trace: list[dict]) -> list[str]:
    """Spans (J1/J2/J6) that are not a verbatim part of the answer or of a trace output (whitespace-insensitive).
    Reported, not fatal: a judge that misquotes is a calibration finding."""
    hay = _flat(answer + "\n" + trace_text(trace) + "\n" + "\n".join(G.unwrap(c.get("out", "")) for c in trace or [])
                + "\n" + "\n".join(str(c.get("out", "")).replace("\\n", "\n") for c in trace or []))   # cut {"result": ...} outputs keep a literal \\n
    bad = []
    for x in v["j1"] + v["j2"]:
        if x["span"] and _flat(x["span"]) not in hay:
            bad.append(x["span"])
    for s in v["j6"].get("spans", []) + ([v["j3"]["span"]] if v["j3"].get("span") else []) \
            + ([v["j4"]["span"]] if v["j4"].get("span") else []):
        if s and _flat(s) not in hay:
            bad.append(s)
    return bad


def judge_turn(must: list[str], hard_fail: list[str], history: list[tuple[str, str]], user_text: str, lang: str,
               answer: str, trace: list[dict], persona: str, model: str = JUDGE_MODEL, system: str | None = None) -> dict:
    """One judge call (+ one retry on an invalid reply). Returns {verdict, attempts: [...], cost_usd, ok}."""
    system = system if system is not None else PROMPT_FILE.read_text(encoding="utf-8")
    user = build_input(must, hard_fail, history, user_text, lang, answer, trace, persona)
    attempts, verdict, cost = [], None, 0.0
    for n in (1, 2):
        r = call_claude(user, system, model)
        cost += r["cost_usd"]
        att = {"n": n, "cost_usd": r["cost_usd"], "usage": r["usage"], "model_usage": r["model_usage"],
               "secs": r.get("secs"), "error": r["error"], "raw": r["result"]}
        attempts.append(att)
        if r["error"]:
            att["problem"] = r["error"]
            continue
        try:
            verdict = parse_verdict(r["result"], len(must), len(hard_fail))
            break
        except BadVerdict as exc:
            att["problem"] = str(exc)
    out = {"ok": verdict is not None, "verdict": verdict, "attempts": attempts, "cost_usd": cost}
    if verdict:
        out["bad_spans"] = check_spans(verdict, answer, trace)
    return out


# ── aggregation over the turns of a scenario ────────────────────────────────

def aggregate(results: list[dict], n_must: int, n_hard: int) -> dict:
    """Per-item verdicts over the turns: J1 = satisfied in any turn that decided (1 beats 0 beats null);
    J2 = triggered in any turn (1 beats 0 beats null). J3/J4 = lowest decided turn value; J5/J6 = mean (rounded
    to 0.5) over the decided turns, the per-turn values stay under `turns`."""
    vs = [r["verdict"] for r in results if r.get("verdict")]

    def items(key: str, n: int) -> list[dict]:
        out = []
        for i in range(n):
            cands = [v[key][i] for v in vs]
            dec = [c for c in cands if c["v"] is not None]
            pick = (max(dec, key=lambda c: c["v"]) if dec else (cands[0] if cands else {"item": i + 1, "v": None, "src": "none", "span": ""}))
            out.append(dict(pick, item=i + 1))
        return out

    def scal(key: str, how: str) -> dict:
        vals = [v[key]["v"] for v in vs if v[key]["v"] is not None]
        if not vals:
            return {"v": None, "why": "; ".join(v[key]["why"] for v in vs if v[key]["why"])[:300]}
        val = min(vals) if how == "min" else round(sum(vals) / len(vals) * 2) / 2
        return {"v": int(val) if float(val).is_integer() else val, "why": "; ".join(v[key]["why"] for v in vs if v[key]["why"])[:300]}

    return {"j1": items("j1", n_must), "j2": items("j2", n_hard),
            "j3": scal("j3", "min"), "j4": scal("j4", "min"), "j5": scal("j5", "mean"), "j6": scal("j6", "mean")}


# ── run file ────────────────────────────────────────────────────────────────

def load_persona() -> str:
    try:
        return PERSONA_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""


def judge_record(rec: dict, s: dict, persona: str, model: str, system: str) -> dict:
    """The `judge` block of one graded scenario record (one call per turn)."""
    results, history = [], []
    for t in rec["turns"]:
        r = judge_turn(s["must"], s["hard_fail"], list(history), t.get("user_text", ""), t.get("lang", ""),
                       t.get("answer", ""), t.get("trace") or [], persona, model, system)
        results.append(r)
        history.append((t.get("user_text", ""), t.get("answer", "")))
    block = {"turns": [{"ok": r["ok"], "verdict": r["verdict"], "bad_spans": r.get("bad_spans", []),
                        "attempts": r["attempts"],
                        "cost_usd": r["cost_usd"]} for r in results],
             "cost_usd": sum(r["cost_usd"] for r in results), "ok": all(r["ok"] for r in results)}
    if block["ok"]:
        block.update(aggregate(results, len(s["must"]), len(s["hard_fail"])))
    return block


def judge_meta(model: str, system: str, persona: str, records: list[dict]) -> dict:
    blocks = [r["judge"] for r in records if r.get("judge")]
    atts = [a for b in blocks for t in b["turns"] for a in t["attempts"]]
    ver = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    return {"model": model, "prompt_file": "tests/bot_eval/judge_prompt.md", "prompt_sha256": sha256(system),
            "persona_sha256": sha256(persona) if persona else "", "cli_version": ver, "calls": len(atts),
            "retries": sum(1 for a in atts if a["n"] == 2),
            "cli_cost_usd": sum(a["cost_usd"] for a in atts),
            "tokens": {k: sum((a["usage"] or {}).get(k, 0) for a in atts)
                       for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", help="run file written by run.py (its .graded.json is read, or made)")
    ap.add_argument("--only", default="", help="comma-separated scenario ids")
    ap.add_argument("--force", action="store_true", help="judge again scenarios already judged with this prompt")
    ap.add_argument("--dry-run", action="store_true", help="print the judge input of every turn, call nothing")
    ap.add_argument("--model", default=JUDGE_MODEL)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    path = Path(args.run)
    if path.name.endswith(".graded.json"):
        graded_path = path
    else:
        graded_path = path.with_name(path.stem + ".graded.json")
    scenarios = G.load_scenarios()
    if graded_path.is_file():
        doc = json.loads(graded_path.read_text(encoding="utf-8"))
    else:
        doc = G.grade_run(json.loads(path.read_text(encoding="utf-8")), scenarios)
    system = PROMPT_FILE.read_text(encoding="utf-8")
    persona = load_persona()
    only = {x for x in args.only.split(",") if x}
    psha = sha256(system)
    for rec in doc["scenarios"]:
        if only and rec["id"] not in only:
            continue
        s = scenarios[rec["id"]]
        if args.dry_run:
            hist = []
            for i, t in enumerate(rec["turns"], 1):
                print(f"===== {rec['id']} turn {i} =====")
                print(build_input(s["must"], s["hard_fail"], hist, t.get("user_text", ""), t.get("lang", ""),
                                  t.get("answer", ""), t.get("trace") or [], persona))
                hist.append((t.get("user_text", ""), t.get("answer", "")))
            continue
        old = rec.get("judge")
        if old and old.get("ok") and not args.force and doc.get("judge_meta", {}).get("prompt_sha256") == psha:
            print(f"{rec['id']}: already judged with this prompt (--force to redo)")
            continue
        print(f"{rec['id']}: judging {len(rec['turns'])} turn(s) with {args.model} ...", flush=True)
        rec["judge"] = judge_record(rec, s, persona, args.model, system)
        j = rec["judge"]
        print(f"{rec['id']}: {'ok' if j['ok'] else 'JUDGE OUTPUT INVALID'}, cost ${j['cost_usd']:.4f}", flush=True)
        for t in j["turns"]:
            for a in t["attempts"]:
                if a.get("problem"):
                    print(f"  attempt {a['n']}: {a['problem']}")
        if not j["ok"]:
            doc["judge_meta"] = judge_meta(args.model, system, persona, doc["scenarios"])
            graded_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print("stopping: invalid judge output after one retry (nothing more is called)")
            return 1
    if args.dry_run:
        return 0
    doc["judge_meta"] = judge_meta(args.model, system, persona, doc["scenarios"])
    graded_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(G.summary(doc))
    if not args.quiet:
        for rec in doc["scenarios"]:
            j = rec.get("judge")
            if not j or not j.get("ok"):
                continue
            print(f"  {rec['id']} J3={j['j3']['v']} J4={j['j4']['v']} J5={j['j5']['v']} J6={j['j6']['v']}"
                  + (f" · spans not verbatim: {sum(len(t['bad_spans']) for t in j['turns'])}"
                     if any(t["bad_spans"] for t in j["turns"]) else ""))
    print(f"graded file: {graded_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
