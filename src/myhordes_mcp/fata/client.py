"""Fata Morgana client — the single entry point for every request to Fata.

All tools read town state through `fetch_town_data()`, which calls the public
`/towndata` JSON endpoint (towndata.py has the shape and field meanings) and
turns it into the standard result dict.

Requests are coalesced and cached in memory (utils.cache.TTLCache): concurrent
tool calls for the same town/day share one HTTP request, and the parsed result
is reused for FATA_CACHE_TTL seconds (default 180, 0 disables).

Disk archive (archive.py): the current day is stored on every fetch; a past
day is stored once and then always served from disk. Days archived from the
legacy spy page (before 2026-10-15) are still read through parse.py.

Every parsed result also feeds the per-citizen CP log (cp.py) and, for the
current day, the intraday snapshots (snapshot.py).

The endpoint is not affected by the nightly attack (Fata developer, 2026-10-15).
"""

import os

import httpx

from ..utils.cache import TTLCache
from ..utils.config import USER_AGENT, env_int
from . import archive, cp
from .parse import _build_result
from .snapshot import snapshot
from .towndata import build_result, is_towndata

FATA_TOWNDATA_URL = os.getenv("FATA_TOWNDATA_URL", "https://beta.fatamorgana.md26.eu/towndata")

CACHE_TTL = env_int("FATA_CACHE_TTL", 180)  # seconds

# Error results are not cached, so the next call retries.
_cache = TTLCache(CACHE_TTL, cache_if=lambda r: not r.get("error"))


async def fetch_town_data(town_id: int, day: int | None = None) -> dict:
    """Fetch and parse a town's Fata Morgana data.

    Args:
        town_id: The Fata Morgana town/game ID.
        day: Optional day number to fetch historical data. None = current day.

    Returns a dict with keys: meta, defense, water, gate, estimations, attacks,
    citizens, deaths, bank, buildings, scout, zones, error.
    """
    return await _cache.get((town_id, day), lambda: _fetch(town_id, day))


def _from_archive(town_id: int, day: int, *, final_only: bool) -> dict | None:
    raw = archive.load_towndata(town_id, day, final_only=final_only)
    if raw is not None:
        return _result(town_id, raw)
    if final_only:
        return None
    legacy = archive.load_day_json(town_id, day)
    return _build_result(town_id, legacy) if legacy is not None else None


def _result(town_id: int, raw: dict) -> dict:
    day = raw["town_info"].get("day") or 0
    return build_result(town_id, raw, archive.estimation_history(town_id, day))


async def _fetch(town_id: int, day: int | None) -> dict:
    # A past day is final once stored. The town's current day is always fetched
    # fresh: players keep updating Fata throughout the day.
    is_current_day = day is None or day == archive.get_current_day(town_id)
    if not is_current_day:
        cached = _from_archive(town_id, day, final_only=True)
        if cached is not None:
            return cached

    params = {"town": town_id}
    if day is not None:
        params["day"] = day
    try:
        async with httpx.AsyncClient(timeout=30.0, headers={"user-agent": USER_AGENT}) as client:
            resp = await client.get(FATA_TOWNDATA_URL, params=params)
            resp.raise_for_status()
            raw = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        if day is not None:
            cached = _from_archive(town_id, day, final_only=False)
            if cached is not None:
                return cached
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 429:
                return {"error": "Fata Morgana rate limit reached (60 requests). Try again in a minute."}
            return {"error": f"Fata Morgana returned HTTP {e.response.status_code}"}
        if isinstance(e, httpx.RequestError):
            return {"error": f"Could not reach Fata Morgana: {e}"}
        return {"error": "Fata Morgana returned data that is not JSON."}

    if not is_towndata(raw):
        return {"error": f"No Fata Morgana data for town {town_id}"
                         + (f" on day {day}" if day is not None else "") + "."}

    result_day = raw["town_info"].get("day")
    # Final only when the town is known to be past that day; otherwise keep it as live.
    known_day = archive.get_current_day(town_id)
    live = day is None or known_day is None or (result_day or 0) >= known_day
    if result_day is not None:
        archive.save_towndata(town_id, result_day, raw, live=live)

    result = _result(town_id, raw)
    cp.update_cp_log(town_id, result)
    if day is None and result_day is not None:
        archive.save_snapshot(town_id, result_day, snapshot(result))
    return result
