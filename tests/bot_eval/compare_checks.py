"""Plain-assert checks of tests/bot_eval/compare.py (no pytest, no model call, no network):

    .venv/bin/python tests/bot_eval/compare_checks.py        (make bot-eval-compare-checks)

Synthetic graded documents only, with invented scenario ids: hard-fail and score arithmetic over
repeats, the three acceptance rules, ordering (regressions first), one-sided scenarios, the header,
and the file handling (a run file's sibling graded file, a missing one, --strict exit code).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare as C   # noqa: E402

ok = 0


def check(cond, msg=""):
    global ok
    assert cond, msg
    ok += 1


def rec(sid, hard=False, score=1.0, calls=1, chars=100, cost=0.1, repeat=1, judged=True, j2=False):
    """One graded scenario record whose 4.3 score is `score` (0.5 x det rate + 0.5 x J1 mean, or 0 on a hard fail):
    J1 is all satisfied, so det rate = 2 x score - 1 (score must be in [0.5, 1])."""
    det = round(2 * score - 1, 6)
    r = {"id": sid, "repeat": repeat, "fixture": "x", "tier": "public", "context": "thread",
         "grades": {"hard_failed": ["D3"] if hard else [], "det_passed": int(round(det * 1000)), "det_applicable": 1000},
         "turns": [{"answer": "a" * chars, "cli_cost_usd": cost, "usage": {"output_tokens": 50},
                    "trace": [{"tool": "get_town_overview", "args": {}, "out": ""} for _ in range(calls)]
                             + [{"tool": "ToolSearch", "args": {}, "out": ""}]}]}
    if judged:
        r["judge"] = {"j1": [{"item": 1, "v": 1}], "j2": [{"item": 1, "v": 1 if j2 else 0}]}
    return r


def doc(*recs, label="x", model="claude-sonnet-5-5", sha="a" * 40, dirty=False, prompt="p" * 64, rubric="r" * 64,
        scen=None):
    return {"meta": {"label": label, "date": "2026-11-20T10:00:00", "suite": "core", "repeat": 1, "git_sha": sha,
                     "git_dirty": dirty, "git_dirty_files": ["M x"] if dirty else [], "model_requested": model,
                     "cli_version": "1", "system_prompt_sha256": {"public": prompt, "trusted": prompt},
                     "wiki_processed_sha256": "w", "scenario_sha256": scen or {}, "fixture_sha256": {}},
            "judge_meta": {"prompt_sha256": rubric}, "scenarios": list(recs), "_path": f"/tmp/{label}.graded.json"}


def run(a, b, only=None, target=None):
    return C.compare(a, b, only, target)


def rule(res, n):
    return next(r for r in res["rules"] if r["n"] == n)


# ── per-scenario figures over repeats ───────────────────────────────────────
s = C.stats([rec("T", hard=True, calls=2, chars=100, cost=0.1), rec("T", score=1.0, calls=4, chars=300, cost=0.3),
             rec("T", score=0.8, calls=3, chars=200, cost=0.2)])
check(s["n"] == 3 and s["hf"] == 1 and s["pass"] == 2, s)
check(abs(s["score"] - (0 + 1.0 + 0.8) / 3) < 1e-9, s)                      # a hard fail counts 0 in the mean
check(s["calls"] == 3 and s["chars"] == 200 and abs(s["cost"] - 0.2) < 1e-9, s)   # ToolSearch is not a game call
check(s["tokens"] == 50 and s["judged"] == 3, s)
check(C.stats([rec("T", judged=False)])["score"] is None, "unjudged -> no score")
check(C.stats([rec("T", judged=True, j2=True)])["hf"] == 1, "a J2 hit is a hard fail")
check(C.stats([rec("T", cost=None)])["cost"] is None)

# ── classification ──────────────────────────────────────────────────────────
def kind(a, b):
    return C.classify(C.stats(a), C.stats(b))


check(kind([rec("T")], [rec("T", hard=True)])[0] == "regression" and "new hard fail" in kind([rec("T")], [rec("T", hard=True)])[1])
check(kind([rec("T", hard=True)], [rec("T")])[0] == "improvement")
check(kind([rec("T", score=1.0)], [rec("T", score=0.78)])[0] == "regression")           # drop 0.22
check(kind([rec("T", score=1.0)], [rec("T", score=0.8)])[0] == "unchanged")             # exactly 0.2 is accepted
check(kind([rec("T", score=0.7)], [rec("T", score=1.0)])[0] == "improvement")
check(kind([rec("T", hard=True)], [rec("T", hard=True)])[0] == "unchanged")
rep = lambda *flags: [rec("T", hard=f, repeat=i + 1) for i, f in enumerate(flags)]
check(kind(rep(True, False, False), rep(False, False, False))[0] == "improvement")
check(kind(rep(True, False, False), rep(True, True, False))[1][0] == "more hard fails")
check(kind(rep(True, False, False), rep(True, False, False))[0] == "unchanged")
k, why = kind([rec("T", judged=False)], [rec("T")])
check(k == "unchanged" and any("not comparable" in w for w in why), (k, why))             # no crash without a judge

# ── the three rules ─────────────────────────────────────────────────────────
a = doc(*rep(False, False, False), rec("U"), rec("V", score=0.9))
b = doc(*rep(False, True, False), rec("U"), rec("V", score=0.9))
r = run(a, b, target=["T"])
check(not rule(r, 1)["ok"] and "T hard fails 0/3 -> 1/3" in rule(r, 1)["details"][0], rule(r, 1))
check(rule(r, 2)["ok"], "2 of 3 repeats pass: target accepted")
b2 = doc(*rep(True, True, False), rec("U"), rec("V", score=0.9))
r = run(a, b2, target=["T"])
check(not rule(r, 2)["ok"] and "T passes 1/3" in rule(r, 2)["details"][0], rule(r, 2))
check(not run(a, doc(rec("U")), target=["T"])["rules"][1]["ok"], "target missing in B")
check(rule(run(a, b), 2)["skipped"], "no TARGET: skipped")
# a hard fail already in A and not worse in B is not new
a3, b3 = doc(*rep(True, False, False)), doc(*rep(True, False, False))
check(rule(run(a3, b3), 1)["ok"])
check(not rule(run(doc(rec("T", score=1.0)), doc(rec("T", score=0.7))), 3)["ok"])
check(rule(run(doc(rec("T", score=1.0)), doc(rec("T", score=0.8))), 3)["ok"])
check(rule(run(doc(rec("T", judged=False)), doc(rec("T", judged=False))), 3)["ok"], "unjudged: rule 3 cannot fail")
# n=1 target that hard-fails
check(not rule(run(doc(rec("T")), doc(rec("T", hard=True)), target=["T"]), 2)["ok"])

# ── ordering, one-sided scenarios, ONLY ─────────────────────────────────────
a = doc(rec("A"), rec("B", score=1.0), rec("C", hard=True), rec("D"), rec("E", score=1.0), rec("OLD"))
b = doc(rec("A", score=0.7), rec("B", hard=True), rec("C"), rec("D"), rec("E", score=1.0), rec("NEW"))
r = run(a, b)
check([x[0] for x in r["rows"]["regression"]] == ["B", "A"], "new hard fail before a score drop")
check([x[0] for x in r["rows"]["improvement"]] == ["C"] and [x[0] for x in r["rows"]["unchanged"]] == ["D", "E"])
check(list(r["only_a"]) == ["OLD"] and list(r["only_b"]) == ["NEW"])
check(rule(r, 0)["details"] == ["OLD (only in A)", "NEW (only in B)"])
check(set(run(a, b, only=["A", "OLD"])["sa"]) == {"A", "OLD", "B", "C", "D", "E"} and
      [x[0] for x in run(a, b, only=["A", "OLD"])["rows"]["regression"]] == ["A"], "ONLY filters the rows")
text = C.report(a, b, r)
check(text.index("Regressions") < text.index("Improvements") < text.index("Unchanged") < text.index("Only in A")
      < text.index("Acceptance"))
check("=> REJECT" in text and "rule 1  FAIL" in text and "rule 3  FAIL" in text)
good = C.report(doc(rec("A")), doc(rec("A")), run(doc(rec("A")), doc(rec("A"))))
check("=> ACCEPT" in good and "n < 3" in good)
check("not judged" in C.report(doc(rec("A", judged=False)), doc(rec("A", judged=False)),
                               run(doc(rec("A", judged=False)), doc(rec("A", judged=False)))))

# ── header ──────────────────────────────────────────────────────────────────
h = "\n".join(C.header(doc(rec("A"), label="base", sha="1" * 40, dirty=True, prompt="a" * 64),
                       doc(rec("A"), label="new", model="claude-haiku-5-5", sha="2" * 40, prompt="b" * 64,
                           rubric="q" * 64, scen={"A": "1"})))
check("1111111+dirty(1)" in h and "2222222" in h and "aaaaaaaaaaaa" in h and "bbbbbbbbbbbb" in h, h)
check("rubric hash    rrrrrrrrrrrr" in h and "qqqqqqqqqqqq" in h and "judge rubrics differ" in h, h)
check("the models differ" in h and "claude-haiku-5-5  <- differs" in h)
same = "\n".join(C.header(doc(rec("A")), doc(rec("A"))))
check("differs" not in same and "NOTE" not in same, same)
check("scenario definition changed: A" in "\n".join(C.header(doc(rec("A"), scen={"A": "1"}), doc(rec("A"), scen={"A": "2"}))) or
      "scenario definition changed between the runs: A" in "\n".join(C.header(doc(rec("A"), scen={"A": "1"}), doc(rec("A"), scen={"A": "2"}))))

# ── files ───────────────────────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    (t / "r1.json").write_text("{}")
    try:
        C.graded_path(str(t / "r1.json"))
        check(False, "a run file without graded sibling must exit")
    except SystemExit as e:
        check("r1.graded.json is missing" in str(e) and "make bot-eval-grade RUN=" in str(e), str(e))
    try:
        C.graded_path(str(t / "nope.json"))
        check(False, "a missing file must exit")
    except SystemExit as e:
        check("no such file" in str(e), str(e))
    for name, d in (("r1", doc(rec("T"), rec("U"))), ("r2", doc(rec("T", hard=True), rec("U")))):
        (t / f"{name}.graded.json").write_text(json.dumps(d))
    check(C.graded_path(str(t / "r1.json")).name == "r1.graded.json")
    check(C.graded_path(str(t / "r1.graded.json")).name == "r1.graded.json")
    check(C.load(str(t / "r2.json"))["scenarios"][0]["id"] == "T")
    cmd = [sys.executable, str(Path(C.__file__)), str(t / "r1.json"), str(t / "r2.graded.json")]
    p = subprocess.run(cmd, capture_output=True, text=True)
    check(p.returncode == 0 and "=> REJECT" in p.stdout, p.stdout + p.stderr)
    check(subprocess.run(cmd + ["--strict"], capture_output=True, text=True).returncode == 1, "--strict exits 1 on REJECT")
    p = subprocess.run(cmd[:3] + [str(t / "r1.json"), "--target", "T", "--strict"], capture_output=True, text=True)
    check(p.returncode == 0 and "=> ACCEPT" in p.stdout, p.stdout + p.stderr)
    p = subprocess.run(cmd + ["--only", "U"], capture_output=True, text=True)
    check("=> ACCEPT" in p.stdout and "Regressions (0)" in p.stdout, p.stdout)

print(f"compare_checks: {ok} assertions passed")
