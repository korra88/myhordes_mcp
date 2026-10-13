"""Gest'Hordes REST API client — town statistics endpoint.

Fetches per-day attack/defense statistics for a town, including:
- Theoretical min/max attack curve (atk_min_theo / atk_max_theo)
- Per-day actual attack and Gest'Hordes estimates
- Defense totals and per-source breakdown
- Actual deaths per night (morts_reels)

No authentication required. The stats endpoint is public.
URL: https://gesthordes.fr/rest/v1/stats/{map_id}

Requests are coalesced and cached like the Fata client (GESTHORDES_CACHE_TTL,
default 120 s — stats change infrequently during the day).
"""

import httpx

from ..utils.cache import TTLCache
from ..utils.config import USER_AGENT, env_int

GESTHORDES_STATS_URL = "https://gesthordes.fr/rest/v1/stats/{map_id}"

CACHE_TTL = env_int("GESTHORDES_CACHE_TTL", 120)  # seconds

_cache = TTLCache(CACHE_TTL, cache_if=lambda r: "error" not in r)


async def fetch_stats(map_id: int) -> dict:
    """Fetch town statistics from Gest'Hordes.

    Returns the raw parsed JSON response dict, or a dict with an 'error' key.
    """
    return await _cache.get(map_id, lambda: _fetch(map_id))


async def _fetch(map_id: int) -> dict:
    url = GESTHORDES_STATS_URL.format(map_id=map_id)
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                url,
                headers={
                    "accept": "application/json",
                    "gh-mapid": str(map_id),
                    "user-agent": USER_AGENT,
                },
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return {"error": f"Gest'Hordes returned HTTP {e.response.status_code}"}
    except httpx.RequestError as e:
        return {"error": f"Could not reach Gest'Hordes: {e}"}

    try:
        data = resp.json()
    except Exception:
        return {"error": "Could not parse Gest'Hordes response as JSON"}

    if not data.get("success"):
        return {"error": "Gest'Hordes API returned success=false"}

    return data
