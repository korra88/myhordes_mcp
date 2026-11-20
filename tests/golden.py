"""Golden-output tests: run every MCP tool offline on a frozen town and compare the text
with the output recorded before. A refactoring must leave every output identical, except
the changes it means to make (then `--update` and review the diff in git... of the goldens,
which stay local: see below).

    python tests/golden.py            check (exit 1 on any difference, a diff is printed)
    python tests/golden.py --update   record the current outputs as the goldens
    python tests/golden.py --freeze   copy the fixture towns from towns/ (and fetch the
                                      Gest'Hordes stats once) into tests/golden/fixtures/

Offline and deterministic: Fata and Gest'Hordes requests are served from the frozen files,
the clock and time.time() are fixed (patched before the code is imported), the town log is
off except in the townlog cases, every write goes to a temporary copy of towns/ (checked by
the _files pseudo-case); the run stops if a module still sees the real towns/ or clock, or
if the real towns/ changes. --any-seed keeps a random string-hash seed (else pinned to 0).
tests/golden/ holds real town data (player names): it is gitignored, never commit it.
"""

import argparse
import asyncio
import difflib
import json
import os
import shutil
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from offline import frozen_now, manifest, offline   # noqa: E402
GOLDEN = ROOT / "tests" / "golden"
FIXTURES = GOLDEN / "fixtures"
OUT = GOLDEN / "out"

# Frozen towns: (folder under towns/, town id). The first is the main one.
# The second one has beta days (4-8, 13) and days archived from the legacy spy page (1-5,
# read by parse.py).
TOWNS = [("s19-autoritares-opium-der-einsiedler", 8299), ("s19-grave-arenas-of-hades", 8212)]
MAIN, OTHER = TOWNS[0][1], TOWNS[1][1]
CLOCK_AFTER_DATA = timedelta(minutes=10)   # "now" = the main town's data time + 10 min

# Extra fixture, kept outside fixtures/ so `--freeze` never wipes it: a copy of the raw v1.3
# /towndata of town 8299 day 26 (Fata camp plans, camping_upgrade; the frozen towns above are
# v1.2). Hand-copied, not frozen; a case opts in with {"fixture": "v13"}: the folder is copied
# into the temporary towns/ for that case only (so `_files` is unchanged) and the clock moves
# to its data time + 10 min.
V13_DIR = GOLDEN / "fixtures-v13"
V13 = [("s19-camp-plans-v13", 9926)]


def _v13_name(citizen_id: int) -> str:
    """A citizen's name in the V13 fixture: the cases name players by id, so no player name
    sits in this public file."""
    import gzip
    path = V13_DIR / "towns" / V13[0][0] / "cache" / "day-26.towndata.live.json.gz"
    try:
        raw = json.loads(gzip.decompress(path.read_bytes()))
    except OSError:
        return f"citizen-{citizen_id}"   # fixture missing: the case reports it
    return next((c["name"] for c in raw["town_citizens"] if c["citizen_id"] == citizen_id), "?")


DUMP_SHEET = "Water Ration\nBattery\n\nPlastic Bag\nMachete\nBurning Laser Pointer\nTwinoid"

# (name, tool, kwargs). Names are the golden file names: keep them stable.
CASES = [
    ("overview", "get_town_overview", {}),
    ("overview_full", "get_town_overview", {"detail": "full"}),
    ("overview_day6", "get_town_overview", {"day": 6}),
    ("overview_legacy", "get_town_overview", {"town_id": OTHER, "day": 2}),
    ("overview_other", "get_town_overview", {"town_id": OTHER}),
    ("positions", "get_citizen_positions", {}),
    ("cp", "get_citizen_cp", {}),
    ("defense", "get_defense_status", {}),
    ("bank", "get_bank_inventory", {}),
    ("bank_full", "get_bank_inventory", {"detail": "full"}),
    ("bank_legacy", "get_bank_inventory", {"town_id": OTHER, "day": 2}),
    ("bank_other", "get_bank_inventory", {"town_id": OTHER}),
    ("defense_other", "get_defense_status", {"town_id": OTHER}),
    ("build_options_other", "get_build_options", {"town_id": OTHER}),
    ("zones_legacy", "get_zone_details", {"town_id": OTHER, "day": 3}),
    ("buildings", "get_buildings", {}),
    ("buildings_history", "get_buildings", {"mode": "history"}),
    ("buildings_available", "get_buildings", {"mode": "available", "include_resources": True}),
    ("build_options", "get_build_options", {}),
    ("build_options_all", "get_build_options", {"include_resources": True, "include_all": True}),
    ("blueprint_order", "get_blueprint_order", {}),
    ("construction_history", "get_construction_history", {}),
    ("changes_day", "get_town_changes", {"since": "day"}),
    ("night_report", "get_night_report", {}),
    ("night_report_day5", "get_night_report", {"day": 5}),
    ("roster", "get_expedition_roster", {}),
    ("roster_listed", "get_expedition_roster", {"listed": "Korra, Nobody"}),
    ("dump_sheet", "map_bank_to_dump_sheet", {"sheet_items": DUMP_SHEET}),
    ("scout_map", "get_scout_map", {}),
    ("zone_one", "get_zone_details", {"x1": -3, "y1": 8, "x2": -3, "y2": 8}),
    ("zone_area", "get_zone_details", {"x1": -5, "y1": 5, "x2": -1, "y2": 10}),
    ("zone_ap", "get_zone_details", {"x1": -10, "y1": -10, "x2": 10, "y2": 10, "max_ap": 4}),
    ("zones_overview", "get_zone_details", {}),
    ("zone_item", "get_zone_details", {"item": "flatpacked"}),
    ("path", "find_expedition_path", {"x1": 0, "y1": 0, "x2": 1, "y2": -10}),
    ("path_round_steps", "find_expedition_path",
     {"x1": 0, "y1": 0, "x2": 1, "y2": -10, "round_trip": True, "step_table": True, "show_items": True}),
    ("path_waypoints_dig", "find_expedition_path",
     {"x1": 0, "y1": 0, "x2": -3, "y2": 13, "waypoints": "4,-8", "round_trip": True, "dig": True}),
    ("path_party_flash", "find_expedition_path",
     {"x1": 0, "y1": 0, "x2": -3, "y2": 9, "party": "Korra", "escape_items": 1}),
    ("path_party_handle", "find_expedition_path",
     {"x1": 0, "y1": 0, "x2": -3, "y2": 9, "party": "@Korra:394972002051424256"}),
    ("supplies", "plan_expedition_supplies", {"waypoints": "1,-10"}),
    ("supplies_pickup", "plan_expedition_supplies",
     {"waypoints": "1,-10", "pickups": "1,-10: heavy", "available": "water=1, food7=1",
      "guardian": True, "group_cp": 4}),
    ("supplies_scout_steps", "plan_expedition_supplies",
     {"waypoints": "4,-8; 1,-10", "scout": True, "shoes": True, "step_table": True, "second_wind": 2}),
    ("supplies_thirsty", "plan_expedition_supplies",
     {"waypoints": "-3,9", "thirst": "thirsty", "already_ate": True, "available": "water=2"}),
    ("supplies_budget_guard", "plan_expedition_supplies", {"waypoints": "1,-10", "start_ap": 19}),
    ("kill_zoo", "plan_kill_route", {"zoo": True}),
    ("kill_zoo_other", "plan_kill_route", {"town_id": OTHER, "zoo": True}),
    ("kill_strip", "plan_kill_route",
     {"waypoints": "-3,0; -3,9; -2,9; -2,1", "party": "Korra", "available": "water=1, food6=1"}),
    ("kill_edge", "plan_kill_route", {"waypoints": "-3,0; -3,13; -2,13; -2,0", "party": "Korra"}),
    ("kill_kit", "plan_kill_route", {"waypoints": "-3,0; -3,9", "kit": "laser, machete, battery=2"}),
    ("kill_fata_route_day6", "plan_kill_route", {"route": "SpecialAgent3", "day": 6}),
    ("attack_distribution", "get_attack_distribution", {}),
    ("attack_forecast", "get_attack_forecast", {}),
    ("wiki", "search_wiki", {"query": "Machete"}),
    ("wiki_categories", "list_wiki_categories", {}),
    ("knowledge", "search_knowledge", {"query": "heavy defensive relay", "section": "tactics"}),
    # Audit 2026-10-30 (coverage of the refactor-plan targets): way home without / with other
    # platform levels, scout and flash pathing, detours, pickups, boosters, error texts,
    # Fata routes, zone reach, change markers (changes_first then changes_again: keep the order).
    ("path_round_day3_lvl2", "find_expedition_path", {"x1": 0, "y1": 0, "x2": 1, "y2": -10, "round_trip": True, "day": 3}),
    ("path_round_day1_nolevel", "find_expedition_path", {"x1": 0, "y1": 0, "x2": 1, "y2": -5, "round_trip": True, "day": 1}),
    ("path_round_other_day4_lvl3", "find_expedition_path", {"town_id": OTHER, "x1": 0, "y1": 0, "x2": 3, "y2": -4, "round_trip": True, "day": 4}),
    ("path_round_near_teleport", "find_expedition_path", {"x1": 0, "y1": 0, "x2": 1, "y2": 1, "round_trip": True}),
    ("path_round_offtown", "find_expedition_path", {"x1": 1, "y1": -5, "x2": 4, "y2": -8, "round_trip": True}),
    ("path_scout_mode", "find_expedition_path", {"x1": 0, "y1": 0, "x2": -5, "y2": 7, "scout_mode": True, "group_cp": 1}),
    ("path_dehydrated_steps", "find_expedition_path", {"x1": 0, "y1": 0, "x2": -9, "y2": 13, "step_table": True, "thirst_counter": 25, "start_ep": 2}),
    ("path_unknown_dest", "find_expedition_path", {"x1": 0, "y1": 0, "x2": 14, "y2": 13}),
    ("path_bad_waypoint", "find_expedition_path", {"x1": 0, "y1": 0, "x2": 1, "y2": -5, "waypoints": "abc"}),
    ("path_party_unknown", "find_expedition_path", {"x1": 0, "y1": 0, "x2": -3, "y2": 9, "party": "Korra, Nobody"}),
    ("supplies_detour", "plan_expedition_supplies", {"waypoints": "-5,7"}),
    ("supplies_detour_free", "plan_expedition_supplies", {"waypoints": "-5,6"}),
    ("supplies_dehydrated", "plan_expedition_supplies", {"waypoints": "-3,9", "thirst": "dehydrated", "available": "water=1"}),
    ("supplies_dig", "plan_expedition_supplies", {"waypoints": "4,-8; 1,-10", "dig": True}),
    ("supplies_offtown", "plan_expedition_supplies", {"start": "1,-5", "waypoints": "4,-8"}),
    ("supplies_oneway", "plan_expedition_supplies", {"waypoints": "-3,9", "round_trip": False}),
    ("supplies_two_heavy_guardian", "plan_expedition_supplies", {"waypoints": "1,-5; 4,-3", "pickups": "1,-5: heavy; 4,-3: heavy", "guardian": True, "group_cp": 4}),
    ("supplies_two_heavy_trolley", "plan_expedition_supplies", {"waypoints": "1,-5; 4,-3", "pickups": "1,-5: heavy; 4,-3: heavy", "trolley": True}),
    ("supplies_three_heavy", "plan_expedition_supplies", {"waypoints": "1,-5", "pickups": "1,-5: 3 heavy", "guardian": True}),
    ("supplies_far_default", "plan_expedition_supplies", {"waypoints": "-9,13"}),
    ("supplies_boosters_given", "plan_expedition_supplies", {"waypoints": "-7,10", "available": "water=2, food7=1, alcohol=1, twinoid=1, coffee=1", "drug_taken_today": False}),
    ("supplies_sw4_wounded", "plan_expedition_supplies", {"waypoints": "-7,10", "second_wind": 4, "wounded": True, "drunk_or_hungover": True}),
    ("supplies_err_thirst", "plan_expedition_supplies", {"waypoints": "1,-10", "thirst": "very"}),
    ("supplies_err_item", "plan_expedition_supplies", {"waypoints": "1,-10", "available": "water=x"}),
    ("supplies_err_item2", "plan_expedition_supplies", {"waypoints": "1,-10", "available": "pizza=1"}),
    ("supplies_err_sw", "plan_expedition_supplies", {"waypoints": "1,-10", "second_wind": 5}),
    ("supplies_err_slots", "plan_expedition_supplies", {"waypoints": "1,-10", "slots": 0}),
    ("supplies_err_pickup", "plan_expedition_supplies", {"waypoints": "1,-10", "pickups": "4,-8: heavy"}),
    ("supplies_err_pickup_fmt", "plan_expedition_supplies", {"waypoints": "1,-10", "pickups": "1,-10 heavy"}),
    ("supplies_err_zone", "plan_expedition_supplies", {"waypoints": "1;-10"}),
    ("supplies_err_only_start", "plan_expedition_supplies", {"waypoints": "0,0"}),
    ("kill_to_town", "plan_kill_route", {"waypoints": "-3,0; -3,9; -2,9; -2,1; 0,0", "party": "Korra"}),
    ("kill_other_day4", "plan_kill_route", {"town_id": OTHER, "waypoints": "3,0; 3,-6", "day": 4}),
    ("kill_day2_to_town", "plan_kill_route", {"waypoints": "-3,0; -3,4; 0,0", "day": 2}),
    ("kill_sw_repair", "plan_kill_route", {"waypoints": "-3,0; -3,9", "kit": "laser3, machete, knife, repair, water", "second_wind": 3, "slots": 4}),
    ("kill_zoo_day1", "plan_kill_route", {"zoo": True, "day": 1}),
    ("kill_route_unknown", "plan_kill_route", {"route": "Nope"}),
    ("kill_route_many", "plan_kill_route", {"route": "Bacchus"}),
    ("kill_route_legacy", "plan_kill_route", {"town_id": OTHER, "route": "x", "day": 2}),
    ("kill_err_both", "plan_kill_route", {"route": "OBE", "waypoints": "1,1"}),
    ("kill_err_kit", "plan_kill_route", {"waypoints": "-3,0", "kit": "sword"}),
    ("kill_err_kit_count", "plan_kill_route", {"waypoints": "-3,0", "kit": "battery=two"}),
    ("kill_err_slots", "plan_kill_route", {"waypoints": "-3,0", "slots": 0}),
    ("kill_err_sw", "plan_kill_route", {"waypoints": "-3,0", "second_wind": 9}),
    ("kill_err_budget", "plan_kill_route", {"waypoints": "-3,0", "start_ap": 19}),
    ("path_err_budget", "find_expedition_path", {"x1": 0, "y1": 0, "x2": 2, "y2": 2, "start_ap": 19}),
    ("zone_reach_near", "get_zone_details", {"x1": 1, "y1": 1, "x2": 1, "y2": 1}),
    ("zone_reach_nobuild", "get_zone_details", {"town_id": OTHER, "day": 1, "x1": 1, "y1": 0, "x2": 1, "y2": 0}),
    ("zone_reach_lvl1", "get_zone_details", {"day": 2, "x1": 1, "y1": 0, "x2": 1, "y2": 0}),
    ("zone_reach_closed", "get_zone_details", {"town_id": OTHER, "day": 4, "x1": 1, "y1": 1, "x2": 1, "y2": 1}),
    ("zone_item_none", "get_zone_details", {"item": "unobtainium"}),
    ("zone_item_many", "get_zone_details", {"item": "log"}),
    ("zone_empty_box", "get_zone_details", {"x1": 30, "y1": 30, "x2": 31, "y2": 31}),
    ("scout_map_other", "get_scout_map", {"town_id": OTHER}),
    ("overview_missing_day", "get_town_overview", {"day": 4}),
    ("cp_other", "get_citizen_cp", {"town_id": OTHER}),
    ("night_day1", "get_night_report", {"day": 1}),
    ("night_future", "get_night_report", {"day": 9}),
    ("night_other_legacy", "get_night_report", {"town_id": OTHER, "day": 3}),
    ("night_other", "get_night_report", {"town_id": OTHER}),
    ("changes_first", "get_town_changes", {}),
    ("changes_again", "get_town_changes", {}),
    ("changes_since", "get_town_changes", {"since": "09:00"}),
    ("changes_other", "get_town_changes", {"town_id": OTHER}),
    ("roster_other", "get_expedition_roster", {"listed": "Nobody, GhostX", "town_id": OTHER}),
    ("buildings_bad_mode", "get_buildings", {"mode": "nope"}),
    ("buildings_other_history", "get_buildings", {"town_id": OTHER, "mode": "history"}),
    ("blueprint_other", "get_blueprint_order", {"town_id": OTHER}),
    ("history_other", "get_construction_history", {"town_id": OTHER}),
    ("positions_other_day1", "get_citizen_positions", {"town_id": OTHER, "day": 1}),
    ("overview_other_day5_full", "get_town_overview", {"town_id": OTHER, "day": 5, "detail": "full"}),
    ("bank_day1", "get_bank_inventory", {"day": 1}),
    ("dump_other_empty", "map_bank_to_dump_sheet", {"sheet_items": "\n\n", "town_id": OTHER}),
    ("dump_dupes", "map_bank_to_dump_sheet", {"sheet_items": "Water Ration\nwater ration\nBattery\nLog"}),
    ("defense_day1", "get_defense_status", {"day": 1}),
    ("path_flash", "find_expedition_path", {"x1": 0, "y1": 0, "x2": -3, "y2": 7, "escape_items": 2, "step_table": True}),
    ("supplies_pickup_kinds", "plan_expedition_supplies", {"waypoints": "4,-3; 1,-5; 1,-10", "pickups": "4,-3: defense; 1,-5: projector; 1,-10: 2 battery", "guardian": True, "slots": 3}),
    ("kill_other_respawn", "plan_kill_route", {"town_id": OTHER, "waypoints": "1,0; 1,-3"}),
    ("kill_day2_loop", "plan_kill_route", {"waypoints": "-3,0; -3,4", "day": 2}),
    # Plans made with more than the player gave: "Not feasible as asked" first.
    ("supplies_asked_short", "plan_expedition_supplies", {"waypoints": "-3,0; -3,9; -2,9; -2,1", "start_ap": 6, "available": "water=1, food6=1"}),
    ("supplies_asked_dies", "plan_expedition_supplies", {"waypoints": "-3,9", "thirst_counter": 30, "thirst": "dehydrated", "available": "food7=1"}),
    ("supplies_asked_slots", "plan_expedition_supplies", {"waypoints": "-3,9", "slots": 2}),
    ("supplies_asked_pickup_slots", "plan_expedition_supplies", {"waypoints": "1,-5; 1,-10", "pickups": "1,-5: heavy; 1,-10: 2 battery", "available": "water=1, food6=1", "slots": 3}),
    ("supplies_asked_ok", "plan_expedition_supplies", {"waypoints": "-3,9", "available": "water=2, food7=1, steroid=1"}),
    # Evening (alerts), estimations rebuilt from the archive, town log writing, a repeat
    # after other towns and days (no stale cache across them).
    ("overview_evening", "get_town_overview", {}, {"clock": "23:10"}),
    ("defense_evening", "get_defense_status", {}, {"clock": "23:10"}),
    ("positions_evening", "get_citizen_positions", {}, {"clock": "23:10"}),
    ("overview_noest", "get_town_overview", {}, {"hide": [f"{TOWNS[0][0]}/cache/estimations.json"]}),
    ("defense_other_noest", "get_defense_status", {"town_id": OTHER},
     {"hide": [f"{TOWNS[1][0]}/cache/estimations.json"]}),
    ("townlog_first", "get_town_overview", {}, {"townlog": True}),
    ("townlog_again", "get_town_overview", {}, {"townlog": True}),
    ("path_round_steps_repeat", "find_expedition_path",
     {"x1": 0, "y1": 0, "x2": 1, "y2": -10, "round_trip": True, "step_table": True, "show_items": True}),
    # Which town: town_id=0 resolves the default (user file, current-town file, none).
    ("town_current_file", "get_town_overview", {"town_id": 0}, {"files": {"_current_town": f"{OTHER}\n"}}),
    ("town_user_file", "get_bank_inventory", {"town_id": 0},
     {"env": {"LISTENER_USER_ID": "123"}, "files": {"_user_towns/123": str(OTHER), "_current_town": str(MAIN)}}),
    ("town_user_file_bad", "get_bank_inventory", {"town_id": 0},
     {"env": {"LISTENER_USER_ID": "123"}, "files": {"_user_towns/123": "../x"}}),
    ("town_current_file_bad", "get_bank_inventory", {"town_id": 0}, {"files": {"_current_town": "abc"}}),
]

# Every tool through its "no town" and "no such day" branches (the shared preamble, A8).
_REQUIRED = {"map_bank_to_dump_sheet": {"sheet_items": "Water Ration"},
             "find_expedition_path": {"x1": 0, "y1": 0, "x2": 1, "y2": -5},
             "plan_expedition_supplies": {"waypoints": "1,-5"}}
_TOWN_TOOLS = ["get_bank_inventory", "get_town_overview", "get_citizen_positions", "get_citizen_cp",
               "get_defense_status", "get_buildings", "get_build_options", "get_blueprint_order",
               "get_construction_history", "get_town_changes", "get_night_report", "get_expedition_roster",
               "map_bank_to_dump_sheet", "get_scout_map", "find_expedition_path", "plan_expedition_supplies",
               "plan_kill_route", "get_zone_details", "get_attack_distribution", "get_attack_forecast"]
_DAY_TOOLS = ["get_bank_inventory", "get_town_overview", "get_citizen_positions", "get_defense_status",
              "get_buildings", "get_scout_map", "find_expedition_path", "plan_kill_route", "get_zone_details"]
# Name lookup (exact / unique prefix / unique substring / ambiguous), at each lookup site.
CASES += [
    ("kill_route_exact", "plan_kill_route", {"route": "ivana", "day": 6}),
    ("kill_route_prefix", "plan_kill_route", {"route": "Skip", "day": 6}),
    ("kill_route_substring", "plan_kill_route", {"route": "Agent2", "day": 6}),
    ("kill_route_ambiguous", "plan_kill_route", {"route": "SpecialAgent", "day": 6}),
    ("kill_route_ambiguous_sub", "plan_kill_route", {"route": "agent", "day": 6}),
    ("kill_route_duplicate", "plan_kill_route", {"route": "Ammonia", "day": 6}),
    ("kill_route_none", "plan_kill_route", {"route": "zzzz", "day": 6}),
    ("supplies_pickup_name_exact", "plan_expedition_supplies", {"waypoints": "1,-5", "pickups": "1,-5: Rotting Log"}),
    ("supplies_pickup_name_prefix", "plan_expedition_supplies", {"waypoints": "1,-5", "pickups": "1,-5: scrap"}),
    ("supplies_pickup_name_substring", "plan_expedition_supplies", {"waypoints": "1,-5", "pickups": "1,-5: projector"}),
    ("supplies_pickup_name_ambiguous", "plan_expedition_supplies", {"waypoints": "1,-5", "pickups": "1,-5: in"}),
    ("dump_lookup", "map_bank_to_dump_sheet",
     {"sheet_items": "Battery\nUnshaped Concre\nOverhead Proj\netal\nWater P\nzzz\nWater Ration"}),
]
# Fata camp plans and camp-level estimates (v1.3 fixture, see V13): zone from the citizen's
# own plan, plan values as defaults, explicit arguments winning, two plans on one zone.
CASES += [
    ("v13_camping_citizen_plan", "get_camping_odds", {"town_id": V13[0][1], "citizen": "Korra"}, {"fixture": "v13"}),
    ("v13_camping_two_plans_zone", "get_camping_odds", {"town_id": V13[0][1], "x": 7, "y": -13}, {"fixture": "v13"}),
    ("v13_camping_override", "get_camping_odds",
     {"town_id": V13[0][1], "x": 7, "y": -13, "citizen": _v13_name(38242), "skill": "reclusive4", "nights": 2,
      "camp_level": 10}, {"fixture": "v13"}),
    ("v13_camping_fata_level_plan", "get_camping_odds",
     {"town_id": V13[0][1], "x": 10, "y": -8, "citizen": _v13_name(154), "ap": 2, "defense_items": 1}, {"fixture": "v13"}),
    ("v13_camping_cap_ap", "get_camping_odds",
     {"town_id": V13[0][1], "citizen": "Korra", "ap": 6, "defense_items": 1}, {"fixture": "v13"}),
    ("v13_camping_tomorrow", "get_camping_odds",
     {"town_id": V13[0][1], "citizen": "Korra", "day": 27, "camp_level": 0, "ap": 6, "defense_items": 1}, {"fixture": "v13"}),
    ("v13_camping_tomorrow_estimate", "get_camping_odds",
     {"town_id": V13[0][1], "x": 10, "y": -8, "citizen": _v13_name(154), "day": 27, "ap": 2, "defense_items": 1}, {"fixture": "v13"}),
    ("v13_camping_past_day", "get_camping_odds",
     {"town_id": V13[0][1], "citizen": "Korra", "day": 20}, {"fixture": "v13"}),
    ("v13_positions", "get_citizen_positions", {"town_id": V13[0][1]}, {"fixture": "v13"}),
]
# Group camping planner (plan_group_camping, docs/group-camping-plan.md) on the same fixture: the
# Fata plan's group tonight, tomorrow with overrides, a Tamer with a steak, an AP-limited group,
# and a five-camper plan group with floor items and spare AP.
_G3 = f"{_v13_name(5325)}:R4:n2, {_v13_name(35153)}:R2:n2"
CASES += [
    ("v13_group_tonight", "plan_group_camping",
     {"town_id": V13[0][1], "group": f"Korra, {_v13_name(5325)}, {_v13_name(35153)}"}, {"fixture": "v13"}),
    ("v13_group_tomorrow", "plan_group_camping",
     {"town_id": V13[0][1], "group": f"Korra:R2:n2, {_G3}", "day": 27, "camp_level": 0}, {"fixture": "v13"}),
    ("v13_group_tamer_steak", "plan_group_camping",
     {"town_id": V13[0][1], "x": 14, "y": 13, "day": 27, "camp_level": 0, "steaks": 1,
      "group": f"Korra:tamer:n3:none, {_v13_name(5325)}:R4:n3, {_v13_name(35153)}:R2:n3"}, {"fixture": "v13"}),
    ("v13_group_ap_limited", "plan_group_camping",
     {"town_id": V13[0][1], "x": 14, "y": 13, "day": 27, "camp_level": 0, "ap": 3, "defense_items": 1,
      "group": f"Korra:n4:none, {_v13_name(5325)}:R4:n3, {_v13_name(35153)}:R2:n4"}, {"fixture": "v13"}),
    ("v13_group_plan_zone_carry", "plan_group_camping",
     {"town_id": V13[0][1], "x": 10, "y": -8, "ap": 4, "defense_items": 1}, {"fixture": "v13"}),
    ("v13_group_err_zones", "plan_group_camping", {"town_id": V13[0][1]}, {"fixture": "v13"}),
]
# Multi-night chain (docs/camping-multinight-plan.md): three campers with finite defensive items and
# nearby items, the five-camper plan zone (Fata plan upgrades counted, AP per night), the errors.
CASES += [
    ("v13_group_multinight", "plan_group_camping",
     {"town_id": V13[0][1], "x": 14, "y": 13, "day": 26, "until_day": 29, "camp_level": 0, "ap": 6, "defense_items": 2,
      "group": f"Korra:R2:n2, {_G3}"}, {"fixture": "v13"}),
    ("v13_group_multinight_plan_zone", "plan_group_camping",
     {"town_id": V13[0][1], "x": 10, "y": -8, "day": 26, "until_day": 28, "ap": 6}, {"fixture": "v13"}),
    ("v13_group_multinight_unlimited_ap", "plan_group_camping",
     {"town_id": V13[0][1], "x": 14, "y": 13, "day": 27, "until_day": 31, "camp_level": 0,
      "group": f"Korra:n4:none, {_v13_name(5325)}:R4:n3, {_v13_name(35153)}:R2:n4"}, {"fixture": "v13"}),
    ("v13_group_err_until_before", "plan_group_camping",
     {"town_id": V13[0][1], "x": 14, "y": 13, "day": 27, "until_day": 26}, {"fixture": "v13"}),
    ("v13_group_err_too_many_nights", "plan_group_camping",
     {"town_id": V13[0][1], "x": 14, "y": 13, "until_day": 40}, {"fixture": "v13"}),
]
# Camping odds (rules verified in the game source: docs/camping-plan.md section 1.2).
CASES += [
    ("camping_ruin_plan", "get_camping_odds",
     {"x": 1, "y": -5, "skill": "reclusive4", "camp_level": 0, "nights": 1, "ap": 6, "defense_items": 2}),
    ("camping_ruin_odds_only", "get_camping_odds", {"x": 1, "y": -5, "nights": 0, "camp_level": 10}),
    ("camping_buried_ruin", "get_camping_odds", {"x": 0, "y": 7, "ap": 4, "defense_items": 1, "hidden_before": 1}),
    ("camping_no_ruin_citizen", "get_camping_odds",
     {"x": -3, "y": 9, "citizen": "korra", "ap": 8, "defense_items": 3, "camp_items": 1, "hidden_before": 2}),
    ("camping_citizen_position", "get_camping_odds", {"citizen": "Korra", "ap": 2}),
    ("camping_other_town_procamp", "get_camping_odds",
     {"town_id": OTHER, "x": 2, "y": -3, "skill": "procamp", "nights": 7, "tomb": True, "vest": True}),
    ("camping_err_zone", "get_camping_odds", {}),
    ("camping_err_town", "get_camping_odds", {"x": 0, "y": 0}),
    ("camping_err_skill", "get_camping_odds", {"x": 1, "y": 1, "skill": "ninja"}),
    ("camping_err_citizen", "get_camping_odds", {"x": 1, "y": 1, "citizen": "Nobody"}),
]
CASES += [(f"notown_{t}", t, {"town_id": 0, **_REQUIRED.get(t, {})}) for t in _TOWN_TOOLS]
CASES += [(f"noday_{t}", t, {"day": 4, **_REQUIRED.get(t, {})}) for t in _DAY_TOOLS]


# ---------------------------------------------------------------------------
# Freeze: copy the fixture towns
# ---------------------------------------------------------------------------

def freeze() -> None:
    if FIXTURES.exists():
        shutil.rmtree(FIXTURES)
    for folder, _ in TOWNS:
        src = ROOT / "towns" / folder
        dst = FIXTURES / "towns" / folder
        shutil.copytree(src / "cache", dst / "cache", ignore=shutil.ignore_patterns("*.html"))
        for f in ("citizens-cp.json",):
            if (src / f).exists():
                shutil.copy2(src / f, dst / f)
    sys.path.insert(0, str(ROOT / "src"))
    from myhordes_mcp.gesthordes.client import _fetch   # one request, on the user's command
    stats = asyncio.run(_fetch(MAIN))
    if "error" in stats:
        sys.exit(f"Gest'Hordes: {stats['error']}")
    (FIXTURES / "gesthordes.json").write_text(json.dumps(stats), encoding="utf-8")
    print(f"Frozen {len(TOWNS)} towns and Gest'Hordes stats into {FIXTURES.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Offline run (the harness is in tests/offline.py)
# ---------------------------------------------------------------------------

def _tool_schemas(main) -> str:
    """Name, description and input schema of every MCP tool: what the bot sees of them."""
    tools = asyncio.run(main.mcp.list_tools())
    return "\n\n".join(f"## {t.name}\n{t.description}\n{json.dumps(t.inputSchema, indent=1, sort_keys=True)}"
                       for t in sorted(tools, key=lambda t: t.name))


def run_cases(*, full: bool = True) -> dict[str, str]:
    """Run CASES (name, tool, kwargs[, opts]). opts: clock "HH:MM" (same date), env {var: value},
    files {path under towns/: text} written for the case, fixture "v13" (the V13 town copied in,
    clock set to its data time + 10 min), hide [paths under towns/] moved away
    for the case, townlog True (town log on; the .md files it changed are added to the
    output). full: also the pseudo-cases _files (written files) and _tools (tool schemas)."""
    with offline(FIXTURES, TOWNS + V13, MAIN, clock_after=CLOCK_AFTER_DATA, prefix="golden-") as run:
        return _run_cases(run, full)


def _run_cases(run, full: bool) -> dict[str, str]:
    main, towns_dir, tmp, now, day0 = run.main, run.towns_dir, run.tmp, run.now, run.day0
    from myhordes_mcp.fata import camplog, townlog
    camplog.AUTO = 1   # the camping log runs in every case (it is off where TOWN_LOG_AUTO=0)

    def norm(text: str) -> str:
        return text.replace(str(towns_dir), "<towns>").replace(str(tmp), "<tmp>")

    out = {}
    for name, tool, kwargs, *rest in CASES:
        opts = rest[0] if rest else {}
        if "clock" in opts:
            h, m = map(int, opts["clock"].split(":"))
            now["t"] = day0.replace(hour=h, minute=m)
        if opts.get("fixture") == "v13":
            for folder, _ in V13:
                shutil.copytree(V13_DIR / "towns" / folder, towns_dir / folder)
            now["t"] = frozen_now(towns_dir, V13, V13[0][1], CLOCK_AFTER_DATA)
        env_old = {k: os.environ.get(k) for k in opts.get("env", {})}
        os.environ.update(opts.get("env", {}))
        for rel, text in opts.get("files", {}).items():
            (towns_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (towns_dir / rel).write_text(text, encoding="utf-8")
        hidden = []
        for rel in opts.get("hide", []):
            if (towns_dir / rel).exists():
                hidden.append(rel)
                (towns_dir / rel).rename(towns_dir / (rel + ".hidden"))
        logs_before = {f: f.read_text() for f in towns_dir.rglob("*.md")}
        townlog.TOWN_LOG_AUTO = 1 if opts.get("townlog") else 0
        fn = getattr(main, tool)
        fn = getattr(fn, "fn", fn)
        args = {"town_id": MAIN, **kwargs} if "town_id" in fn.__code__.co_varnames else kwargs
        try:
            res = fn(**args)
            if asyncio.iscoroutine(res):
                res = asyncio.run(res)
        except Exception as e:   # a crash is an output too: the golden records it
            res = f"EXCEPTION {type(e).__name__}: {e}"
        res = str(res).rstrip("\n")
        if opts.get("townlog"):
            for f in sorted(towns_dir.rglob("*.md")):
                if logs_before.get(f) != (text := f.read_text()):
                    res += f"\n\n--- {f.relative_to(towns_dir)} ---\n" + text.rstrip("\n")
        out[name] = norm(res) + "\n"
        townlog.TOWN_LOG_AUTO = 0
        for rel in hidden:
            (towns_dir / (rel + ".hidden")).rename(towns_dir / rel)
        for rel in opts.get("files", {}):
            (towns_dir / rel).unlink(missing_ok=True)
        for k, v in env_old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if opts.get("fixture") == "v13":
            for folder, _ in V13:
                shutil.rmtree(towns_dir / folder)
        now["t"] = day0
    if full:
        out["_files"] = manifest(towns_dir) + "\n"
        out["_tools"] = _tool_schemas(main) + "\n"
    return out


def main_cli() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--update", action="store_true", help="record the current outputs")
    g.add_argument("--freeze", action="store_true", help="copy the fixture towns from towns/")
    ap.add_argument("-k", help="only the cases whose name contains this")
    ap.add_argument("--any-seed", action="store_true",
                    help="keep this process's string-hash seed (finds set-order leaks; else pinned to 0)")
    a = ap.parse_args()
    if a.freeze:
        freeze()
        return 0
    if a.k:
        CASES[:] = [c for c in CASES if a.k in c[0]]
    outputs = run_cases(full=not a.k)
    if a.update:
        OUT.mkdir(parents=True, exist_ok=True)
        for name, text in outputs.items():
            (OUT / f"{name}.txt").write_text(text, encoding="utf-8")
        print(f"Recorded {len(outputs)} goldens in {OUT.relative_to(ROOT)}")
        return 0
    failed, missing = [], []
    for name, text in outputs.items():
        f = OUT / f"{name}.txt"
        if not f.exists():
            missing.append(name)
            continue
        old = f.read_text(encoding="utf-8")
        if old != text:
            failed.append(name)
            sys.stdout.writelines(difflib.unified_diff(
                old.splitlines(True), text.splitlines(True), f"golden/{name}", f"now/{name}", n=1))
    print(f"\n{len(outputs) - len(failed) - len(missing)} same, {len(failed)} different"
          + (f": {', '.join(failed)}" if failed else "")
          + (f", {len(missing)} without golden: {', '.join(missing)}" if missing else ""))
    return 1 if failed or missing else 0


if __name__ == "__main__":
    # String hashing is salted per process: pin it, or set order leaks into the output
    # (refactor-plan: ties sorted by name would make this unnecessary).
    if os.environ.get("PYTHONHASHSEED") != "0" and "--any-seed" not in sys.argv:
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable, *sys.argv])
    sys.exit(main_cli())
