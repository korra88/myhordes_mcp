"""Calibration of the bot-eval judge (docs/bot-eval-plan.md 4.2): the maintainer hand-grades 10 answers, this
script compares them with the judge's verdicts.

Files, all private, in towns/_eval/calibration/:
    items.json   the 10 answers (id K01..K10, conversation, tool trace, `must` / `hard_fail` lists)
    judge.json   the judge's stored verdicts for them (written by `--judge`)
    sheet.md     the hand-grading sheet (written by `--write-sheet`): NO judge verdict, NO deterministic grade, no model

    .venv/bin/python tests/bot_eval/calibrate.py                    compare sheet.md with judge.json   (make bot-eval-calibrate)
    .venv/bin/python tests/bot_eval/calibrate.py --sheet FILE       compare another (e.g. a filled copy)
    .venv/bin/python tests/bot_eval/calibrate.py --judge [--only K01,K02] [--redo]   CALLS OPUS: judge the items, store judge.json
    .venv/bin/python tests/bot_eval/calibrate.py --write-sheet [--force-sheet]       make an empty sheet (never overwrites a sheet unless forced)

An item agrees when every J1 and every J2 value of the hand grade equals the judge's (`?` / null match each other).
J6 is compared and printed but is not part of the agreement (the plan's target: J1/J2 agree on >= 9/10 items).
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tests" / "bot_eval"))
import judge as J   # noqa: E402

DIR = ROOT / "towns" / "_eval" / "calibration"
ITEMS, JUDGE, SHEET = DIR / "items.json", DIR / "judge.json", DIR / "sheet.md"


def load_items() -> list[dict]:
    return json.loads(ITEMS.read_text(encoding="utf-8"))["items"]


# ── the sheet ───────────────────────────────────────────────────────────────

HEADER = """# Judge calibration: hand-grading sheet

Grade each answer yourself, **before** looking at any judge output. Write inside the brackets:

- `must N: [1]` the MUST item is satisfied, `[0]` it is not, `[?]` you cannot decide from what is shown.
- `hard_fail N: [1]` the failure HAPPENED (bad), `[0]` it did not, `[?]` cannot decide.
- `J6: [0|1|2]` fit for Discord: 2 = direct, no narration, one language, no table outside a code block, no tool or
  parameter names, persona audible and numbers easy to find; 1 = one minor defect (a bit long, persona faint, a number
  harder to find); 0 = a serious defect (tool name shown, mixed languages, a table that will not render, narration,
  several defects, persona hiding the numbers).

The tool outputs of each answer are in `towns/_eval/calibration/items.json` (same id); old-bench outputs were cut to
1500 characters by that bench. Judge a MUST item about "as the tool prints it" against that file. Keep the brackets
and the labels exactly as they are: `calibrate.py` reads them.

Persona the answers should carry: `persona.md` (the Town Chronicler). Reply rules: `prompts/discord.md`.
"""


def write_sheet(items: list[dict]) -> str:
    out = [HEADER]
    for it in items:
        out.append(f"\n---\n\n## {it['id']}\n")
        hist = it["turns"]
        for n, t in enumerate(hist, 1):
            suffix = f" (turn {n}/{len(hist)}, language {t.get('lang') or '?'})" if len(hist) > 1 else f" (language {t.get('lang') or '?'})"
            out.append(f"**Question{suffix}:** {t['user_text']}\n")
            out.append("**Answer:**\n\n~~~~text\n" + t["answer"].rstrip() + "\n~~~~\n")
        calls = [f"`{c['tool']}({json.dumps(c.get('args') or {}, ensure_ascii=False)})`" for t in hist for c in t.get("trace", [])]
        out.append("**Calls:** " + (", ".join(calls) if calls else "none") + f" (full outputs: items.json, {it['id']})\n")
        out.append("**MUST:**\n")
        out += [f"{i}. {m}" for i, m in enumerate(it["must"], 1)]
        out.append("\n**HARD_FAIL (1 = it happened):**\n")
        out += [f"{i}. {m}" for i, m in enumerate(it["hard_fail"], 1)]
        out.append("\n**Your grades:**\n")
        out += [f"- must {i}: [ ]" for i in range(1, len(it["must"]) + 1)]
        out += [f"- hard_fail {i}: [ ]" for i in range(1, len(it["hard_fail"]) + 1)]
        out.append("- J6: [ ]")
    return "\n".join(out) + "\n"


def parse_sheet(text: str, items: list[dict]) -> tuple[dict, list[str]]:
    """({id: {"must": [v..], "hard_fail": [v..], "j6": v}}, problems). v is 0, 1, None ('?') or "" (not filled)."""
    sections = re.split(r"^## (K\d+)\s*$", text, flags=re.M)
    by_id = {sections[i]: sections[i + 1] for i in range(1, len(sections) - 1, 2)}
    grades, problems = {}, []

    def val(s: str):
        s = s.strip()
        if s in ("0", "1", "2"):
            return int(s)
        return None if s == "?" else ""

    for it in items:
        body = by_id.get(it["id"])
        if body is None:
            problems.append(f"{it['id']}: section missing")
            continue
        g = {"must": [], "hard_fail": [], "j6": ""}
        for key, n in (("must", len(it["must"])), ("hard_fail", len(it["hard_fail"]))):
            for i in range(1, n + 1):
                m = re.search(rf"^- {key} {i}: \[([^\]]*)\]", body, flags=re.M)
                if not m:
                    problems.append(f"{it['id']}: line '{key} {i}' missing")
                    g[key].append("")
                    continue
                v = val(m.group(1))
                if v not in (0, 1, None):
                    problems.append(f"{it['id']}: {key} {i} is not filled with 1, 0 or ? ('{m.group(1).strip()}')")
                    v = ""
                g[key].append(v)
        m = re.search(r"^- J6: \[([^\]]*)\]", body, flags=re.M)
        g["j6"] = val(m.group(1)) if m else ""
        if g["j6"] not in (0, 1, 2, None):
            problems.append(f"{it['id']}: J6 is not filled with 0, 1, 2 or ?")
        grades[it["id"]] = g
    return grades, problems


# ── judge ───────────────────────────────────────────────────────────────────

def run_judge(items: list[dict], only: set[str], redo: bool) -> int:
    stored = json.loads(JUDGE.read_text(encoding="utf-8")) if JUDGE.is_file() else {"meta": {}, "items": {}}
    system = J.PROMPT_FILE.read_text(encoding="utf-8")
    persona = J.load_persona()
    psha = J.sha256(system)
    total, calls = 0.0, 0
    for it in items:
        if only and it["id"] not in only:
            continue
        old = stored["items"].get(it["id"])
        if old and old.get("ok") and not redo and stored.get("meta", {}).get("prompt_sha256") == psha:
            print(f"{it['id']}: already judged with this prompt (--redo to call again)")
            continue
        rec = {"turns": it["turns"]}
        block = J.judge_record(rec, {"must": it["must"], "hard_fail": it["hard_fail"]}, persona, J.JUDGE_MODEL, system)
        stored["items"][it["id"]] = block
        n = sum(len(t["attempts"]) for t in block["turns"])
        calls += n
        total += block["cost_usd"]
        costs = ", ".join(f"${a['cost_usd']:.4f}" for t in block["turns"] for a in t["attempts"])
        print(f"{it['id']}: {'ok' if block['ok'] else 'INVALID'} · {n} call(s): {costs}", flush=True)
        for t in block["turns"]:
            for a in t["attempts"]:
                if a.get("problem"):
                    print(f"   attempt {a['n']}: {a['problem']}")
        recs = [{"judge": b} for b in stored["items"].values()]
        stored["meta"] = J.judge_meta(J.JUDGE_MODEL, system, persona, recs)
        JUDGE.write_text(json.dumps(stored, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        if not block["ok"]:
            print("stopping: invalid judge output after one retry")
            return 1
    print(f"this run: {calls} call(s), CLI cost ${total:.4f}; stored in {JUDGE}")
    return 0


# ── comparison ──────────────────────────────────────────────────────────────

def compare(items: list[dict], grades: dict, stored: dict) -> tuple[int, list[str]]:
    lines, agree = [], 0
    detail = []
    for it in items:
        g, jb = grades.get(it["id"]), stored["items"].get(it["id"])
        if g is None or jb is None or not jb.get("ok"):
            lines.append(f"{it['id']}: no judge verdict or no hand grade")
            continue
        jv = {"j1": [x["v"] for x in jb["j1"]], "j2": [x["v"] for x in jb["j2"]]}
        mism = []
        for key, jk in (("must", "j1"), ("hard_fail", "j2")):
            for i, (h, v) in enumerate(zip(g[key], jv[jk]), 1):
                if h != v:
                    mism.append((("J1" if key == "must" else "J2"), i, h, v, jb[jk][i - 1]))
        ok = not mism
        agree += ok
        j1m = sum(1 for h, v in zip(g["must"], jv["j1"]) if h == v)
        j2m = sum(1 for h, v in zip(g["hard_fail"], jv["j2"]) if h == v)
        j6 = f"J6 hand {g['j6'] if g['j6'] != '' else '-'} judge {jb['j6']['v']}"
        lines.append(f"{it['id']}: {'AGREE   ' if ok else 'DISAGREE'} J1 {j1m}/{len(jv['j1'])} J2 {j2m}/{len(jv['j2'])} · {j6}")
        for k, i, h, v, jx in mism:
            lst = it["must"] if k == "J1" else it["hard_fail"]
            sh = lambda x: "?" if x is None else x
            detail.append(f"{it['id']} {k} item {i} ({lst[i - 1][:90]}): hand {sh(h)} vs judge {sh(v)}"
                          f" [{jx.get('src', 'none')}] span: {jx.get('span') or '(none)'!r}")
    return agree, lines + [""] + detail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", default=str(SHEET), help="the hand-graded sheet to read")
    ap.add_argument("--judge", action="store_true", help="call the judge on the items and store judge.json (costs)")
    ap.add_argument("--only", default="", help="with --judge: comma-separated item ids")
    ap.add_argument("--redo", action="store_true", help="with --judge: call again for items already judged")
    ap.add_argument("--write-sheet", action="store_true")
    ap.add_argument("--force-sheet", action="store_true", help="with --write-sheet: overwrite an existing sheet (loses hand grades)")
    ap.add_argument("--allow-partial", action="store_true", help="compare the items that are filled, skip the others")
    args = ap.parse_args()
    items = load_items()
    if args.judge:
        return run_judge(items, {x for x in args.only.split(",") if x}, args.redo)
    if args.write_sheet:
        if SHEET.exists() and not args.force_sheet:
            sys.exit(f"{SHEET} exists; --force-sheet overwrites it (hand grades would be lost)")
        SHEET.write_text(write_sheet(items), encoding="utf-8")
        print(f"wrote {SHEET}")
        return 0
    sheet = Path(args.sheet)
    if not sheet.is_file() or not JUDGE.is_file():
        sys.exit(f"need {sheet} and {JUDGE}")
    grades, problems = parse_sheet(sheet.read_text(encoding="utf-8"), items)
    unfilled = [it["id"] for it in items if it["id"] in grades
                and any(v == "" for v in grades[it["id"]]["must"] + grades[it["id"]]["hard_fail"])]
    if problems and not args.allow_partial:
        print("sheet problems:\n  " + "\n  ".join(problems))
        print(f"{len(unfilled)} item(s) not completely filled; fill them or use --allow-partial")
        return 2
    items = [it for it in items if it["id"] not in unfilled]
    stored = json.loads(JUDGE.read_text(encoding="utf-8"))
    agree, lines = compare(items, grades, stored)
    print("\n".join(lines))
    print(f"\nJ1/J2 agree on {agree}/{len(items)} items" + (f" ({len(unfilled)} skipped, not filled)" if unfilled else "")
          + " · target >= 9/10")
    return 0


if __name__ == "__main__":
    sys.exit(main())
