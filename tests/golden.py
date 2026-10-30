"""Golden-output tests: run every MCP tool offline on a frozen town and compare the text
with the output recorded before. A refactoring must leave every output identical, except
the changes it means to make (then `--update` and review the diff in git... of the goldens,
which stay local: see below).

    python tests/golden.py            check (exit 1 on any difference, a diff is printed)
    python tests/golden.py --update   record the current outputs as the goldens
    python tests/golden.py --freeze   copy the fixture towns from towns/ (and fetch the
                                      Gest'Hordes stats once) into tests/golden/fixtures/

Offline and deterministic: Fata requests are served from the frozen archive files, the
clock and time.time() are fixed, the town log is off, every write goes to a temporary copy.
tests/golden/ holds real town data (player names): it is gitignored, never commit it.
"""

import argparse
import asyncio
import difflib
import gzip
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
]


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
        if "gesthordes" in str(url):
            f = FIXTURES / "gesthordes.json"
            return FakeResponse(url, 200, f.read_text()) if f.exists() else FakeResponse(url, 404, "")
        raise httpx.ConnectError(f"offline test: {url}")

    httpx.AsyncClient.get = fake_get


def _frozen_now(towns_dir: Path) -> datetime:
    from myhordes_mcp.fata.towndata import _game_time
    from myhordes_mcp.utils.clock import data_datetime
    raw = _fixture_raw(towns_dir, MAIN, None)
    dt = data_datetime({"data_time": _game_time(raw["town_info"].get("last_game_update"))})
    return dt + CLOCK_AFTER_DATA


def run_cases() -> dict[str, str]:
    if not (FIXTURES / "towns").is_dir():
        sys.exit(f"No fixtures in {FIXTURES.relative_to(ROOT)}: run with --freeze first.")
    tmp = Path(tempfile.mkdtemp(prefix="golden-"))
    towns_dir = tmp / "towns"
    shutil.copytree(FIXTURES / "towns", towns_dir)
    os.environ["TOWN_LOG_AUTO"] = "0"
    os.environ["FATA_CACHE_TTL"] = "0"
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    _install_fakes(towns_dir)

    import main
    from myhordes_mcp.fata import archive, risk, townlog
    from myhordes_mcp.utils import clock, config

    for mod in (archive, config):
        mod.TOWNS_DIR = towns_dir
    townlog.TOWN_LOG_AUTO = 0
    frozen = _frozen_now(towns_dir)
    clock.now = risk.now = lambda: frozen
    time.time = lambda: frozen.timestamp()

    out = {}
    try:
        for name, tool, kwargs in CASES:
            fn = getattr(main, tool)
            fn = getattr(fn, "fn", fn)
            args = {"town_id": MAIN, **kwargs} if "town_id" in fn.__code__.co_varnames else kwargs
            try:
                res = fn(**args)
                if asyncio.iscoroutine(res):
                    res = asyncio.run(res)
            except Exception as e:   # a crash is an output too: the golden records it
                res = f"EXCEPTION {type(e).__name__}: {e}"
            out[name] = str(res).rstrip("\n") + "\n"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def main_cli() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--update", action="store_true", help="record the current outputs")
    g.add_argument("--freeze", action="store_true", help="copy the fixture towns from towns/")
    ap.add_argument("-k", help="only the cases whose name contains this")
    a = ap.parse_args()
    if a.freeze:
        freeze()
        return 0
    if a.k:
        CASES[:] = [c for c in CASES if a.k in c[0]]
    outputs = run_cases()
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
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable, *sys.argv])
    sys.exit(main_cli())
