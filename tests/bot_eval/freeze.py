"""Freeze one bot-evaluation fixture: the /towndata days a scenario needs, copied into
towns/_eval/fixtures/<fixture-id>/towns/<slug>/ (layout: docs/bot-eval-plan.md 5.1).

    .venv/bin/python tests/bot_eval/freeze.py 7365-d22 --town 7365 --day 22 --with-day 21 \
        [--source DIR ...] [--inject-note TEXT]

For each (town, day) the sources are tried in this order, and Fata is asked only when
none has the day:
  a. towns/<slug>/cache/day-NN.towndata[.live].json.gz   (the live archive, read only)
  b. every --source DIR (a folder laid out like towns/: <slug>/cache/...)
  c. one request through fata.client.fetch_town_data(T, day=N), with config.TOWNS_DIR
     pointed at the fixture folder so nothing is written to the live towns/.
Every request is printed and counted; none is made between 23:50 and 00:10 Paris time.
The scenario's day (--day) becomes the fixture's current day: _meta.json current_day,
and its file is named `.live.` so tool headers show an age.
--inject-note replaces the first non-empty map note by TEXT (synthetic prompt-injection fixture).
No Gest'Hordes request is made here.
"""

import argparse
import asyncio
import gzip
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent.parent
REAL_TOWNS = ROOT / "towns"
FIXTURES = REAL_TOWNS / "_eval" / "fixtures"


def day_file(cache: Path, day: int) -> Path | None:
    """The stored /towndata of a day in a cache/ folder (final first, then live)."""
    for suffix in (".towndata.json.gz", ".towndata.live.json.gz"):
        f = cache / f"day-{day:02d}{suffix}"
        if f.exists():
            return f
    return None


def find_town_dirs(root: Path, town: int) -> list[Path]:
    """Town folders of a towns/-like tree whose cache/_meta.json has this town id."""
    found = []
    if root.is_dir():
        for d in sorted(root.iterdir()):
            try:
                meta = json.loads((d / "cache" / "_meta.json").read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not d.name.startswith("_") and meta.get("town_id") == town:
                found.append(d)
    return found


def read_gz(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def write_gz(path: Path, raw: dict) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)


def data_cutoff(raw: dict) -> int:
    """Epoch time of the newest data in a /towndata day: the last game update or the last
    zone update, whichever is later (zone updates can follow the game update: town 6741
    day 30, a zone at 21:47:33 UTC after a game update at 21:42:21)."""
    lu = raw["town_info"].get("last_game_update")
    times = [int(datetime.fromisoformat(lu).timestamp())] if lu else []
    times += [(m.get("zone_update") or {}).get("time") or 0 for m in raw.get("town_maps", [])]
    return max(times, default=0)


def cut_cp_log(log: dict, cutoff: int) -> dict:
    """The CP log as it stood at `cutoff` (epoch s): readings and groups after it are
    dropped and last/max recomputed, so a fixture never sees later days (the live log is
    copied from the town folder, which keeps growing)."""
    citizens = {}
    for cid, e in log.get("citizens", {}).items():
        readings = [r for r in e.get("readings", []) if r["time"] <= cutoff]
        old_max = e.get("max")
        cands = readings + ([old_max] if old_max and old_max["time"] <= cutoff else [])
        if not cands:
            continue
        kept = {k: v for k, v in e.items() if k not in ("readings", "last", "max")}
        kept["readings"] = readings
        kept["last"] = readings[-1] if readings else old_max
        kept["max"] = max(cands, key=lambda r: (r["cp"], r["time"]))
        citizens[cid] = kept
    groups = [g for g in log.get("groups", []) if g["time"] <= cutoff]
    return {**log, "citizens": citizens, "groups": groups, "updated": cutoff}


def check_clock() -> None:
    now = datetime.now(ZoneInfo("Europe/Paris"))
    minutes = now.hour * 60 + now.minute
    if minutes >= 23 * 60 + 50 or minutes <= 10:
        sys.exit(f"Refusing to ask Fata at {now:%H:%M} Paris time (nightly attack, 23:50-00:10).")


def fetch_from_fata(town: int, day: int, dest_towns: Path) -> Path:
    """One request, archived under dest_towns. Returns the saved day file."""
    check_clock()
    os.environ["TOWN_LOG_AUTO"] = "0"
    os.environ["FATA_CACHE_TTL"] = "0"
    sys.path.insert(0, str(ROOT / "src"))
    from myhordes_mcp.utils import config
    config.TOWNS_DIR = dest_towns
    import myhordes_mcp.fata.client as client
    for mod in list(sys.modules.values()):
        if getattr(mod, "__name__", "").startswith("myhordes_mcp"):
            for k, v in list(vars(mod).items()):
                if isinstance(v, Path) and v == REAL_TOWNS:
                    setattr(mod, k, dest_towns)
    dest_towns.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(client.fetch_town_data(town, day=day))
    if result.get("error"):
        sys.exit(f"Fata request town={town} day={day} failed: {result['error']}")
    for d in find_town_dirs(dest_towns, town):
        f = day_file(d / "cache", day)
        if f:
            return f
    sys.exit(f"Fata answered for town={town} day={day} but nothing was archived.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixture_id")
    ap.add_argument("--town", type=int, required=True)
    ap.add_argument("--day", type=int, required=True, help="the scenario's day (fixture current day)")
    ap.add_argument("--with-day", type=int, action="append", default=[], metavar="M",
                    help="earlier day to include (night report, changes); repeatable")
    ap.add_argument("--source", type=Path, action="append", default=[], metavar="DIR",
                    help="extra folder laid out like towns/, tried after the live archive; repeatable")
    ap.add_argument("--inject-note", metavar="TEXT", help="replace the first map note by TEXT (synthetic)")
    args = ap.parse_args()

    fixture = FIXTURES / args.fixture_id
    if fixture.exists():
        sys.exit(f"{fixture} exists; remove it first.")
    roots = [REAL_TOWNS] + [p.resolve() for p in args.source]
    days = sorted(set(args.with_day) | {args.day})
    work = fixture.with_name(fixture.name + ".tmp")
    shutil.rmtree(work, ignore_errors=True)
    dest_towns = work / "towns"
    dest_towns.mkdir(parents=True)

    picked: dict[int, Path] = {}      # day -> source file
    requests = 0
    for day in days:
        src = next((f for r in roots for d in find_town_dirs(r, args.town)
                    if (f := day_file(d / "cache", day))), None)
        if src is None:
            requests += 1
            print(f"REQUEST {requests}: Fata /towndata?town={args.town}&day={day}")
            src = fetch_from_fata(args.town, day, dest_towns)
            print(f"  day {day}: fetched")
        else:
            print(f"  day {day}: copied from {src.relative_to(src.anchor)}")
        picked[day] = src

    raw_current = read_gz(picked[args.day])
    ti = raw_current["town_info"]
    if ti.get("day") != args.day:
        sys.exit(f"{picked[args.day]} holds day {ti.get('day')}, not {args.day}.")
    # Folder name: the live archive's slug when known, else the one the archive made.
    existing = [d for r in roots for d in find_town_dirs(r, args.town)] + find_town_dirs(dest_towns, args.town)
    slug = existing[0].name
    cache = dest_towns / slug / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    for day, src in picked.items():
        name = f"day-{day:02d}.towndata{'.live' if day == args.day else ''}.json.gz"
        target = cache / name
        if src.resolve() != target.resolve():
            if args.inject_note and day == args.day:
                continue
            shutil.copyfile(src, target)
        if day == args.day:
            for stale in (cache / f"day-{day:02d}.towndata.json.gz",):
                if stale != target and stale.exists():
                    stale.unlink()
    if args.inject_note:
        notes = [m for m in raw_current.get("town_maps", []) if m.get("comment")]
        if not notes:
            sys.exit("--inject-note: the day has no map note to replace.")
        notes[0]["comment"] = args.inject_note
        write_gz(cache / f"day-{args.day:02d}.towndata.live.json.gz", raw_current)
        print(f"  injected note into zone {notes[0].get('x')},{notes[0].get('y')}")

    (cache / "_meta.json").write_text(json.dumps(
        {"town_id": args.town, "town_name": ti.get("name"), "season": ti.get("season"),
         "current_day": args.day}, indent=2))

    for d in [x for r in roots for x in find_town_dirs(r, args.town)]:
        est = d / "cache" / "estimations.json"
        if est.exists() and not (cache / "estimations.json").exists():
            shutil.copyfile(est, cache / "estimations.json")
        cp = d / "citizens-cp.json"
        if cp.exists() and not (cache.parent / "citizens-cp.json").exists():
            log = cut_cp_log(json.loads(cp.read_text(encoding="utf-8")), data_cutoff(raw_current))
            (cache.parent / "citizens-cp.json").write_text(
                json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")

    work.rename(fixture)
    print(f"Frozen {args.fixture_id}: town {args.town} day {args.day} (+{args.with_day or 'no earlier days'}), "
          f"{requests} Fata request(s). Folder: {fixture}")


if __name__ == "__main__":
    main()
