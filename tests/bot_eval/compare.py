"""Compare two graded bot-eval runs, scenario by scenario (docs/bot-eval-plan.md 6.3 steps 4-5).
No model call, no network: it only reads the two `<run>.graded.json` files.

    .venv/bin/python tests/bot_eval/compare.py A B [--only E1,K1] [--target E1,E2] [--strict]
or `make bot-eval-compare A=<run|graded file> B=<run|graded file> [ONLY=E1,K1] [TARGET=E1,E2]`.

A = before, B = after. Each argument is a graded file or the run file whose sibling `.graded.json`
holds the grades (an error says how to create it when it is missing). A scenario may appear several
times in one file (`REPEAT>1`, field `repeat`); the figures are then per scenario over its repeats:
  HF      hard fails / repeats (a failed hard check, or a judge J2 hit; grade.py)
  score   mean of the 4.3 score over the judged repeats (a hard fail counts 0); "-" when not judged
  calls   mean game-tool calls; chars mean answer length (all turns); cost mean CLI-reported USD
Output: a header (what differs between the two runs), then regressions first, improvements,
unchanged, and the scenarios present on one side only; then the verdict of 6.3 step 5:
  1  no scenario has a new hard fail (its hard-fail rate is higher in B than in A)
  2  every TARGET scenario passes (no hard fail) in at least 2/3 of its repeats in B
  3  no scenario's mean score drops by more than 0.2
Each rule prints PASS or FAIL with the scenarios that broke it. `--strict` exits 1 on a FAIL.
n = 1 per scenario is a direction, not a rate; the verdict says so.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grade as G   # noqa: E402

SCORE_DROP = 0.2            # rule 3, strict: a drop of exactly 0.2 is accepted
TARGET_PASS_RATE = 2 / 3    # rule 2


# ── loading ─────────────────────────────────────────────────────────────────

def graded_path(arg: str) -> Path:
    """The graded file for a run file or a graded file; SystemExit saying what to do when absent."""
    p = Path(arg)
    if p.name.endswith(".graded.json"):
        if not p.is_file():
            raise SystemExit(f"error: {arg}: no such file")
        return p
    sibling = p.with_name(p.stem + ".graded.json")
    if not sibling.is_file():
        if not p.is_file():
            raise SystemExit(f"error: {arg}: no such file")
        raise SystemExit(f"error: {sibling} is missing (the run file alone has no grades); "
                         f"create it with: make bot-eval-grade RUN={arg}  (then make bot-eval-judge RUN={arg} for the scores)")
    return sibling


def load(arg: str) -> dict:
    import json
    path = graded_path(arg)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not (isinstance(doc, dict) and "scenarios" in doc and "meta" in doc):
        raise SystemExit(f"error: {path}: not a bot-eval run file")
    if not all("grades" in r for r in doc["scenarios"]):
        raise SystemExit(f"error: {path}: a scenario has no `grades` (run make bot-eval-grade)")
    doc["_path"] = str(path)
    return doc


# ── per-record figures ──────────────────────────────────────────────────────

def hard_failed(rec: dict) -> bool:
    return bool(rec["grades"]["hard_failed"] or G.judge_hits(rec))


def game_calls(rec: dict) -> int:
    return sum(1 for t in rec["turns"] for c in t.get("trace") or [] if G.is_game_tool(c["tool"]))


def answer_chars(rec: dict) -> int:
    return sum(len(t.get("answer") or "") for t in rec["turns"])


def cost_usd(rec: dict) -> float | None:
    vals = [t.get("cli_cost_usd") for t in rec["turns"]]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return sum(vals) if vals else None


def out_tokens(rec: dict) -> int | None:
    vals = [(t.get("usage") or {}).get("output_tokens") for t in rec["turns"]]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return sum(vals) if vals else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def stats(recs: list[dict]) -> dict:
    """Figures of one scenario over its repeats."""
    scores = [G.score_of(r) for r in recs]
    hf = [hard_failed(r) for r in recs]
    return {"n": len(recs), "hf": sum(hf), "pass": len(recs) - sum(hf),
            "judged": sum(1 for s in scores if s is not None), "score": mean(scores),
            "calls": mean([game_calls(r) for r in recs]), "chars": mean([answer_chars(r) for r in recs]),
            "cost": mean([cost_usd(r) for r in recs]), "tokens": mean([out_tokens(r) for r in recs])}


def by_id(doc: dict) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for r in doc["scenarios"]:
        groups.setdefault(r["id"], []).append(r)
    return {i: stats(rs) for i, rs in groups.items()}


# ── comparison ──────────────────────────────────────────────────────────────

def classify(a: dict, b: dict) -> tuple[str, list[str]]:
    """('regression' | 'improvement' | 'unchanged', reasons) for one scenario present on both sides."""
    ra, rb = a["hf"] / a["n"], b["hf"] / b["n"]
    reasons, bad, good = [], False, False
    if rb > ra:
        bad = True
        reasons.append("new hard fail" if a["hf"] == 0 else "more hard fails")
    elif rb < ra:
        good = True
        reasons.append("hard fail cleared" if b["hf"] == 0 else "fewer hard fails")
    if a["score"] is not None and b["score"] is not None:
        d = round(b["score"] - a["score"], 9)
        if d < -SCORE_DROP:
            bad = True
            reasons.append(f"score dropped {-d:.2f}")
        elif d > SCORE_DROP:
            good = True
            reasons.append(f"score up {d:.2f}")
    elif a["score"] is None or b["score"] is None:
        reasons.append("score not comparable (a side is not judged)")
    return ("regression" if bad else "improvement" if good else "unchanged"), reasons


def severity(a: dict, b: dict) -> tuple:
    new_hf = b["hf"] / b["n"] - a["hf"] / a["n"]
    drop = (a["score"] - b["score"]) if a["score"] is not None and b["score"] is not None else 0.0
    return (-new_hf, -drop)


def compare(da: dict, db: dict, only: list[str] | None = None, target: list[str] | None = None) -> dict:
    """The structured result (printed by `report`)."""
    sa, sb = by_id(da), by_id(db)
    only = only or []
    ids_a = [i for i in sa if not only or i in only]
    ids_b = [i for i in sb if not only or i in only]
    both = [i for i in ids_a if i in sb and i in ids_b]
    rows = {"regression": [], "improvement": [], "unchanged": []}
    for i in both:
        kind, why = classify(sa[i], sb[i])
        rows[kind].append((i, sa[i], sb[i], why))
    rows["regression"].sort(key=lambda r: severity(r[1], r[2]))
    rows["improvement"].sort(key=lambda r: severity(r[1], r[2]), reverse=True)
    only_a = [i for i in ids_a if i not in sb]
    only_b = [i for i in ids_b if i not in sa]
    rules = verdict(sa, sb, both, target or [], only_a, only_b)
    return {"rows": rows, "only_a": {i: sa[i] for i in only_a}, "only_b": {i: sb[i] for i in only_b},
            "rules": rules, "sa": sa, "sb": sb, "target": target or [], "both": both}


def verdict(sa, sb, both, target, only_a, only_b) -> list[dict]:
    """The three rules of 6.3 step 5: [{n, title, ok, details}]."""
    r1 = []
    for i in both:
        a, b = sa[i], sb[i]
        if b["hf"] / b["n"] > a["hf"] / a["n"]:
            r1.append(f"{i} hard fails {a['hf']}/{a['n']} -> {b['hf']}/{b['n']}")
    r2 = []
    for i in target:
        if i not in sb:
            r2.append(f"{i} is not in B")
        elif sb[i]["pass"] / sb[i]["n"] < TARGET_PASS_RATE - 1e-9:
            r2.append(f"{i} passes {sb[i]['pass']}/{sb[i]['n']} (needs at least 2/3)")
    r3 = []
    for i in both:
        a, b = sa[i], sb[i]
        if a["score"] is not None and b["score"] is not None and round(a["score"] - b["score"], 9) > SCORE_DROP:
            r3.append(f"{i} score {a['score']:.2f} -> {b['score']:.2f} (-{a['score'] - b['score']:.2f})")
    missing = [f"{i} (only in A)" for i in only_a] + [f"{i} (only in B)" for i in only_b]
    return [
        {"n": 1, "title": "no new hard fail anywhere", "ok": not r1, "details": r1},
        {"n": 2, "title": ("targeted scenarios " + ",".join(target) + " pass at least 2/3 of their repeats")
                          if target else "targeted scenarios pass at least 2/3 of their repeats (no TARGET given: not checked)",
         "ok": not r2, "details": r2, "skipped": not target},
        {"n": 3, "title": f"no scenario's mean score drops by more than {SCORE_DROP}", "ok": not r3, "details": r3},
        {"n": 0, "title": "scenarios on one side only (not judged by the rules)", "ok": True, "details": missing, "info": True},
    ]


# ── printing ────────────────────────────────────────────────────────────────

def short(h, n=12):
    return (h or "-")[:n]


def fnum(x, fmt):
    return "-" if x is None else format(x, fmt)


def header(da: dict, db: dict) -> list[str]:
    ma, mb = da["meta"], db["meta"]
    jma, jmb = da.get("judge_meta") or {}, db.get("judge_meta") or {}

    def sha(m):
        d = len(m.get("git_dirty_files") or [])
        return f"{short(m.get('git_sha'), 7)}" + (f"+dirty({d})" if m.get("git_dirty") else "")

    def prompts(m):
        p = m.get("system_prompt_sha256") or {}
        return " ".join(f"{t}={short(p.get(t))}" for t in ("public", "trusted") if t in p) or "-"

    fields = [
        ("file", Path(da["_path"]).name.removesuffix(".graded.json"), Path(db["_path"]).name.removesuffix(".graded.json")),
        ("label / date", f"{ma.get('label')} {str(ma.get('date', ''))[:16]}", f"{mb.get('label')} {str(mb.get('date', ''))[:16]}"),
        ("model", ma.get("model_requested"), mb.get("model_requested")),
        ("suite / repeat", f"{ma.get('suite')} x{ma.get('repeat')}", f"{mb.get('suite')} x{mb.get('repeat')}"),
        ("git sha", sha(ma), sha(mb)),
        ("system prompt", prompts(ma), prompts(mb)),
        ("rubric hash", short(jma.get("prompt_sha256")), short(jmb.get("prompt_sha256"))),
        ("claude CLI", ma.get("cli_version"), mb.get("cli_version")),
        ("wiki hash", short(ma.get("wiki_processed_sha256")), short(mb.get("wiki_processed_sha256"))),
    ]
    out = [f"{'':<15}{'A (before)':<50}{'B (after)'}"]
    for name, a, b in fields:
        mark = "" if a == b else "  <- differs"
        out.append(f"{name:<15}{str(a):<50}{str(b)}{mark}")
    notes = []
    if ma.get("model_requested") != mb.get("model_requested"):
        notes.append("the models differ: this compares two models, not a change to prompts / tools (costs are the CLI figures, not trusted for Haiku 5.5)")
    if jma.get("prompt_sha256") != jmb.get("prompt_sha256"):
        notes.append("the judge rubrics differ: scores are not comparable")
    sa, sb = ma.get("scenario_sha256") or {}, mb.get("scenario_sha256") or {}
    changed = sorted(i for i in sa if i in sb and sa[i] != sb[i])
    if changed:
        notes.append("scenario definition changed between the runs: " + ", ".join(changed))
    fa, fb = ma.get("fixture_sha256") or {}, mb.get("fixture_sha256") or {}
    fchanged = sorted(i for i in fa if i in fb and fa[i] != fb[i])
    if fchanged:
        notes.append("fixture changed between the runs: " + ", ".join(fchanged))
    ta, tb = ma.get("allowed_tools") or {}, mb.get("allowed_tools") or {}
    if ta != tb or (ma.get("extra_allowed") or []) != (mb.get("extra_allowed") or []):
        notes.append("the allowed tool lists differ")
    return out + [f"NOTE: {n}" for n in notes]


def row_line(i: str, a: dict, b: dict, why: list[str] | None = None) -> str:
    hf = f"{a['hf']}/{a['n']}>{b['hf']}/{b['n']}"
    sc = f"{fnum(a['score'], '.2f')}>{fnum(b['score'], '.2f')}"
    calls = f"{fnum(a['calls'], '.1f')}>{fnum(b['calls'], '.1f')}"
    chars = f"{fnum(a['chars'], '.0f')}>{fnum(b['chars'], '.0f')}"
    cost = f"{fnum(a['cost'], '.4f')}>{fnum(b['cost'], '.4f')}"
    line = f"{i:<6}{hf:<10}{sc:<13}{calls:<12}{chars:<14}{cost:<17}"
    return line + ("; ".join(why) if why else "")


def one_side(i: str, s: dict) -> str:
    return (f"{i:<6}n={s['n']} hf {s['hf']}/{s['n']} score {fnum(s['score'], '.2f')} calls {fnum(s['calls'], '.1f')} "
            f"chars {fnum(s['chars'], '.0f')} cost {fnum(s['cost'], '.4f')}")


def report(da: dict, db: dict, res: dict) -> str:
    out = header(da, db)
    cols = f"{'ID':<6}{'HF A>B':<10}{'score A>B':<13}{'calls A>B':<12}{'chars A>B':<14}{'cost A>B (USD)':<17}why"
    for title, key in (("Regressions", "regression"), ("Improvements", "improvement"), ("Unchanged", "unchanged")):
        rows = res["rows"][key]
        out += ["", f"{title} ({len(rows)})"]
        if rows:
            out.append(cols)
            out += [row_line(i, a, b, why) for i, a, b, why in rows]
    for title, d in (("Only in A", res["only_a"]), ("Only in B", res["only_b"])):
        out += ["", f"{title} ({len(d)})"]
        out += [one_side(i, s) for i, s in d.items()]
    allb = [res["sb"][i] for i in res["both"]]
    alla = [res["sa"][i] for i in res["both"]]
    if allb:
        out += ["", f"Over the {len(allb)} common scenario(s): hard fails {sum(s['hf'] for s in alla)}/{sum(s['n'] for s in alla)}"
                    f" > {sum(s['hf'] for s in allb)}/{sum(s['n'] for s in allb)}"
                    f" · mean score {fnum(mean([s['score'] for s in alla]), '.2f')} > {fnum(mean([s['score'] for s in allb]), '.2f')}"
                    f" · mean calls {fnum(mean([s['calls'] for s in alla]), '.1f')} > {fnum(mean([s['calls'] for s in allb]), '.1f')}"
                    f" · mean answer chars {fnum(mean([s['chars'] for s in alla]), '.0f')} > {fnum(mean([s['chars'] for s in allb]), '.0f')}"
                    f" · cost per scenario {fnum(mean([s['cost'] for s in alla]), '.4f')} > {fnum(mean([s['cost'] for s in allb]), '.4f')}"
                    f" · output tokens {fnum(mean([s['tokens'] for s in alla]), '.0f')} > {fnum(mean([s['tokens'] for s in allb]), '.0f')}"]
    out += ["", "Acceptance (docs/bot-eval-plan.md 6.3 step 5)"]
    accepted = True
    for r in res["rules"]:
        if r.get("info"):
            continue
        if r.get("skipped"):
            out.append(f"  rule {r['n']}  SKIP  {r['title']}")
            continue
        accepted &= r["ok"]
        out.append(f"  rule {r['n']}  {'PASS' if r['ok'] else 'FAIL'}  {r['title']}")
        out += [f"          {d}" for d in r["details"]]
    judged = all(s["judged"] == s["n"] for s in list(res["sa"].values()) + list(res["sb"].values()))
    small = [i for i in res["both"] if min(res["sa"][i]["n"], res["sb"][i]["n"]) < 3]
    out.append(f"  => {'ACCEPT' if accepted else 'REJECT'}"
               + ("" if judged else " (some scenarios are not judged: scores and J2 are missing, rule 3 is partial)"))
    if small:
        out.append(f"  note: n < 3 repeats for {len(small)} common scenario(s): a direction, not a rate "
                   "(REPEAT=3 on the targeted ones, docs/bot-eval-plan.md 6.3 step 3)")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", metavar="A", help="run file or graded file, before the change")
    ap.add_argument("b", metavar="B", help="run file or graded file, after the change")
    ap.add_argument("--only", default="", help="comma-separated scenario ids to compare")
    ap.add_argument("--target", default="", help="comma-separated targeted scenario ids (rule 2)")
    ap.add_argument("--strict", action="store_true", help="exit 1 when the verdict is REJECT")
    args = ap.parse_args()
    da, db = load(args.a), load(args.b)
    only = [x for x in args.only.split(",") if x]
    target = [x for x in args.target.split(",") if x]
    res = compare(da, db, only, target)
    print(report(da, db, res))
    return 1 if args.strict and not all(r["ok"] for r in res["rules"]) else 0


if __name__ == "__main__":
    sys.exit(main())
