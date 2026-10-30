"""Filesystem archive of Fata Morgana data.

Stores the raw response per town per day, so historical data is preserved even
if Fata Morgana stops serving it.

Layout:
    towns/{town_slug}/cache/
        _meta.json                     # town_id → this folder (skills resolve the folder from it)
        day-07.towndata.json.gz        # /towndata for a finished day (final, never refetched)
        day-07.towndata.live.json.gz   # /towndata while day 7 was the current day (overwritten)
        day-01.html / day-01.json      # legacy spy page + extracted JS dict (read-only now)
"""

import gzip
import json
import re
import unicodedata
from pathlib import Path

from ..utils.config import TOWNS_DIR
from .towndata import estimation_entry


def _find_town_dir(town_id: int) -> Path | None:
    """Find the town directory that matches this town_id.

    Town dirs follow the pattern s{season}-{slug}/. We check if any existing
    town dir's cached metadata matches the given town_id.
    """
    if not TOWNS_DIR.is_dir():
        return None
    for entry in TOWNS_DIR.iterdir():
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        # Check if this dir has cached data with a matching town_id
        meta_file = entry / "cache" / "_meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                if meta.get("town_id") == town_id:
                    return entry
            except (json.JSONDecodeError, OSError):
                continue
    return None


def _ensure_cache_dir(town_dir: Path) -> Path:
    """Create and return the cache/ subdirectory under a town dir."""
    cache_dir = town_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _create_town_dir(town_id: int, town_name: str, season: int | None) -> Path:
    """Create a new town directory based on metadata from the fetched data."""
    # "Anónimos" → "anonimos": strip accents so the slug matches the town name as read
    ascii_name = unicodedata.normalize("NFKD", town_name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    season_prefix = f"s{season}" if season else "s0"
    dir_name = f"{season_prefix}-{slug}" if slug else f"{season_prefix}-town-{town_id}"
    town_dir = TOWNS_DIR / dir_name
    town_dir.mkdir(parents=True, exist_ok=True)
    return town_dir


def _save_meta(cache_dir: Path, town_id: int, town_name: str,
               season: int | None, current_day: int | None = None):
    """Write cache metadata so we can match town_id to directory later."""
    meta = {"town_id": town_id, "town_name": town_name, "season": season}
    if current_day is not None:
        meta["current_day"] = current_day
    meta_file = cache_dir / "_meta.json"
    meta_file.write_text(json.dumps(meta, indent=2))


def get_current_day(town_id: int) -> int | None:
    """Return the last-known current day for a town, or None if unknown."""
    town_dir = _find_town_dir(town_id)
    if town_dir is None:
        return None
    meta_file = town_dir / "cache" / "_meta.json"
    if not meta_file.exists():
        return None
    try:
        meta = json.loads(meta_file.read_text())
        return meta.get("current_day")
    except (json.JSONDecodeError, OSError):
        return None


def load_day_json(town_id: int, day: int) -> dict | None:
    """Load cached JSON for a specific day. Returns None if not cached."""
    town_dir = _find_town_dir(town_id)
    if town_dir is None:
        return None
    json_file = town_dir / "cache" / f"day-{day:02d}.json"
    if not json_file.exists():
        return None
    try:
        return json.loads(json_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# /towndata responses (gzipped raw JSON)
# ---------------------------------------------------------------------------

def _towndata_file(cache_dir: Path, day: int, live: bool) -> Path:
    return cache_dir / f"day-{day:02d}.towndata{'.live' if live else ''}.json.gz"


def town_dir(town_id: int) -> Path | None:
    """The town's folder under towns/, or None if nothing was fetched for it yet."""
    return _find_town_dir(town_id)


def save_towndata(town_id: int, day: int, raw: dict, *, live: bool, current: bool = False) -> Path:
    """Store a /towndata response. live=True: a day that may still change
    (overwritten on every fetch); live=False: a finished day, final.
    current=True: `day` is the town's current day (only a request without a
    day can tell), recorded in _meta.json. Returns the town folder."""
    ti = raw.get("town_info") or {}
    tdir = _find_town_dir(town_id)
    if tdir is None:
        tdir = _create_town_dir(town_id, ti.get("name", "Unknown"), ti.get("season"))
    cache_dir = _ensure_cache_dir(tdir)
    if current:
        _save_meta(cache_dir, town_id, ti.get("name", "Unknown"), ti.get("season"), current_day=day)
    elif not (cache_dir / "_meta.json").exists():
        _save_meta(cache_dir, town_id, ti.get("name", "Unknown"), ti.get("season"))
    _save_estimation(cache_dir, day, ti.get("estimation_today"), final=not live)
    path = _towndata_file(cache_dir, day, live)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
    tmp.replace(path)
    if not live:
        _towndata_file(cache_dir, day, live=True).unlink(missing_ok=True)
    return tdir


def load_towndata(town_id: int, day: int, *, final_only: bool = False) -> dict | None:
    """A stored /towndata day: the final version, else (unless final_only) the last live one."""
    tdir = _find_town_dir(town_id)
    if tdir is None:
        return None
    for live in ((False,) if final_only else (False, True)):
        path = _towndata_file(tdir / "cache", day, live)
        if path.exists():
            try:
                with gzip.open(path, "rt", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError, EOFError):
                continue
    return None


# Estimations per day, kept small so the history doesn't need the day files:
#   cache/estimations.json  {"towndata": {day: est}, "final": [days], "legacy": {day: est} | null}

def _est_file(cache_dir: Path) -> Path:
    return cache_dir / "estimations.json"


def _load_estimations(cache_dir: Path) -> dict:
    try:
        data = json.loads(_est_file(cache_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data.setdefault("towndata", {})
    data.setdefault("final", [])
    data.setdefault("legacy", None)
    return data


def _write_estimations(cache_dir: Path, data: dict) -> None:
    _est_file(cache_dir).write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


def _save_estimation(cache_dir: Path, day: int, est, *, final: bool) -> None:
    entry = estimation_entry(est)
    data = _load_estimations(cache_dir)
    if entry is None or (str(day) in data["final"] and not final):
        return
    data["towndata"][str(day)] = entry
    if final and str(day) not in data["final"]:
        data["final"].append(str(day))
    _write_estimations(cache_dir, data)


def estimation_history(town_id: int, before_day: int) -> dict:
    """{day_str: {min, max, maxed}} for days before `before_day`, from
    cache/estimations.json. Built once from the archive when missing: legacy
    spy pages (the latest one has the full history) and older /towndata files."""
    tdir = _find_town_dir(town_id)
    if tdir is None or not (tdir / "cache").is_dir():
        return {}
    cache_dir = tdir / "cache"
    data = _load_estimations(cache_dir)
    changed = False

    if data["legacy"] is None:
        data["legacy"] = {}
        legacy_days = sorted((int(m.group(1)) for f in cache_dir.glob("day-*.json")
                              if (m := re.match(r"day-(\d+)\.json$", f.name))), reverse=True)
        for day in legacy_days:
            legacy = load_day_json(town_id, day)
            if legacy and isinstance(legacy.get("estimations"), dict):
                for d, e in legacy["estimations"].items():
                    if d.isdigit() and isinstance(e, dict):
                        data["legacy"][d] = {"min": e.get("min"), "max": e.get("max"), "maxed": e.get("maxed")}
                break
        changed = True

    for f in cache_dir.glob("day-*.towndata*.json.gz"):
        m = re.match(r"day-(\d+)\.towndata(\.live)?\.json\.gz$", f.name)
        if not m or str(int(m.group(1))) in data["towndata"]:
            continue
        raw = load_towndata(town_id, int(m.group(1)))
        entry = estimation_entry(((raw or {}).get("town_info") or {}).get("estimation_today"))
        if entry:
            data["towndata"][str(int(m.group(1)))] = entry
            changed = True

    if changed:
        _write_estimations(cache_dir, data)
    hist = {d: e for d, e in (data["legacy"] or {}).items() if int(d) < before_day}
    hist.update({d: e for d, e in data["towndata"].items() if int(d) < before_day})
    return hist


# ---------------------------------------------------------------------------
# Intraday snapshots — compact state saved on every live fetch that changed
# something, so changes over the day can be computed in code.
#
#   cache/snapshots/day-02/1791644026.json
#   cache/_changes_marker.json      {"day": 2, "taken_at": 1791644026}
# ---------------------------------------------------------------------------

def _snapshot_dir(town_id: int, day: int) -> Path | None:
    town_dir = _find_town_dir(town_id)
    if town_dir is None:
        return None
    return town_dir / "cache" / "snapshots" / f"day-{day:02d}"


def save_snapshot(town_id: int, day: int, snap: dict) -> bool:
    """Store a snapshot unless its content equals the latest one. Returns True if saved."""
    sdir = _snapshot_dir(town_id, day)
    if sdir is None:
        return False
    sdir.mkdir(parents=True, exist_ok=True)
    latest = load_snapshots(town_id, day)[-1:] or [None]
    if latest[0] is not None and latest[0].get("hash") == snap.get("hash"):
        return False
    (sdir / f"{snap['taken_at']}.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return True


def load_snapshots(town_id: int, day: int) -> list[dict]:
    """All snapshots of a day, oldest first."""
    sdir = _snapshot_dir(town_id, day)
    if sdir is None or not sdir.is_dir():
        return []
    snaps = []
    for f in sorted(sdir.glob("*.json"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0):
        try:
            snaps.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return snaps


def get_changes_marker(town_id: int) -> dict | None:
    town_dir = _find_town_dir(town_id)
    f = town_dir / "cache" / "_changes_marker.json" if town_dir else None
    if f is None or not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def set_changes_marker(town_id: int, day: int, taken_at: int) -> None:
    town_dir = _find_town_dir(town_id)
    if town_dir is None:
        return
    f = _ensure_cache_dir(town_dir) / "_changes_marker.json"
    f.write_text(json.dumps({"day": day, "taken_at": taken_at}))
