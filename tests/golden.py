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
import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden"
FIXTURES = GOLDEN / "fixtures"
OUT = GOLDEN / "out"

# Frozen towns: (folder under towns/, town id). The first is the main one.
# The second one has beta days (4-8, 13) and days archived from the legacy spy page (1-5,
# read by parse.py).
TOWNS = [("s19-autoritares-opium-der-einsiedler", 8299), ("s19-grave-arenas-of-hades", 8212)]
MAIN, OTHER = TOWNS[0][1], TOWNS[1][1]
CLOCK_AFTER_DATA = timedelta(minutes=10)   # "now" = the main town's data time + 10 min

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
# Offline run
# ---------------------------------------------------------------------------

def _fixture_raw(towns_dir: Path, town: int, day: int | None) -> dict | None:
    for folder, tid in TOWNS:
        if tid != town:
            continue
        cache = towns_dir / folder / "cache"
        if day is None:
            day = json.loads((cache / "_meta.json").read_text())["current_day"]
        for name in (f"day-{day:02d}.towndata.json.gz", f"day-{day:02d}.towndata.live.json.gz"):
            if (cache / name).exists():
                return json.loads(gzip.decompress((cache / name).read_bytes()))
    return None


def _install_fakes(towns_dir: Path) -> None:
    """Point the archive at the temporary copy and serve every HTTP request from fixtures."""
    import httpx

    class FakeResponse:
        def __init__(self, url: str, status: int, body: str):
            self.status_code, self.text = status, body
            self.request = httpx.Request("GET", url)

        def json(self):
            return json.loads(self.text)

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("fixture", request=self.request, response=self)

    async def fake_get(self, url, params=None, **kw):
        if "fatamorgana" in str(url):
            raw = _fixture_raw(towns_dir, int(params["town"]), params.get("day"))
            return FakeResponse(url, 200, json.dumps(raw)) if raw else FakeResponse(url, 404, "")
        if "gesthordes" in str(url):   # recorded for the main town only: others get a 404
            f = FIXTURES / "gesthordes.json"
            ok = str(url).rstrip("/").endswith(f"/{MAIN}") and f.exists()
            return FakeResponse(url, 200, f.read_text()) if ok else FakeResponse(url, 404, "")
        raise httpx.ConnectError(f"offline test: {url}")

    httpx.AsyncClient.get = fake_get


def _frozen_now(towns_dir: Path) -> datetime:
    from myhordes_mcp.fata.towndata import _game_time
    from myhordes_mcp.utils.clock import data_datetime
    raw = _fixture_raw(towns_dir, MAIN, None)
    dt = data_datetime({"data_time": _game_time(raw["town_info"].get("last_game_update"))})
    return dt + CLOCK_AFTER_DATA


def _tree(root: Path) -> dict[str, tuple[int, int]]:
    """{relative path: (size, mtime_ns)} of every file under root."""
    return {str(f.relative_to(root)): (f.stat().st_size, f.stat().st_mtime_ns)
            for f in root.rglob("*") if f.is_file()}


def _manifest(towns_dir: Path) -> str:
    """Every file the run left in the temporary towns/: path and a hash of its content
    (decompressed for .gz), so a refactoring of archive/cp/snapshot/townlog writes is checked."""
    lines = []
    for f in sorted(p for p in towns_dir.rglob("*") if p.is_file()):
        data = f.read_bytes()
        if f.suffix == ".gz":
            data = gzip.decompress(data)
        lines.append(f"{f.relative_to(towns_dir)}  {hashlib.sha1(data).hexdigest()[:12]}")
    return "\n".join(lines)


def _tool_schemas(main) -> str:
    """Name, description and input schema of every MCP tool: what the bot sees of them."""
    tools = asyncio.run(main.mcp.list_tools())
    return "\n\n".join(f"## {t.name}\n{t.description}\n{json.dumps(t.inputSchema, indent=1, sort_keys=True)}"
                       for t in sorted(tools, key=lambda t: t.name))


def run_cases(*, full: bool = True) -> dict[str, str]:
    """Run CASES (name, tool, kwargs[, opts]). opts: clock "HH:MM" (same date), env {var: value},
    files {path under towns/: text} written for the case, hide [paths under towns/] moved away
    for the case, townlog True (town log on; the .md files it changed are added to the
    output). full: also the pseudo-cases _files (written files) and _tools (tool schemas)."""
    if not (FIXTURES / "towns").is_dir():
        sys.exit(f"No fixtures in {FIXTURES.relative_to(ROOT)}: run with --freeze first.")
    real_towns = ROOT / "towns"
    before = _tree(real_towns) if real_towns.is_dir() else {}
    tmp = Path(tempfile.mkdtemp(prefix="golden-"))
    towns_dir = tmp / "towns"
    shutil.copytree(FIXTURES / "towns", towns_dir)
    os.environ["TOWN_LOG_AUTO"] = "0"
    os.environ["FATA_CACHE_TTL"] = "0"
    os.environ.pop("LISTENER_USER_ID", None)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    _install_fakes(towns_dir)

    # Patch config and the clock BEFORE anything else imports them, so every module (also
    # one added later with `from ..utils.config import TOWNS_DIR`) gets the temporary paths.
    from myhordes_mcp.utils import clock, config
    real_now = clock.now
    config.TOWNS_DIR = towns_dir
    config.CURRENT_TOWN_FILE = towns_dir / "_current_town"
    config.USER_TOWNS_DIR = towns_dir / "_user_towns"
    config.FATAMORGANA_TOWN_ID = None
    config.TOWN_LOG_AUTO = 0
    now = {}
    clock.now = lambda: now["t"]
    time.time = lambda: now["t"].timestamp()
    now["t"] = day0 = _frozen_now(towns_dir)   # imports the fata package: after the patches

    import main
    from myhordes_mcp.fata import townlog
    leaked = [f"{m.__name__}.{k}" for m in list(sys.modules.values())
              if getattr(m, "__name__", "").startswith(("myhordes_mcp", "main"))
              for k, v in vars(m).items() if isinstance(v, Path) and v == real_towns]
    leaked += [f"{m.__name__}.{k}" for m in list(sys.modules.values())
               if getattr(m, "__name__", "").startswith(("myhordes_mcp", "main"))
               for k, v in vars(m).items() if v is real_now]
    if leaked:
        sys.exit(f"Not patched (real towns/ or real clock): {', '.join(leaked)}")

    def norm(text: str) -> str:
        return text.replace(str(towns_dir), "<towns>").replace(str(tmp), "<tmp>")

    out = {}
    try:
        for name, tool, kwargs, *rest in CASES:
            opts = rest[0] if rest else {}
            if "clock" in opts:
                h, m = map(int, opts["clock"].split(":"))
                now["t"] = day0.replace(hour=h, minute=m)
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
            now["t"] = day0
        if full:
            out["_files"] = _manifest(towns_dir) + "\n"
            out["_tools"] = _tool_schemas(main) + "\n"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    after = _tree(real_towns) if real_towns.is_dir() else {}
    if after != before:
        changed = sorted(set(after.items()) ^ set(before.items()))
        sys.exit(f"The run changed the real towns/ (must never happen): {changed[:5]}")
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
