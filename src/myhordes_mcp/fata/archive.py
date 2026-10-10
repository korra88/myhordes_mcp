"""Filesystem archive of Fata Morgana spy pages.

Stores fetched HTML pages and extracted JSON data per town per day,
so historical data is preserved even if Fata Morgana stops serving it.

Layout:
    {TOWNS_DIR}/{town_slug}/cache/      (TOWNS_DIR: MYHORDES_TOWNS_DIR, default towns/)
        day-01.html     # full raw HTML (archival)
        day-01.json     # extracted JS dict (fast access)
"""

import json
import re
from pathlib import Path

from ..utils.config import TOWNS_DIR


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
    slug = re.sub(r"[^a-z0-9]+", "-", town_name.lower()).strip("-")
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


def save_day(town_id: int, day: int, html: str, js_data: dict,
             town_name: str = "Unknown", season: int | None = None,
             is_current_day: bool = False):
    """Save a day's HTML and extracted JSON to the filesystem cache.

    Creates the town directory if it doesn't exist yet.

    For past days (is_current_day=False): HTML is written once (immutable),
    JSON is always updated (in case the parser improved).

    For the current day (is_current_day=True): both HTML and JSON are
    overwritten on every fetch, since players update Fata throughout the day.
    The current day number is also stored in _meta.json so that explicit
    requests for the current day number (e.g. day=1 when town is on day 1)
    are treated as live, not served from stale cache.
    """
    town_dir = _find_town_dir(town_id)
    if town_dir is None:
        town_dir = _create_town_dir(town_id, town_name, season)

    cache_dir = _ensure_cache_dir(town_dir)
    # Always update current_day in meta when we know the town's actual day
    actual_day = js_data.get("system", {}).get("day")
    _save_meta(cache_dir, town_id, town_name, season, current_day=actual_day)

    html_file = cache_dir / f"day-{day:02d}.html"
    json_file = cache_dir / f"day-{day:02d}.json"

    if is_current_day or not html_file.exists():
        html_file.write_text(html, encoding="utf-8")

    json_file.write_text(json.dumps(js_data, ensure_ascii=False, indent=2), encoding="utf-8")


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


def load_day_html(town_id: int, day: int) -> str | None:
    """Load cached HTML for a specific day. Returns None if not cached."""
    town_dir = _find_town_dir(town_id)
    if town_dir is None:
        return None
    html_file = town_dir / "cache" / f"day-{day:02d}.html"
    if not html_file.exists():
        return None
    try:
        return html_file.read_text(encoding="utf-8")
    except OSError:
        return None


def list_cached_days(town_id: int) -> list[int]:
    """Return sorted list of day numbers that are cached for this town."""
    town_dir = _find_town_dir(town_id)
    if town_dir is None:
        return []
    cache_dir = town_dir / "cache"
    if not cache_dir.is_dir():
        return []
    days = []
    for f in cache_dir.glob("day-*.json"):
        m = re.match(r"day-(\d+)\.json", f.name)
        if m:
            days.append(int(m.group(1)))
    return sorted(days)
