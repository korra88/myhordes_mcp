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
assert "camp bonus +43%: Fata estimate" in out and "hero skill Reclusive 1" in out
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
assert "Fata plan tomorrow night on [8|13]" in tom and "camp bonus +0%: the existing bonus typed in Ann's Fata plan for day 27" in tom
assert "today's count, tomorrow's may differ" in tom
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

print("camping checks: ok")
