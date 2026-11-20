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
assert not is_pro_camper("reclusive1", 6) and not is_pro_camper("none", 0)
assert is_pro_camper("reclusive2", 7) and not is_pro_camper("reclusive4", 8)
assert prev(nights=6, skill="reclusive1") == -100       # Reclusive 1: normal table from 6
assert prev(nights=7, skill="reclusive3") == -50 and prev(nights=8, skill="reclusive3") == -400
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
assert camplog.counts(log, 1) == (1, 1, 0) and camplog.counts(log, 2) == (1, 0, 0) and camplog.counts(log, 99) == (0, 0, 0)
assert log["citizens"]["3"]["died_outside"] == N and log["citizens"]["3"]["nights"] == []
assert camplog.night_line(log, N) == "Camped: 1 sure (B), 1 probable (A)", camplog.night_line(log, N)
assert camplog.night_line(log, 5) is None
camplog.apply_night(log, N, {}, {})   # recomputed to nothing: night removed, dead cleared, empty entries dropped
assert camplog.counts(log, 1) == (1, 0, 0) and "2" not in log["citizens"] and "3" not in log["citizens"]

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

# --- Fata camp plans, v1.3 (towndata.town_camping -> camp_plans; anonymised values of town 8299 day 26) ---
from myhordes_mcp.fata.camping import format_camping_odds, plan_player_odds, skill_label   # noqa: E402
from myhordes_mcp.fata.towndata import build_result, plans_for_citizen, plans_for_day, plans_for_zone   # noqa: E402


IDS = {"Ann": 101, "Bob": 102, "Cyd": 103, "Dan": 104, "Eve": 105, "Fay": 106}


def fplayer(order, name, job, r, nights, vest, aids, tomb, eff, theo):
    return {"order": order, "player_id": IDS[name], "name": name, "job": job, "r_value": r,
            "previous_campings": nights, "camouflaged_scout": vest, "camping_aids": aids, "tomb": tomb,
            "effective_chances": eff, "theoretical_chances": theo}


def fplan(x, y, target_day, building, pre, new, dist, players, mode=1, creator=101):   # 101 = Ann
    return {"town": 1, "day": 26, "x": x, "y": y, "uid": f"u{x}-{y}-{target_day}", "target_day": target_day,
            "mode": mode, "creator": creator, "editor": None,
            "camping_plan": {"distance": dist, "zombies": 0, "night": True, "hardcore": False, "devastated": True,
                             "lighthouse": True, "building_id": building, "pre_existing_upgrades": pre,
                             "new_upgrades": new, "players": players}}


RAW = {
    "version": "1.3", "town_info": {"town": 1, "day": 26, "name": "T", "tx": 12, "ty": 13, "devast": 1},
    "town_maps": [{"x": 19, "y": 0, "camping_upgrade": 8.6, "zone_update": {"day": 26}},   # [7|13]
                  {"x": 20, "y": 0, "camping_upgrade": None, "zone_update": {"day": 26}}],
    "town_citizens": [{"citizen_id": IDS[n], "name": n, "job": j, "x": 12, "y": 13, "out": True}
                      for n, j in [("Ann", "shield"), ("Bob", "tamer"), ("Cyd", "tech"), ("Dan", "tech"),
                                   ("Eve", "book"), ("Fay", "vest")]],
    "building_data": [{"id": 36, "name_en": "Warehouse", "camp_boost": 10, "camp_slots": 5},
                      {"id": 58, "name_en": "Tent", "camp_boost": 30, "camp_slots": 1},
                      {"id": 10, "name_en": "Bunker", "camp_boost": 50, "camp_slots": 5}],
    "town_camping": [
        # Reclusive 1 at 6 nights (normal table again), Reclusive 2 with 3 camp items, a crowd malus
        fplan(19, 0, 26, 36, 8.4, 2.8, 15, [
            fplayer(1, "Ann", "shield", "R1", 6, False, 0, True, 0, -26),
            fplayer(2, "Bob", "tamer", "R1", 6, False, 0, True, 0, -26),
            fplayer(3, "Cyd", "tech", "R1", 6, False, 0, True, 0, -36),
            fplayer(4, "Dan", "tech", "R2", 6, False, 3, True, 59, 59)], creator=IDS["Dan"]),
        # Reclusive 4 at 7 nights, Scout vest, alone, a tent
        fplan(19, 1, 26, 58, 8.6, 2.8, 14, [fplayer(1, "Fay", "vest", "R4", 7, True, 0, True, 40, 40)], mode=2,
              creator=IDS['Fay']),
        # Survivalist (cap 100%) behind two Reclusive shields
        fplan(20, 0, 26, 10, 8.6, 2.8, 13, [
            fplayer(1, "Ann", "shield", "R1", 1, False, 0, False, 90, 169),
            fplayer(2, "Bob", "shield", "R4", 1, False, 0, False, 99, 169),
            fplayer(3, "Eve", "book", "R2", 6, False, 1, True, 100, 102)], creator=IDS['Eve']),
        # tomorrow, no ruin: shape only (the 52 is our own sum, not a Fata value)
        fplan(20, 0, 27, 0, 0, 1, 13, [fplayer(1, "Eve", "book", "none", 0, False, 0, False, 52, 52)]),
    ],
}
res = build_result(1, RAW)
plans = res["camp_plans"]   # sorted by target day, then zone
assert len(plans) == 4 and [(p["target_day"], p["coords"]) for p in plans] == [
    (26, "[7|12]"), (26, "[7|13]"), (26, "[8|13]"), (27, "[8|13]")]
fay, wh, bunker, tomorrow = plans
assert wh["ruin"]["name"] == "Warehouse" and wh["creator"] == "Dan" and wh["editor"] is None
assert (wh["level_before"], wh["level_after"], wh["upgrades_pct"]) == (42, 56, 14)
assert tomorrow["ruin"] is None and tomorrow["creator"] == "Ann"          # building_id 0 = no ruin
eve = bunker["players"][2]
assert (eve["job"], eve["skill"], eve["nights"], eve["camp_items"], eve["tomb"]) == ("Survivalist", "reclusive2", 6, 1, True)
assert fay["players"][0]["vest"] and fay["players"][0]["skill"] == "reclusive4"
assert [z["camp_level"] for z in res["zones"]] == [43, None]               # 8.6 units = 43 %, null = no estimate
# selection helpers: today by default, then by zone and by citizen
assert len(plans_for_day(res)) == 3 and len(plans_for_day(res, 27)) == 1 and not plans_for_day(res, 5)
assert len(plans_for_zone(res, "[8|13]")) == 1 and len(plans_for_zone(res, "[8|13]", 27)) == 1
assert [p["coords"] for p in plans_for_citizen(res, 105)] == ["[8|13]"]     # Eve, today only
# every camper: our terms == Fata's uncapped sum, our capped odds == Fata's effective odds
n_checked = 0
for p in plans:
    for i, q in enumerate(p["players"]):
        terms, theo, eff = plan_player_odds(p, i)
        assert theo == q["fata_theoretical"] and eff == q["fata_effective"], (p["coords"], q["name"], theo, eff, q)
        n_checked += 1
assert n_checked == 9
# the tool: plan values as defaults, a right Fata number is silent, a wrong one is a MISMATCH line
out = format_camping_odds(res, x=7, y=13, citizen="Ann", town_id=None)
assert "MISMATCH" not in out and "Fata plan tonight on [7|13], Warehouse (by Dan)" in out
assert "hero skill Reclusive 1: from Dan's Fata plan" in out and "camping nights survived: 6, from Dan's Fata plan" in out
assert "camp bonus +56%: the level after the upgrades of Dan's Fata plan (the plan starts from +42%)" in out
assert "Fata's zone estimate (+43%) differs from the plan's existing bonus (+42%)" in out and "hero skill Reclusive 1" in out
RAW["town_camping"][0]["camping_plan"]["players"][3]["effective_chances"] = 58
assert "MISMATCH Dan" in format_camping_odds(build_result(1, RAW), x=7, y=13, town_id=None)
RAW["town_camping"][0]["camping_plan"]["players"][3]["effective_chances"] = 59
# the plan's zone is used when none is given; explicit arguments win over the plan
out = format_camping_odds(res, x=None, y=None, citizen="Fay", town_id=None)
assert "Zone [7|12]," in out and "hero skill Reclusive 4" in out and "camping nights survived: 7, from Fay's" in out
out = format_camping_odds(res, x=None, y=None, citizen="Fay", skill="procamp", nights=0, vest=False, camp_level=0, town_id=None)
assert "hero skill Pro camper" in out and "camping nights survived" not in out and "Scout vest" not in out
# no plans (v1.2 data): no plan block, no plan values
old = build_result(1, {k: v for k, v in RAW.items() if k != "town_camping"})
assert old["camp_plans"] == [] and "Fata plan" not in format_camping_odds(old, x=7, y=13, citizen="Ann", town_id=None)

# --- day parameter: projection for a later night ---
tom = format_camping_odds(res, x=8, y=13, citizen="Eve", day_arg=27, town_id=None)
assert "Night of day 27 (tomorrow): a projection from today's data." in tom, tom
assert "Fata plan tomorrow night on [8|13]" in tom and "camp bonus +5%: the level after the upgrades of Ann's Fata plan (the plan starts from +0%)" in tom
assert "Planned in Ann's Fata plan for day 27: upgrades for +5% (+0% -> +5%), counted as done (1 improve = 1 AP)" in tom
assert ("still none tomorrow" in tom or "can spread in at night" in tom or "+1 a night" in tom
        or "probably higher" in tom), tom
# zombie projection (MapMaker::spreadCycleMH): growth +1 a night, spread only from neighbours
from myhordes_mcp.fata.camping import _project_zombies
_zm = {(5, 5): {"zombies": 0, "updated_day": 26}}
for _dx in (-1, 0, 1):
    for _dy in (-1, 0, 1):
        _zm.setdefault((5 + _dx, 5 + _dy), {"zombies": 0, "updated_day": 26})
import myhordes_mcp.fata.camping as _cm
_orig_zone_map, _orig_today = _cm.zone_map, _cm.zone_is_today
_cm.zone_map = lambda d: d["_zm"]
_cm.zone_is_today = lambda z, day: z.get("updated_day") == day
try:
    n, note = _project_zombies({"_zm": _zm}, (5, 5), _zm[(5, 5)], 0, "", 26, 27)
    assert n == 0 and "still none tomorrow" in note, note
    _zm[(6, 6)] = {"zombies": 3, "updated_day": 26}
    n, note = _project_zombies({"_zm": _zm}, (5, 5), _zm[(5, 5)], 0, "", 26, 27)
    assert n == 0 and "1 neighbouring zone has zombies" in note and "can spread in" in note, note
    _zm[(5, 5)] = {"zombies": 2, "updated_day": 26}
    n, note = _project_zombies({"_zm": _zm}, (5, 5), _zm[(5, 5)], 2, "", 26, 28)
    assert n == 4 and "counted 4 that night" in note, note
finally:
    _cm.zone_map, _cm.zone_is_today = _orig_zone_map, _orig_today
assert "Night of day 26 (tonight)." in format_camping_odds(res, x=8, y=13, town_id=None)
assert format_camping_odds(res, x=8, y=13, day_arg=26, town_id=None) == format_camping_odds(res, x=8, y=13, town_id=None)
err = format_camping_odds(res, x=8, y=13, day_arg=20, town_id=None)
assert err.startswith("Error: day 20 is already over (today is day 26)"), err
# no plan on the zone for day 27, but tonight's plan on it (+56% after its upgrades): carried
# over minus 15 per night, stated as conditional on those upgrades
proj = format_camping_odds(res, x=7, y=13, day_arg=27, town_id=None)
assert "camp bonus +41%: +56% planned in Dan's Fata plan for day 26 minus 15% (1 night)" in proj, proj
proj3 = format_camping_odds(res, x=7, y=13, day_arg=29, town_id=None)
assert "camp bonus +11%: +56% planned" in proj3 and "minus 45% (3 nights)" in proj3 and "Night of day 29 (in 3 days)" in proj3, proj3
# no plan on the zone at all: today's Fata level minus 15 per night
res_np = dict(res, camp_plans=[p for p in res["camp_plans"] if p["coords"] != "[7|13]"])
projn = format_camping_odds(res_np, x=7, y=13, day_arg=27, town_id=None)
assert "camp bonus +28%: today's +43%" in projn and "assuming no upgrades until then" in projn, projn
assert "nights camped from tonight to day 28 are not included" in proj3 and "tonight's camping is not included" in proj
# explicit camp_level wins, over the plan's typed level too
assert "Odds that night (camp bonus +10%)" in format_camping_odds(res, x=8, y=13, day_arg=27, camp_level=10, town_id=None)

# --- cap wording and zombie tolerance ---
def spare_of(out):
    import re
    mt = re.search(r"no upgrade needed, odds at the cap with (\d+) points to spare \((\d+) extra zombies? at hide time keeps? the cap, (\d+) would not\)", out)
    assert mt, out
    return tuple(map(int, mt.groups()))


for ap_ in (0, 5):
    out = format_camping_odds(res, x=7, y=13, camp_level=80, ap=ap_, town_id=None)
    assert "Tonight: no upgrade needed" in out and "ask the player how many AP" not in out, out
    sp, k, k1 = spare_of(out)
    assert (sp, k, k1) == (20, 2, 3) and "Plan:" not in out
# a vest tolerates floor(spare / 3)
out = format_camping_odds(res, x=7, y=13, camp_level=80, vest=True, town_id=None)
sp, k, k1 = spare_of(out)
assert (sp, k) == (20, 6), out
# ... and the tolerance is real: k extra zombies keep the cap, k + 1 do not (terms of the zone above)
t80 = camping_terms(level=80, distance=15, devastated=True)
assert camping_odds({**t80, "zombies": -7 * 2}, 0.9) == 0.9 and camping_odds({**t80, "zombies": -7 * 3}, 0.9) < 0.9
# exactly at the cap, no spare: the wording says so
assert "0 points to spare (one more zombie" in format_camping_odds(res, x=7, y=13, camp_level=60, town_id=None)
# not at the cap: the minimal plan is labelled Tonight, the optional line is separate and only when it carries over
out = format_camping_odds(res, x=7, y=13, camp_level=0, ap=3, defense_items=1, town_id=None)
assert "Tonight: " in out and "Plan:" not in out and "Optional" not in out, out
out = format_camping_odds(res, x=7, y=13, camp_level=0, ap=20, defense_items=5, camp_items=4, town_id=None)
assert "Optional, for later nights only (no effect on the odds tonight): " in out and "left tomorrow. Only the bonus above +15% survives the night." in out, out
out = format_camping_odds(res, x=7, y=13, camp_level=60, ap=1, town_id=None)   # 60 >= 50: no action, nothing to carry over
assert "Optional" not in out
# hero skill is not the job
out = format_camping_odds(res, x=7, y=13, citizen="Ann", town_id=None)
assert "Citizen: Ann (" in out and ", hero skill Reclusive 1)" in out and "Skill:" not in out
assert skill_label("procamp") == "Pro camper" and skill_label("reclusive3") == "Reclusive 3" and skill_label("none") == ""

# --- camping log: "planned" label (Fata camp plans as evidence) ---
def pview(alive_=None, dead_=None, plans=None):
    return {"alive": alive_ or {}, "dead": dead_ or {}, "plans": plans or []}


def plan(uid, day_, coords, *cits):
    return {"uid": uid, "target_day": day_, "coords": coords, "citizens": list(cits)}


# anonymised shape of town 8299 night 25: a citizen with an end-of-day record at 15:00 outside, alive
# next day, in a plan for night N: sure/probable do not apply (daytime), the plan does
AFT = EVE - 5 * 3600   # 15:00
pe = pview({1: alive("[2|3]", N, AFT, name="A"), 2: alive("[4|4]", N, EVE, name="B"), 3: alive("[0|0]", N, EVE, inside=True, name="C"),
            4: alive("[0|0]", N, AFT, inside=True, name="D"), 5: alive("[6|6]", N, AFT, name="E5")},
           plans=[plan("p1", N, "[2|3]", 1, 2, 3, 4, 7), plan("p-old", N - 1, "[9|9]", 5)])
pm = pview({1: alive("[0|0]", N + 1, EVE + 9000, inside=True, name="A"), 2: alive("[4|4]", N + 1, EVE + 9000, name="B"),
            3: alive("[0|0]", N + 1, EVE + 9000, inside=True, name="C"),
            4: alive("[0|0]", N + 1, EVE + 9000, inside=True, name="D"), 5: alive("[6|6]", N, AFT, name="E5")},
           {7: {"name": "G", "type": 5, "day": N, "coords": "[2|3]"}},
           plans=[plan("p1", N, "[2|3]", 1, 2, 3, 4, 7)])
camped, died = camplog.night_outcome(N, pe, pm)
assert camped[1] == {"name": "A", "zone": "[2|3]", "label": "planned"}        # 15:00 outside + plan
assert camped[2]["label"] == "sure"                                           # sure/probable come first
assert 3 not in camped                                                        # inside at 19:00+: contrary evidence
assert camped[4] == {"name": "D", "zone": "[2|3]", "label": "planned"}        # inside at 15:00 only: not contrary
assert 5 not in camped                                                        # only a plan of another night
assert 7 not in camped and list(died) == [7]                                  # dead in M: not planned (counted as died)
# no plan evidence: the old rule only
assert [c["label"] for c in camplog.night_outcome(N, {**pe, "plans": []}, {**pm, "plans": []})[0].values()] == ["sure"]
# plans of E and M are united by uid, M wins; a plan only in E counts too
only_e = camplog.night_outcome(N, pview(pe["alive"], plans=[plan("p1", N, "[2|3]", 1)]), {**pm, "plans": []})[0]
assert only_e[1]["label"] == "planned"
mw = camplog.night_outcome(N, pview(pe["alive"], plans=[plan("p1", N, "[2|3]", 1)]),
                           {**pm, "plans": [plan("p1", N, "[8|8]", 1)]})[0]
assert mw[1]["zone"] == "[8|8]"
# several plans: the one on the zone of the latest record, else the first
two = [plan("a", N, "[7|7]", 1), plan("b", N, "[2|3]", 1)]
assert camplog.night_outcome(N, pview(pe["alive"], plans=two), {**pm, "plans": []})[0][1]["zone"] == "[2|3]"
assert camplog.night_outcome(N, pview({}, plans=two), {**pm, "plans": []})[0][1]["zone"] == "[7|7]"
# counts / lines with the third label
lg = {}
camplog.apply_night(lg, N, camped, died)
assert camplog.counts(lg, 1) == (0, 0, 1) and camplog.night_count(lg, N) == 3
assert camplog.night_line(lg, N) == "Camped: 1 sure (B), 2 planned (A, D)", camplog.night_line(lg, N)

# rule version: a night stored under older rules is recomputed once, then left alone (temp town dir)
import gzip, json   # noqa: E402


def raw_day(day_, cits, plans):
    return {"version": "1.3", "town_info": {"town": 1, "day": day_, "name": "T", "tx": 12, "ty": 13},
            "town_citizens": [{"citizen_id": i, "name": n, "job": "dig", "x": x, "y": y, "out": True,
                               "last_update": {"day": d, "time": t}} for i, n, x, y, d, t in cits],
            "town_camping": [{"town": 1, "day": day_, "x": x, "y": y, "uid": u, "target_day": td, "mode": 1, "creator": 1,
                              "camping_plan": {"players": [{"order": o, "player_id": c, "name": "?", "job": "dig"}
                                                           for o, c in enumerate(cs)]}} for u, td, x, y, cs in plans]}


with tempfile.TemporaryDirectory() as tmp:
    tdir = Path(tmp) / "s1-test"
    (tdir / "cache").mkdir(parents=True)
    archive.town_dir = lambda town_id: tdir
    camplog.AUTO = 1
    plans_ = [("u1", N, 14, 13, [1])]     # absolute (14,13) = relative [2|0]
    for d_, cits in ((N, [(1, "A", 14, 13, N, AFT)]), (N + 1, [(1, "A", 12, 13, N + 1, EVE + 9000)])):
        with gzip.open(tdir / "cache" / f"day-{d_}.towndata.json.gz", "wt", encoding="utf-8") as f:
            json.dump(raw_day(d_, cits, plans_), f)
    camplog._views.clear()
    assert camplog.update_camping_log(1) == [N]
    lg = camplog.load_log(1)
    assert lg["nights"][str(N)]["rules"] == camplog.RULES and lg["nights"][str(N)]["planned"] == 1
    assert camplog.counts(lg, 1) == (0, 0, 1)
    assert camplog.update_camping_log(1) == []                      # unchanged inputs and rules: nothing to do
    stale = camplog.load_log(1)
    del stale["nights"][str(N)]["rules"]                            # as stored before the planned rule
    stale["citizens"] = {}
    camplog._write(tdir, stale)
    assert camplog.update_camping_log(1) == [N]                     # recomputed once
    assert camplog.counts(camplog.load_log(1), 1) == (0, 0, 1) and camplog.update_camping_log(1) == []


# --- group planner (fata/groupcamp.py, docs/group-camping-plan.md) ---
import itertools   # noqa: E402
import random   # noqa: E402
import os
import platform
import time   # noqa: E402
from myhordes_mcp.fata.groupcamp import (   # noqa: E402
    Camper, format_group_camping, level_ok, order_matters, parse_group, position_terms, solve,
)

C = Camper   # Camper(name, base, cap, tomb, tamer, carried, hint)
R0 = {"camp_boost": 0, "camp_slots": 5, "digs_remaining": 0}   # a ruin with no bonus and room for all
R20 = {"camp_boost": 20, "camp_slots": 1, "digs_remaining": 0}

# crowd absorbed by the camper with the most surplus: A has 10 points to spare, hides last (-10)
s = solve([C("A", 125), C("B", 115), C("C", 115)], level=0, ruin=None, ap=0)
assert s.order[2] == 0 and s.odds == [90, 90, 90] and s.ap == 0, s
# ruin room (1 place, +20, then -25): the camper with more to lose goes first
s = solve([C("A", 60), C("B", 90)], level=0, ruin=R20, ap=0)
assert s.order == [0, 1] and s.odds == [80, 65], s
assert position_terms(3, R20, 1) == [-25, -35, -55]   # 1 hidden before: the only place is taken
# improves beat a paid grave (fewest paid graves first): 7 improves, no grave, no install
s = solve([C("A", 80)], level=0, ruin=None, defense_items=2)
assert (s.improves, s.installs, s.paid, s.level, s.odds) == (7, 0, 0, 35, [90]), s
# at level 50 nothing can be improved: the grave is the only way
s = solve([C("A", 57)], level=50, ruin=None)
assert (s.improves, s.paid, s.ap, s.odds) == (0, 1, 1, [90]), s
assert level_ok(45, 1, 0) and not level_ok(50, 1, 0) and level_ok(44, 1, 1) and not level_ok(45, 1, 1)
# the camp item goes where the group gains most: equal gain, the lowest camper wins
s = solve([C("A", 110), C("B", 105)], level=0, ruin=None, ap=0, pool=1)
assert s.items == [0, 1] and s.odds == [85, 85], s
# the slot limit: 2 items of the 5 available
s = solve([C("A", 40)], level=0, ruin=None, ap=0, pool=5, slots=2)
assert s.items == [2] and s.odds == [25], s
# Tamer: the dog digs the grave for free; a steak adds +5 to the zone while it is below 50
s = solve([C("T", 50, tamer=True)], level=0, ruin=None, ap=0)
assert (s.grave, s.odds, s.dogs, s.boosts, s.ap) == (["dog"], [33], 1, 0, 0), s
s = solve([C("T", 50, tamer=True)], level=0, ruin=None, ap=0, steaks=1)
assert (s.grave, s.odds, s.boosts, s.level, s.ap) == (["boost"], [38], 1, 5, 0), s
s = solve([C("T", 50, tamer=True)], level=50, ruin=None, ap=0, steaks=1)
assert (s.grave, s.boosts, s.level) == (["dog"], 0, 50), s                      # zone not improvable: plain dog
s = solve([C("T", 50, tamer=True, tomb=True)], level=0, ruin=None, ap=0, steaks=1)
assert s.grave == ["dug"] and s.boosts == 0, s                                  # grave already dug: no dog use
# objective: 1 AP, one improve (+5 for both) or one grave
s = solve([C("A", 40), C("B", 80)], level=0, ruin=R0, ap=1)
assert (s.improves, s.paid, s.odds) == (1, 0, [45, 85]), s
s = solve([C("A", 40), C("B", 80)], level=0, ruin=R0, ap=1, objective="weakest")
assert (s.improves, s.paid, s.grave, s.odds) == (0, 1, ["paid", ""], [48, 80]), s
# AP limit
s = solve([C("A", 80)], level=0, ruin=None, ap=2)
assert (s.ap, s.improves, s.paid, s.odds) == (2, 1, 1, [68]), s    # 1 improve + 1 grave: 80 - 25 + 5 + 8
s = solve([C("A", 80)], level=0, ruin=None, ap=0)
assert s.ap == 0 and s.odds == [55], s
# hiding order irrelevant when everyone is far above the cap
cs = [C("A", 200), C("B", 200)]
s = solve(cs, level=0, ruin=R0, ap=0)
assert not order_matters(cs, s, position_terms(2, R0, 0), s.level)
cs = [C("A", 60), C("B", 90)]
s = solve(cs, level=0, ruin=R20, ap=0)
assert order_matters(cs, s, position_terms(2, R20, 0), s.level)

# exact: compared with a brute force over every order, grave, item split and upgrade count
def brute(campers, *, level, ruin, hidden_before=0, ap=None, defense_items=0, pool=0, steaks=0, slots=5,
          objective="expected"):
    n = len(campers)
    pos = position_terms(n, ruin, hidden_before)
    tam = sum(1 for c in campers if c.tamer and not c.tomb)
    best = None
    allocs = [m for m in itertools.product(range(min(slots, pool) + 1), repeat=n) if sum(m) <= pool]
    kinds = []
    for c in campers:
        if c.tomb:
            kinds.append([("dug", 0, 0, 0, 0)])
        else:
            k = [("", 0, 0, 0, 0), ("paid", 1, 0, 8, 0)]
            if c.tamer:
                k += [("dog", 0, 0, 8, 1), ("boost", 0, 1, 8, 1)]
            kinds.append(k)
    for j in range(defense_items + 1 if ap is None else min(defense_items, ap) + 1):
        for sb in range(min(steaks, tam) + 1):
            i = 0
            while (ap is None or i + j <= ap) and level_ok(level, i + sb, j):
                lv = level + 5 * (i + sb) + 9 * j
                gm = n if ap is None else ap - i - j
                for ks in itertools.product(*kinds):
                    paid, b, dogs = sum(k[1] for k in ks), sum(k[2] for k in ks), sum(k[4] for k in ks)
                    if paid > gm or b != sb:
                        continue
                    for m in allocs:
                        for perm in itertools.permutations(range(n)):
                            odds = [0] * n
                            for p, k in enumerate(perm):
                                odds[k] = max(0, min(campers[k].base + pos[p] + lv + ks[k][3] + 5 * m[k], campers[k].cap))
                            surv = (sum(odds), min(odds)) if objective == "expected" else (min(odds), sum(odds))
                            key = (tuple(-v for v in surv), j, paid, i + j + paid, sb, dogs, sum(m))
                            if best is None or key < best:
                                best = key
                i += 1
    return best


rnd = random.Random(7)
for t in range(40):
    n = rnd.choice([1, 2, 3, 3])
    cs = [C(f"c{k}", rnd.randint(-30, 95), rnd.choice([90, 99, 100]), rnd.random() < .15, rnd.random() < .35,
            rnd.choice([0, 0, 1]), k) for k in range(n)]
    kw = dict(level=rnd.choice([0, 0, 10, 35, 47, 50]),
              ruin=rnd.choice([None, {"camp_boost": rnd.choice([-20, 0, 10, 25]), "camp_slots": rnd.choice([1, 2, 5]),
                                      "digs_remaining": 0}]),
              hidden_before=rnd.choice([0, 0, 1, 2]), ap=rnd.choice([None, None, 0, 1, 3, 6]),
              defense_items=rnd.choice([0, 1, 2]), pool=rnd.choice([0, 1, 2, 3]), steaks=rnd.choice([0, 0, 1, 2]),
              slots=rnd.choice([1, 2, 5]), objective=rnd.choice(["expected", "weakest"]))
    s = solve(cs, **kw)
    got = (tuple(-v for v in s.survival), s.installs, s.paid, s.ap, s.boosts, s.dogs, sum(s.items)) if s else None
    assert got == brute(cs, **kw), (t, got, brute(cs, **kw), kw)

# runtime: 6 campers, a lot to decide (PC; the Pi 3B+ is about 10x slower)
RUIN3 = {"camp_boost": 10, "camp_slots": 3, "digs_remaining": 0}
worst = 0.0
for bases, kw in [([20, 10, 0, -10, -20, -30], dict(ap=30, defense_items=5, pool=6, steaks=2)),
                  ([75, 65, 55, 45, 35, 25], dict(ap=None, defense_items=6, pool=8, steaks=2)),
                  ([60, 50, 40, 30, 20, 10], dict(ap=6, defense_items=3, pool=4, steaks=1))]:
    cs = [C(f"c{i}", b, 90 if i % 3 else 99, False, i < 2, 1 if i < 2 else 0, i) for i, b in enumerate(bases)]
    for ruin in (None, RUIN3):
        t0 = time.perf_counter()
        solve(cs, level=0, ruin=ruin, **kw)
        worst = max(worst, time.perf_counter() - t0)
# Measured 2026-11-18 on 100 random 6-camper instances: PC median 25 ms / max 363 ms, Pi 3B+
# median 356 ms / max 4983 ms. The bound is a regression guard, loose enough for the Pi.
LIMIT = float(os.getenv("CAMPING_SOLVER_LIMIT_S", "1.0" if platform.machine() == "x86_64" else "10.0"))
assert worst < LIMIT, (worst, LIMIT)

# group spec
assert parse_group("Korra:R2:n2, Ammonia:R4:n2:tomb:items=1, Bob:tamer:vest, @Eve:123:surv") == [
    {"name": "Korra", "skill": "reclusive2", "nights": 2},
    {"name": "Ammonia", "skill": "reclusive4", "nights": 2, "tomb": True, "items": 1},
    {"name": "Bob", "tamer": True, "vest": True}, {"name": "@Eve:123", "surv": True}]
assert parse_group("") == [] and parse_group("A:pro:none")[0]["skill"] == "none"
assert parse_group("A:zzz").startswith("Error: cannot read 'zzz' after A")

# the tool on the synthetic town above
out = format_group_camping(res, x=7, y=13, town_id=None)
assert out.startswith("## Group camping") and "Ann (" in out and "Dan (" in out and "Expected survivors" in out, out
assert "Night of day 26 (tonight)." in out and "Zone [7|13]" in out
assert format_group_camping(res, x=7, y=13, group="Ann, Bob, Cyd, Dan", town_id=None).split("Hiding order")[1] == out.split("Hiding order")[1]
assert "Error: the group's plans are on several zones ([7|12], [7|13], [8|13])" in format_group_camping(res, x=None, y=None, town_id=None)
assert "Zone [8|13]" in format_group_camping(res, x=None, y=None, group="Eve", town_id=None)
e = format_group_camping(res, x=7, y=13, group="Anna", town_id=None)
assert e.startswith("Error: 'Anna' is not a living citizen") and "Ann" in e, e
e = format_group_camping(res, x=7, y=13, group="Ann,Bob,Cyd,Dan,Eve,Fay,Ann", town_id=None)
assert e.startswith("Error: 7 campers: the planner handles at most 6"), e
assert format_group_camping(res, x=7, y=13, day_arg=20, town_id=None).startswith("Error: day 20 is already over")
assert format_group_camping(res, x=7, y=13, objective="best", town_id=None).startswith("Error: objective must be")
assert format_group_camping(res, x=0, y=0, group="Ann", town_id=None).startswith("Error: nobody camps in town")
assert "a projection from today's data" in format_group_camping(res, x=7, y=13, day_arg=27, town_id=None)
w = format_group_camping(res, x=8, y=13, group="Eve:R4:surv", ap=0, town_id=None)
assert "Survivalist" in w and "cap 100" in w and "AP used 0 of 0" in w, w

# --- multi-night chain, Fata plan upgrades, nearby defensive items (docs/camping-multinight-plan.md) ---
import copy, re   # noqa: E402
from types import SimpleNamespace   # noqa: E402
from myhordes_mcp.fata.groupcamp import (   # noqa: E402
    MAX_NIGHTS, Camper as _Camper, _absorbable, _ap_warning, _make_camper, nearby_defense_lines,
)
from myhordes_mcp.fata.camping import fata_plan_upgrades, typed_plan   # noqa: E402

# the 2026-11-20 case: Fata plan 7.6 pre-existing + 3 new units of 5% (+38% -> +53%), estimate 38
RAW2 = copy.deepcopy(RAW)
RAW2["town_maps"].append({"x": 21, "y": 0, "camping_upgrade": 7.6, "zone_update": {"day": 26}})
RAW2["town_camping"].append(fplan(21, 0, 26, 0, 7.6, 3.0, 12, [
    fplayer(1, "Eve", "book", "R2", 2, False, 0, False, 50, 50), fplayer(2, "Fay", "vest", "R2", 2, True, 0, False, 50, 50)],
    creator=105))
res2 = build_result(1, RAW2)
up = fata_plan_upgrades(typed_plan(plans_for_zone(res2, "[9|13]"), None))
assert (up["before"], up["after"], up["pct"], up["improves"], up["creator"]) == (38, 53, 15, 3, "Eve"), up
assert fata_plan_upgrades(None) is None and fata_plan_upgrades({"level_before": 5, "level_after": 5, "creator": "x", "target_day": 1}) is None
# A tonight, single night: start = level_after, the plan line is printed, 3 AP "if not done"
one = format_group_camping(res2, x=9, y=13, town_id=None)
assert "Camp bonus +53% with the Fata plan's upgrades (+38% before them)" in one, one
assert "Fata plan (Eve): upgrades for +15% (+38% -> +53%). Not a game reading: check in game whether they are done" in one
assert "(+3 AP if the Fata plan's upgrades are not done yet)" in one
# camp_level given wins: the plan's upgrades are not added, no plan line
given = format_group_camping(res2, x=9, y=13, camp_level=38, town_id=None)
assert "Camp bonus now +38%" in given and "Fata plan (Eve)" not in given, given
# get_camping_odds uses the same helper
assert "Fata plan (Eve): upgrades for +15%" in format_camping_odds(res2, x=9, y=13, citizen="Eve", town_id=None)
# chain: each night starts from the previous night's level after ALL its upgrades, -15
chain = format_group_camping(res2, x=9, y=13, until_day=29, town_id=None)
assert "Nights 26-29, Eve and Fay at [9|13]" in chain and "starts +38% now, then Eve's Fata plan upgrades for +15% -> +53%" in chain, chain
nl = [l for l in chain.splitlines() if l.startswith("Night ")]
assert len(nl) == 4
level = 53   # after night 26 (plan upgrades counted, solver adds nothing)
for l in nl[1:]:
    st = int(re.search(r"starts \+(\d+)%", l).group(1))
    assert st == level - 15, (l, level)
    m_ = re.search(r"-> \+(\d+)%", l)
    level = int(m_.group(1)) if m_ else st
assert "AP per night: 5 (+3 if not done) / 5 / 5 / 5; the group has 12 a day (6 each)." in chain, chain
# until_day == day is a single night (old layout); errors
assert format_group_camping(res2, x=9, y=13, until_day=26, town_id=None) == one
assert format_group_camping(res2, x=9, y=13, until_day=25, town_id=None).startswith("Error: until_day 25 is before the first night (day 26)")
assert format_group_camping(res2, x=9, y=13, until_day=26 + MAX_NIGHTS, town_id=None).startswith(f"Error: {MAX_NIGHTS + 1} nights asked")
assert "Nights 26-31" in format_group_camping(res2, x=9, y=13, until_day=25 + MAX_NIGHTS, town_id=None)
# a real Fata plan for a later night on the zone wins over the chain (and is said)
RAW3 = copy.deepcopy(RAW2)
RAW3["town_camping"].append(fplan(21, 0, 27, 0, 4, 0, 12, [fplayer(1, "Eve", "book", "R2", 3, False, 0, False, 50, 50)]))
c3 = format_group_camping(build_result(1, RAW3), x=9, y=13, until_day=27, town_id=None)
assert "Fata plan for day 27 types +20%; the chain from night 26 gives +38%: the plan's number is used" in c3, c3
assert "the Fata plan for day 27 has other campers: the first night's group is kept" in c3
# finite pools: 2 defensive items, ap 1 a night -> an install each of the first two nights only
pools = format_group_camping(res2, x=9, y=13, camp_level=0, ap=1, defense_items=2, group="Eve:n1:R2", until_day=28, town_id=None)
assert pools.count("1× install (1 AP + 1 defensive item)") == 2 and "Items: defensive 2 used (2 available at the start)." in pools, pools
night28 = next(l for l in pools.splitlines() if l.startswith("Night 28"))
assert "install" not in night28, night28
# steaks: one steak-fed dog use in the first night only
st = format_group_camping(res2, x=9, y=13, camp_level=0, steaks=1, ap=2, group="Bob:n1:R2", until_day=28, town_id=None)
assert st.count("steak-fed dog (+5%") == 1 and "steaks 1 used (1 available)" in st, st
# AP warning: night over the group's 6
w = format_group_camping(res2, x=9, y=13, camp_level=0, group="Eve:n0:R2", until_day=27, town_id=None)
assert "WARNING Night 26 needs 11 AP, more than the 6 the group has (6 each): drink/eat for AP." in w, w
# nN gets + k, a grave never carries (k > 0): _make_camper
inf = {"name": "X", "job": "Resident", "skill": "reclusive2", "nights": 2, "tomb": True, "vest": False,
       "tamer": False, "carried": 0, "hint": 0}
ctx_ = {"panda": False, "lighthouse": False, "devastated": False, "km": 10}
c0, c1 = _make_camper(inf, 0, ctx_, 0), _make_camper(inf, 1, ctx_, 0)
assert c0.tomb and not c1.tomb
assert c1.base == _make_camper({**inf, "nights": 3, "tomb": False}, 0, ctx_, 0).base
assert c0.base - c1.base == (8 + (prev(nights=2, skill="reclusive2", panda=False) - prev(nights=3, skill="reclusive2", panda=False))), (c0, c1)
# the AP warning names how many improves the night before could take over
_sol = lambda lvl, ap_, imp: SimpleNamespace(level=lvl, ap=ap_, improves=imp)
_n = lambda t, sol, fut=False: SimpleNamespace(target=t, sol=sol, plan_ap=0, future=fut, ap_total=sol.ap)
assert _absorbable(40) == 2 and _absorbable(50) == 0 and _absorbable(44) == 2 and _absorbable(0) == 10
wtxt = _ap_warning(_n(28, _sol(30, 9, 9)), _n(27, _sol(30, 2, 2)), 1)
assert "Night 28 needs 9 AP, more than the 6 the group has (6 each)" in wtxt and "do 3 of these improves the night before (night 27;" in wtxt, wtxt
assert _ap_warning(_n(28, _sol(30, 6, 6)), None, 1) == ""
# nearby defensive items: distance, round trip, nearest first, 3 shown + "more", tiers, hint, pointer
def zn(x, y, *names, day=26):
    return {"coords": f"[{x}|{y}]", "x": x, "y": y, "updated_day": day, "zombies": 0, "seen_today": True,
            "items": [{"name": n, "count": 1, "category": "Armor", "heavy": True} for n in names]}
nd = {"meta": {"day": 26}, "zones": [zn(5, 5, "Old Door"), zn(4, 5, "Trestle"), zn(5, 7, "Mattress"), zn(8, 5, "Old Door"),
                                      zn(20, 20, "Old Door"), zn(7, 7), zn(0, 0, "Old Door")]}
nb = nearby_defense_lines(nd, (5, 6), [26, 27], 3, multi=True)
body = [l for l in nb if l.startswith("  [")]
assert [l.split()[0] for l in body] == ["[5|5]", "[5|7]", "[4|5]"], body
assert "[5|5] 1 away, 2 AP round trip: Old Door (heavy, defense)" in body[0] and "[4|5] 2 away, 4 AP" in body[2]
assert any("+1 more zone at 4-4 away" in l for l in nb) and any(l.startswith("  Heavy items: one per camper") for l in nb)
assert any("d <= 3 with the day's 6 AP; d <= 6" in l for l in nb)
assert "Good nights to fetch (AP to spare for the nearest round trip + 1): 26, 27. With 3 campers, one can fetch while the others upgrade." in nb
assert nb[-1].startswith("For an exact route: find_expedition_path / plan_expedition_supplies with start = the camp (x,y)")
assert nearby_defense_lines(nd, (5, 6), [], 2)[-2].startswith("  +1 more zone") and not any("fetch" in l for l in nearby_defense_lines(nd, (5, 6), [], 2))
assert nearby_defense_lines({"meta": {"day": 26}, "zones": [zn(20, 20, "Old Door")]}, (5, 6)) == []   # beyond 12 moves
# only what a camper can install: no pets, no assembly parts
assert nearby_defense_lines({"meta": {"day": 26}, "zones": [zn(5, 5, "Mangy Dachshund", "Bag of Cement", "Flatpacked Furniture")]}, (5, 6)) == []
assert not any("[5|6]" in l for l in nb)   # the camp zone itself is the pool, not the block

print("camping checks: ok")
