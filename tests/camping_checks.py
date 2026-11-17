"""Plain-assert checks of fata/camping.py (no pytest):  .venv/bin/python tests/camping_checks.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from myhordes_mcp.fata.camping import (   # noqa: E402
    camping_odds, camping_terms, is_pro_camper, odds_cap, order_text, plan_upgrades, ruin_term,
)

RUIN = {"camp_boost": 10, "camp_slots": 2, "digs_remaining": 0}


def prev(**kw):
    return camping_terms(**kw)["previous"]


# Plan: worked values of docs/camping-plan.md §1.2
p = plan_upgrades(0, 0, 1.0, ap=30, items=30)
assert (p["improve"], p["install"], p["level"]) == (8, 2, 58), p
assert order_text(p) == "8× improve, then 2× install"
p = plan_upgrades(43, 0, 1.0, ap=30, items=30)
assert (p["improve"], p["install"], p["level"], p["ap"]) == (1, 1, 57, 2), p
# Few AP / items
p = plan_upgrades(0, 0, 1.0, ap=3, items=0)
assert (p["improve"], p["install"], p["level"]) == (3, 0, 15), p
p = plan_upgrades(0, 0, 1.0, ap=3, items=5)
assert (p["improve"], p["install"], p["level"]) == (0, 3, 27), p
# Cap reached early: fewest AP that reach it (base 70 + level, cap 0.9 -> level 20: 4 improve)
p = plan_upgrades(0, 70, 0.9, ap=10, items=0)
assert (p["improve"], p["ap"], round(p["odds"], 2)) == (4, 4, 0.9), p
# Already at the cap: nothing to do
assert plan_upgrades(0, 95, 0.9, ap=5, items=5)["ap"] == 0
# Level >= 50: no action allowed
assert plan_upgrades(50, 0, 1.0, ap=5, items=5)["ap"] == 0

# Previous table, normal / pro / panda, tail and index cap
assert [prev(nights=n) for n in range(7)] == [80, 60, 35, 15, 0, -50, -100]
assert prev(nights=11) == -5000 and prev(nights=500) == -5000       # index capped
assert [prev(nights=n, skill="procamp") for n in range(8)] == [80, 70, 60, 40, 30, 20, 0, -50]
assert [prev(nights=n, panda=True) for n in range(6)] == [50, 30, 20, 10, 0, -50]
assert [prev(nights=n, panda=True, skill="reclusive1") for n in range(6)] == [50, 45, 40, 30, 20, 10]
assert prev(nights=6, panda=True, skill="reclusive1") == -100 and prev(nights=6, panda=True, skill="procamp") == 0
assert camping_terms(panda=True)["town"] == -30 and camping_terms()["town"] == 0

# Pro camper: procamp has no limit, Reclusive only while nights < 6
assert is_pro_camper("procamp", 40) and is_pro_camper("reclusive2", 5)
assert not is_pro_camper("reclusive2", 6) and not is_pro_camper("none", 0)
assert prev(nights=6, skill="reclusive3") == -100       # normal table at index 6
assert prev(nights=6, skill="procamp") == 0             # pro table at index 6

# Caps
assert odds_cap("Survivalist", "none") == 1.0
assert odds_cap("Scout", "reclusive4") == 0.99
assert odds_cap("Scout", "reclusive3") == 0.9 and odds_cap("Resident", "none") == 0.9
assert odds_cap("Survivalist", "reclusive4") == 1.0
assert camping_odds({"a": 300}, 0.9) == 0.9 and camping_odds({"a": -20}, 0.9) == 0.0

# Ruin: bonus, buried, none, full (slot rule), unlimited slots
assert ruin_term(RUIN, 0) == 10 and ruin_term(RUIN, 1) == 10
assert ruin_term(RUIN, 2) == -25
assert ruin_term({**RUIN, "digs_remaining": 3}, 0) == 15
assert ruin_term({**RUIN, "digs_remaining": 3}, 2) == -25      # buried but full
assert ruin_term(None, 0) == -25
assert ruin_term({"camp_boost": 5, "camp_slots": -1}, 99) == 5

# Crowd, zombies, vest, distance, night, devastated, items, lighthouse, tomb
assert [camping_terms(hidden_before=n)["campers"] for n in range(8)] == [0, 0, -10, -30, -50, -70, -70, -70]
t = camping_terms(zombies=3)
assert t["zombies"] == -21 and camping_terms(zombies=3, vest=True)["zombies"] == -9
assert camping_terms(distance=0)["distance"] == -100 and camping_terms(distance=13)["distance"] == 7
assert camping_terms(distance=99)["distance"] == 20
assert camping_terms(night=False)["night"] == 0 and camping_terms(devastated=True)["devastated"] == -50
assert camping_terms(camp_items=2, lighthouse=True, tomb=True)["campitems"] == 10
assert camping_terms(lighthouse=True)["lighthouse"] == 25 and camping_terms(tomb=True)["tomb"] == 8

# Whole sum: 14 km, ruin +10, 0 nights, level 58, night: 80+58+10+10+10 = 168 -> cap
t = camping_terms(level=58, ruin=RUIN, distance=14)
assert sum(t.values()) == 80 + 58 + 10 + 10 + 10 and camping_odds(t, 0.9) == 0.9

# --- camping log rules (fata/camplog.py) ---
from myhordes_mcp.fata import camplog, camp_zones   # noqa: E402

N = 10
# 2026-11-17 20:00 and 12:00 game time (Europe/Paris, UTC+1 in November)
EVE = 1794942000
NOON = EVE - 8 * 3600


def alive(coords, day, time, inside=False, name="X"):
    return {"name": name, "coords": coords, "inside": inside, "day": day, "time": time}


def view(alive_=None, dead_=None):
    return {"alive": alive_ or {}, "dead": dead_ or {}}


def outcome(e_rec, m_rec):
    e = view({1: e_rec} if e_rec else {})
    m = view({1: m_rec} if m_rec else {})
    return camplog.night_outcome(N, e, m)[0].get(1)


# sure: outside on Z at the end of day N, updated on N+1 still on Z
r = outcome(alive("[2|3]", N, EVE), alive("[2|3]", N + 1, EVE + 10000))
assert r and r["label"] == "sure" and r["zone"] == "[2|3]", r
# probable: M not updated on N+1 (record still dated N, same place)
r = outcome(alive("[2|3]", N, EVE), alive("[2|3]", N, EVE))
assert r and r["label"] == "probable", r
# probable: back in town on N+1
r = outcome(alive("[2|3]", N, EVE), alive("[0|0]", N + 1, EVE + 10000, inside=True))
assert r and r["label"] == "probable" and r["zone"] == "[2|3]", r
# probable: elsewhere on N+1
assert outcome(alive("[2|3]", N, EVE), alive("[4|3]", N + 1, EVE + 10000))["label"] == "probable"
# not counted: stale in both (dated before N)
assert outcome(alive("[2|3]", N - 2, EVE), alive("[2|3]", N - 2, EVE)) is None
# not counted: inside at the end of day N, or at the doors
assert outcome(alive("[0|0]", N, EVE, inside=True), alive("[0|0]", N + 1, EVE + 10000, inside=True)) is None
assert outcome(alive("[0|0]", N, EVE), alive("[0|0]", N + 1, EVE + 10000)) is None
# not counted: absent from M (dead or gone)
assert outcome(alive("[2|3]", N, EVE), None) is None
# M record dated N and later than E's overrides it (back in town late on day N: not outside)
assert outcome(alive("[2|3]", N, EVE), alive("[0|0]", N, EVE + 50, inside=True)) is None
# ... and the other way: E inside, M (same day N, later) outside = counted, probable
r = outcome(alive("[0|0]", N, EVE, inside=True), alive("[5|5]", N, EVE + 50))
assert r and r["zone"] == "[5|5]" and r["label"] == "probable", r
# E has no record of the citizen at all, M dated N+1 outside: stale E-side evidence, not counted
assert outcome(None, alive("[2|3]", N + 1, EVE + 10000)) is None
# daytime record (before 19:00) outside with no N+1 confirmation: a day trip, not counted
assert outcome(alive("[2|3]", N, NOON), alive("[2|3]", N, NOON)) is None
assert outcome(alive("[2|3]", N, NOON), alive("[0|0]", N + 1, EVE + 10000, inside=True)) is None
# ... but confirmed on N+1 on the same zone: sure
assert outcome(alive("[2|3]", N, NOON), alive("[2|3]", N + 1, EVE + 10000))["label"] == "sure"
# died outside: type 5 on night N outside; not other types, days, or in town
dead = {7: {"name": "D", "type": 5, "day": N, "coords": "[1|1]"},
        8: {"name": "D2", "type": 6, "day": N, "coords": "[1|1]"},
        9: {"name": "D3", "type": 5, "day": N - 1, "coords": "[1|1]"},
        10: {"name": "D4", "type": 5, "day": N, "coords": "[0|0]"}}
c, d = camplog.night_outcome(N, view(), view(dead_=dead))
assert list(d) == [7] and d[7]["zone"] == "[1|1]" and not c

# apply_night: idempotent replace, line, counts
log = {}
camplog.apply_night(log, 9, {1: {"name": "A", "zone": "[1|1]", "label": "sure"}}, {})
camplog.apply_night(log, N, {1: {"name": "A", "zone": "[1|1]", "label": "probable"},
                             2: {"name": "B", "zone": "[2|2]", "label": "sure"}}, {3: {"name": "C", "zone": "[3|3]"}})
camplog.apply_night(log, N, {1: {"name": "A", "zone": "[1|1]", "label": "probable"},
                             2: {"name": "B", "zone": "[2|2]", "label": "sure"}}, {3: {"name": "C", "zone": "[3|3]"}})
assert camplog.counts(log, 1) == (1, 1) and camplog.counts(log, 2) == (1, 0) and camplog.counts(log, 99) == (0, 0)
assert log["citizens"]["3"]["died_outside"] == N and log["citizens"]["3"]["nights"] == []
assert camplog.night_line(log, N) == "Camped: 1 sure (B), 1 probable (A)", camplog.night_line(log, N)
assert camplog.night_line(log, 5) is None
camplog.apply_night(log, N, {}, {})   # recomputed to nothing: night removed, dead cleared, empty entries dropped
assert camplog.counts(log, 1) == (1, 0) and "2" not in log["citizens"] and "3" not in log["citizens"]

# --- zone camp level record (fata/camp_zones.py) ---
rep = {"day": 20, "level": 58, "source": "reported"}
pl = {"day": 20, "level": 58, "source": "planned"}
assert camp_zones.estimate_level(None, 21) is None
assert camp_zones.estimate_level(rep, 20)[:2] == (58, "reported on day 20")
assert camp_zones.estimate_level(rep, 21)[0] == 43
assert camp_zones.estimate_level(rep, 22)[0] == 28
assert camp_zones.estimate_level(rep, 30)[0] == 0                      # floor
assert camp_zones.estimate_level(pl, 21)[:2] == (43, "estimate from the plan of day 20, not verified")
assert camp_zones.estimate_level(rep, 19)[0] == 58                      # never negative decay

# record file: same-day replace, newer replaces older, older never overwrites newer (temp towns dir)
import tempfile   # noqa: E402
from myhordes_mcp.fata import archive   # noqa: E402
with tempfile.TemporaryDirectory() as tmp:
    tdir = Path(tmp) / "s1-test"
    tdir.mkdir()
    archive.town_dir = lambda town_id: tdir          # this script only: no real towns/ is touched
    camplog.AUTO = 0
    assert not camp_zones.record_zone(1, "[1|2]", 20, 40, "reported")  # off where TOWN_LOG_AUTO=0 (PC)
    camplog.AUTO = 1
    assert camp_zones.record_zone(1, "[1|2]", 20, 40, "reported")
    assert camp_zones.record_zone(1, "[1|2]", 20, 58, "planned")     # same day: the plan replaces it
    assert camp_zones.load_zones(1)["[1|2]"] == {"day": 20, "level": 58, "source": "planned"}
    assert camp_zones.record_zone(1, "[1|2]", 21, 30, "reported")    # newer replaces older
    assert not camp_zones.record_zone(1, "[1|2]", 20, 99, "planned") # older never overwrites newer
    assert camp_zones.load_zones(1)["[1|2]"]["level"] == 30
    assert not camp_zones.record_zone(1, "[1|2]", 21, 1, "bogus")
    assert not list(tdir.glob("*.tmp"))                               # atomic write left no temp file

print("camping checks: ok")
