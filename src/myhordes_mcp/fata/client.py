"""Fata Morgana client — the single entry point for every request to Fata.

All tools read town state through `fetch_town_data()`, which scrapes the spy
page and parses the embedded `var data = {...}` object (see parse.py).

Requests are coalesced and cached in memory (utils.cache.TTLCache): concurrent
tool calls for the same town/day share one HTTP request, and the parsed result
is reused for FATA_CACHE_TTL seconds (default 180, 0 disables). Past days are
also archived on disk (archive.py) and served from there when available.

JSON export (not used yet)
--------------------------
The legacy app exposes a JSON endpoint, poorly documented, confirmed by the
Fata Morgana developer (it will come back on the new app too, and they offered
to expand its output on request):

    GET {FATA_BASE_URL}/getdata?town={town_id}[&advanced=1]

Shape (sampled 2026-10-10, town 8212, 228 zones — 47 KB basic, 56 KB advanced):

    map.id, map.days
    map.zones[]: x, y, rx, ry,
                 details {z (zombies), dried},
                 items [{id, count, broken}]          # item IDs, no names
                 building {type, dried, camped},      # building type ID, no name
                 extra {updatedOn, updatedOnDay, updatedBy, updatedById, deadz},
                 scavsense
    advanced=1 adds:
    map.layout {width, height, town_x, town_y}
    map.citizens[]: id, name, job, x, y, rx, ry
    map.windhistory[], map.searchtower {built, level}

It covers the map only: no bank, buildings, defense, estimations, deaths or
scout data, and items/ruins come as IDs. The spy page has all of that, so it
stays the source until getdata grows to match.
"""

import os

import httpx

from ..utils.cache import TTLCache
from ..utils.config import env_int
from . import archive
from .parse import _build_result, _extract_js_data

FATA_BASE_URL = os.getenv("FATA_BASE_URL", "https://fatamorgana.md26.eu").rstrip("/")
FATA_SPY_URL = FATA_BASE_URL + "/spy/town/{town_id}"
FATA_SPY_DAY_URL = FATA_BASE_URL + "/spy/town/{town_id}/{day}"

CACHE_TTL = env_int("FATA_CACHE_TTL", 180)  # seconds

# Error results are not cached, so the next call retries.
_cache = TTLCache(CACHE_TTL, cache_if=lambda r: not r.get("error"))


async def fetch_town_data(town_id: int, day: int | None = None) -> dict:
    """Fetch and parse all data from a Fata Morgana spy page.

    Args:
        town_id: The Fata Morgana town/game ID.
        day: Optional day number to fetch historical data. None = current day.

    Returns a dict with keys: meta, defense, water, gate, estimations,
    citizens, deaths, bank, buildings, scout, zones, error.
    """
    if day is not None:
        url = FATA_SPY_DAY_URL.format(town_id=town_id, day=day)
    else:
        url = FATA_SPY_URL.format(town_id=town_id)
    return await _cache.get(url, lambda: _fetch(url, town_id, day))


async def _fetch(url: str, town_id: int, day: int | None) -> dict:
    # For past days, try the disk archive before hitting the network.
    # But if the requested day matches the town's current day, always fetch
    # fresh — players keep updating Fata throughout the day.
    is_current_day = day is None
    if not is_current_day:
        known_day = archive.get_current_day(town_id)
        if known_day is not None and day == known_day:
            is_current_day = True

    if not is_current_day:
        cached_js = archive.load_day_json(town_id, day)
        if cached_js is not None:
            return _build_result(town_id, cached_js)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        # On network failure, fall back to the disk archive
        if day is not None:
            cached_js = archive.load_day_json(town_id, day)
            if cached_js is not None:
                return _build_result(town_id, cached_js)
        return {"error": f"Fata Morgana returned HTTP {e.response.status_code}"}
    except httpx.RequestError as e:
        if day is not None:
            cached_js = archive.load_day_json(town_id, day)
            if cached_js is not None:
                return _build_result(town_id, cached_js)
        return {"error": f"Could not reach Fata Morgana: {e}"}

    html = resp.text
    js_data = _extract_js_data(html)
    if not js_data:
        return {"error": "Could not parse town data from Fata Morgana page."}

    result = _build_result(town_id, js_data)

    # Persist to the disk archive
    sys_data = js_data.get("system", {})
    result_day = day if day is not None else sys_data.get("day")
    if result_day is not None:
        archive.save_day(
            town_id=town_id,
            day=result_day,
            html=html,
            js_data=js_data,
            town_name=sys_data.get("gamename", "Unknown"),
            season=sys_data.get("season"),
            is_current_day=(day is None),
        )

    return result
