"""Camping log: which citizen spent which night outside, from the Fata day archives.

Rules (docs/camping-plan.md, 1.2): at night every living citizen outside either hides and
rolls the odds (survived: camping counter + 1) or dies as Vanished (death type 5). So a
citizen outside at the end of day N who is alive on day N+1 camped night N (day N -> N+1).
Fata cannot say who hid, only where each citizen stood at their `last_update`.

Night N is judged from E = the archive of day N (final file, else the last live one) and
M = the archive of day N+1 (the current day's live file for the latest night):

  end-of-day-N record  among the citizen's records in E and M dated day N, the latest by
                       time; none = stale position, the citizen is not counted;
  sure      that record is outside (not at the doors) on zone Z and M's record is dated
            day N+1 and still outside on Z;
  probable  that record is outside on Z, dated 19:00 or later (hiding hours), alive in M,
            but M shows nothing newer or shows the citizen back in town / elsewhere;
  not counted  an outside record from before 19:00 with no M confirmation: most are day
            expeditions back home before night (town 8299 nights 5-6: 19 and 11 such
            citizens from early-day archives);
  died      dead in M with death type 5 whose death day is N (Fata cannot tell a failed
            roll from not hiding at all).

A probable night is never presented as confirmed. Stored per town in
towns/{town}/camping-log.json (only where TOWN_LOG_AUTO is on): per citizen id {name, nights [{night, zone, label}],
died_outside}; per night the signature of both input files, so a night is recomputed only
when an input changed. Updated from client._load on live fetches (no polling).

Backfill (user-run, one request per missing day):
    python -m myhordes_mcp.fata.camplog backfill --town N [--from D]
"""

import asyncio
import gzip
import json
import os
import re
import sys
import time
from datetime import datetime

from . import archive
from .geo import TOWN, fmt_xy
from .towndata import build_result
from ..utils.clock import GAME_TZ
from ..utils.config import TOWN_LOG_AUTO

HIDING_FROM_HOUR = 19   # camping odds get the night bonus from 19:00 (TownConf::isNightTime)

LOG_FILE = "camping-log.json"
# Written only where the town log is on (TOWN_LOG_AUTO, the Pi): towns/ is a git repo shared
# by several machines, one writer avoids merge conflicts on this file.
AUTO = TOWN_LOG_AUTO
VANISHED = 5
TOWN_COORDS = fmt_xy(TOWN)
_DAY_FILE = re.compile(r"^day-(\d+)\.towndata(\.live)?\.json\.gz$")
_views: dict[tuple, dict] = {}   # parsed minimal view per input file signature (this process)


# --- pure rules -------------------------------------------------------------

def day_view(data: dict) -> dict:
    """The few fields the rules need from a parsed /towndata result."""
    alive = {c["id"]: {"name": c["name"], "coords": c["coords"], "inside": bool(c["inside_town"]),
                       "day": c.get("last_update_day"), "time": c.get("last_update_time")}
             for c in data.get("citizens", [])}
    dead = {d["id"]: {"name": d["name"], "type": d.get("type"), "day": d["day"], "coords": d["last_coords"]}
            for d in data.get("deaths", []) if d.get("id") is not None}
    return {"alive": alive, "dead": dead}


def _evening(ts) -> bool:
    """Update made at HIDING_FROM_HOUR or later, game time (the record is already dated day N)."""
    try:
        return datetime.fromtimestamp(int(ts), GAME_TZ).hour >= HIDING_FROM_HOUR
    except (TypeError, ValueError, OverflowError, OSError):
        return False


def night_outcome(night: int, e: dict, m: dict) -> tuple[dict, dict]:
    """({citizen id: {name, zone, label}} camped, {citizen id: {name, zone}} died outside)
    for the night `night` -> `night + 1`, from the views of day N (e) and day N+1 (m)."""
    camped, died = {}, {}
    for cid, mrec in m["alive"].items():
        cands = [(r, tag) for r, tag in ((e["alive"].get(cid), 0), (mrec, 1))
                 if r and r.get("day") == night and r.get("time") is not None]
        if not cands:
            continue
        end = max(cands, key=lambda c: (c[0]["time"], c[1]))[0]   # on a tie M wins
        if end["inside"] or end["coords"] == TOWN_COORDS:
            continue
        sure = (mrec.get("day") == night + 1 and not mrec["inside"]
                and mrec["coords"] == end["coords"])
        if not sure and not _evening(end["time"]):
            continue
        camped[cid] = {"name": mrec["name"], "zone": end["coords"], "label": "sure" if sure else "probable"}
    for cid, d in m["dead"].items():
        if d["type"] == VANISHED and d["day"] == night and d["coords"] != TOWN_COORDS:
            died[cid] = {"name": d["name"], "zone": d["coords"]}
    return camped, died


def apply_night(log: dict, night: int, camped: dict, died: dict) -> None:
    """Replace everything the log holds for `night` (idempotent)."""
    cits = log.setdefault("citizens", {})
    for e in cits.values():
        e["nights"] = [n for n in e.get("nights", []) if n["night"] != night]
        if e.get("died_outside") == night:
            e["died_outside"] = None
    for cid, c in camped.items():
        e = cits.setdefault(str(cid), {"name": c["name"], "nights": [], "died_outside": None})
        e["name"] = c["name"]
        e["nights"].append({"night": night, "zone": c["zone"], "label": c["label"]})
        e["nights"].sort(key=lambda n: n["night"])
    for cid, d in died.items():
        e = cits.setdefault(str(cid), {"name": d["name"], "nights": [], "died_outside": None})
        e["name"], e["died_outside"] = d["name"], night
    for k in [k for k, e in cits.items() if not e["nights"] and e.get("died_outside") is None]:
        del cits[k]


def counts(log: dict, citizen_id: int) -> tuple[int, int]:
    """(sure, probable) camping nights of a citizen."""
    nights = (log.get("citizens", {}).get(str(citizen_id)) or {}).get("nights", [])
    return (sum(n["label"] == "sure" for n in nights), sum(n["label"] == "probable" for n in nights))


def night_line(log: dict, night: int) -> str | None:
    """'Camped: 2 sure (A, B), 1 probable (C)' for the night, None when nobody."""
    groups: dict[str, list[str]] = {"sure": [], "probable": []}
    for e in log.get("citizens", {}).values():
        for n in e.get("nights", []):
            if n["night"] == night:
                groups[n["label"]].append(e["name"])
    parts = [f"{len(v)} {k} ({', '.join(sorted(v, key=str.lower))})" for k, v in groups.items() if v]
    return "Camped: " + ", ".join(parts) if parts else None


# --- files ------------------------------------------------------------------

def _empty(town_id: int) -> dict:
    return {"town_id": town_id, "citizens": {}, "nights": {}}


def load_log(town_id: int) -> dict:
    tdir = archive.town_dir(town_id)
    if tdir is None:
        return _empty(town_id)
    try:
        log = json.loads((tdir / LOG_FILE).read_text(encoding="utf-8"))
        log.setdefault("citizens", {})
        log.setdefault("nights", {})
        return log
    except (OSError, json.JSONDecodeError):
        return _empty(town_id)


def _write(tdir, log: dict) -> None:
    path = tdir / LOG_FILE
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")  # one per writer, see archive.save_towndata
    tmp.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _day_files(cache_dir) -> dict[int, "os.PathLike"]:
    """{day: towndata file}, the final file preferred over the live one."""
    out: dict[int, tuple[bool, object]] = {}
    try:
        names = os.listdir(cache_dir)
    except OSError:
        return {}
    for name in names:
        mt = _DAY_FILE.match(name)
        if mt:
            day, live = int(mt.group(1)), bool(mt.group(2))
            if day not in out or (out[day][0] and not live):
                out[day] = (live, cache_dir / name)
    return {d: p for d, (_, p) in out.items()}


def _sig(path) -> str | None:
    """File name plus the gzip trailer (CRC32 and size of the content): changes exactly when
    the content does, costs one 8-byte read, and survives a copy of towns/."""
    try:
        with open(path, "rb") as f:
            f.seek(-8, os.SEEK_END)
            tail = f.read(8)
    except OSError:
        return None
    return f"{path.name}:{tail.hex()}"


def _view(town_id: int, path, sig: str) -> dict | None:
    v = _views.get((town_id, sig))
    if v is None:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                raw = json.load(f)
            v = day_view(build_result(town_id, raw, None))
        except (OSError, EOFError, KeyError, TypeError, ValueError, AttributeError):
            return None
        if len(_views) > 8:
            _views.clear()
        _views[(town_id, sig)] = v
    return v


def update_camping_log(town_id: int, current_day: int | None = None) -> list[int]:
    """Process every night whose two day files exist and are new or changed since the log
    last saw them (cheap: file stats; only changed nights are parsed). Returns the nights
    recomputed. Called after a live fetch has stored the current day's file."""
    tdir = archive.town_dir(town_id)
    if tdir is None:
        return []
    files = _day_files(archive.cache_path(tdir))
    if not files:
        return []
    top = max(files) if current_day is None else current_day
    log = load_log(town_id)
    done = []
    for night in sorted(d for d in files if d + 1 in files and d + 1 <= top):
        sig_e, sig_m = _sig(files[night]), _sig(files[night + 1])
        if sig_e is None or sig_m is None:
            continue
        rec = log["nights"].get(str(night))
        if rec and rec.get("e") == sig_e and rec.get("m") == sig_m:
            continue
        e, m = _view(town_id, files[night], sig_e), _view(town_id, files[night + 1], sig_m)
        if e is None or m is None:
            continue
        camped, died = night_outcome(night, e, m)
        apply_night(log, night, camped, died)
        log["nights"][str(night)] = {
            "e": sig_e, "m": sig_m,
            "sure": sum(c["label"] == "sure" for c in camped.values()),
            "probable": sum(c["label"] == "probable" for c in camped.values()),
            "died_outside": len(died),
        }
        done.append(night)
    if done:
        log["town_id"] = town_id
        log["updated"] = int(time.time())
        _write(tdir, log)
    return done


# --- backfill CLI -----------------------------------------------------------

def missing_days(town_id: int, first: int = 1) -> list[int]:
    """Past days (from `first` to current - 1) with no towndata file at all."""
    tdir = archive.town_dir(town_id)
    cur = archive.get_current_day(town_id)
    if tdir is None or cur is None:
        return []
    have = _day_files(archive.cache_path(tdir))
    return [d for d in range(max(1, first), cur) if d not in have]


async def _backfill(town_id: int, first: int) -> int:
    from .client import fetch_town_data   # the only HTTP path to Fata
    days = missing_days(town_id, first)
    print(f"{len(days)} missing day archive(s) to fetch: {days}" if days else "no missing day archives")
    for d in days:
        r = await fetch_town_data(town_id, day=d)
        print(f"  day {d}: " + (f"error: {r['error']}" if r.get("error") else "stored"))
    nights = update_camping_log(town_id)
    log = load_log(town_id)
    print(f"camping log rebuilt: nights recomputed {nights or 'none (already current)'}; "
          f"{len(log['citizens'])} citizen(s) in the log")
    return 0


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m myhordes_mcp.fata.camplog")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill", help="fetch missing past-day archives, then rebuild the log")
    b.add_argument("--town", type=int, required=True)
    b.add_argument("--from", dest="first", type=int, default=1)
    args = ap.parse_args(argv)
    return asyncio.run(_backfill(args.town, args.first))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
