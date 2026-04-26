"""Fata Morgana spy page scraper — httpx only, no browser needed.

Fetches the spy page for a given town ID and extracts the embedded
`var data = {...}` JavaScript object which contains all town state:
- Town metadata (name, day, season, game type)
- Defense breakdown and attack estimations
- Water supply
- Gate status (door)
- Citizen positions and jobs (with per-citizen freshness)
- Dead citizens (cadavers) with cause of death
- Bank inventory with item names
- Scout data (zombie counts per zone, per-zone freshness)
- Map zone data (ruins, ground items, zombie counts, danger)
- Buildings with upgrade levels and construction history
"""

import heapq
import json
import re
import time

import httpx

from sources import cache

FATA_SPY_URL = "https://fatamorgana.md26.eu/spy/town/{town_id}"
FATA_SPY_DAY_URL = "https://fatamorgana.md26.eu/spy/town/{town_id}/{day}"
FATA_UPDATE_URL = "https://fatamorgana.md26.eu/map/updatemyzone"

# dtype int → human-readable cause of death
DEATH_TYPES = {
    1: "Dehydrated",
    2: "Eaten by zombies",
    3: "Suicide by cyanide",
    4: "Vanished",
    5: "Disappeared into the outside world",
    6: "Nuclear",
    7: "Infection",
    8: "Ghoul purge",
}

# Zone danger level → human-readable zombie estimate
# These come from in-game map exploration (automatic), not manual scouting.
DANGER_LEVELS = {
    0: "safe (0 zombies)",
    1: "low (1-2 zombies)",
    2: "moderate (3-5 zombies)",
    3: "dangerous (6+ zombies)",
}

# Fata job key → display name
JOB_NAMES = {
    "basic": "Resident",
    "guardian": "Guardian",
    "hunter": "Scout",
    "collec": "Scavenger",
    "survivalist": "Survivalist",
    "tamer": "Tamer",
    "tech": "Technician",
}


# ---------------------------------------------------------------------------
# Response cache — avoids duplicate fetches when multiple tools fire in a row
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 60  # seconds


async def fetch_town_data(town_id: int, day: int | None = None) -> dict:
    """Fetch and parse all data from a Fata Morgana spy page.

    Results are cached for 60 seconds per URL so that consecutive tool calls
    (e.g. get_town_overview + get_citizen_positions) reuse the same fetch.

    Args:
        town_id: The Fata Morgana town/game ID.
        day: Optional day number to fetch historical data. None = current day.

    Returns a dict with keys: meta, defense, water, gate, estimations,
    citizens, deaths, bank, buildings, scout, error.
    """
    if day is not None:
        url = FATA_SPY_DAY_URL.format(town_id=town_id, day=day)
    else:
        url = FATA_SPY_URL.format(town_id=town_id)

    # Return in-memory cached result if fresh
    now = time.monotonic()
    if url in _cache:
        cached_at, cached_data = _cache[url]
        if now - cached_at < CACHE_TTL:
            return cached_data

    # For past days, try filesystem cache before hitting the network.
    # But if the requested day matches the town's current day, always fetch
    # fresh — players keep updating Fata throughout the day.
    is_current_day = day is None
    if not is_current_day and day is not None:
        known_day = cache.get_current_day(town_id)
        if known_day is not None and day == known_day:
            is_current_day = True

    if not is_current_day and day is not None:
        cached_js = cache.load_day_json(town_id, day)
        if cached_js is not None:
            result = _build_result(town_id, cached_js)
            _cache[url] = (now, result)
            return result

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        # On network failure, try filesystem cache as fallback
        if day is not None:
            cached_js = cache.load_day_json(town_id, day)
            if cached_js is not None:
                return _build_result(town_id, cached_js)
        return {"error": f"Fata Morgana returned HTTP {e.response.status_code}"}
    except httpx.RequestError as e:
        if day is not None:
            cached_js = cache.load_day_json(town_id, day)
            if cached_js is not None:
                return _build_result(town_id, cached_js)
        return {"error": f"Could not reach Fata Morgana: {e}"}

    html = resp.text
    js_data = _extract_js_data(html)
    if not js_data:
        return {"error": "Could not parse town data from Fata Morgana page."}

    result = _build_result(town_id, js_data)

    # Persist to filesystem cache
    sys_data = js_data.get("system", {})
    result_day = day if day is not None else sys_data.get("day")
    if result_day is not None:
        cache.save_day(
            town_id=town_id,
            day=result_day,
            html=html,
            js_data=js_data,
            town_name=sys_data.get("gamename", "Unknown"),
            season=sys_data.get("season"),
            is_current_day=(day is None),
        )

    _cache[url] = (now, result)
    return result


async def trigger_update(token: str) -> dict:
    """POST to Fata Morgana's updatemyzone endpoint to pull fresh data from the game API.

    The token is a JWT issued by Fata that encodes the player's user_skey and town gid.
    Fata uses it to call the official MyHordes API on the player's behalf, refreshing
    bank, buildings, citizen positions, and zombie estimates in their database.

    Returns a dict with 'ok' (bool) and 'message' (str).
    """
    headers = {
        "authorization": f"Bearer {token}",
        "content-type": "application/x-www-form-urlencoded",
        "x-requested-with": "XMLHttpRequest",
        "origin": "https://fatamorgana.md26.eu",
        "referer": "https://fatamorgana.md26.eu/map",
    }
    cookies = {"auth_token": token}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(FATA_UPDATE_URL, headers=headers, cookies=cookies)
        if resp.status_code == 200:
            if "MYZONEUPDATEDFAILEDINSIDE" in resp.text:
                return {"ok": True, "message": "Fata Morgana refreshed (bank, buildings, citizens updated). Zone/desert data skipped — must be outside town to refresh that."}
            return {"ok": True, "message": "Fata Morgana data refreshed from game API."}
        try:
            body = resp.json()
            detail = body.get("message") or body.get("error") or resp.text[:200]
        except Exception:
            detail = resp.text[:200]
        return {"ok": False, "message": f"HTTP {resp.status_code}: {detail}"}
    except httpx.RequestError as e:
        return {"ok": False, "message": f"Could not reach Fata Morgana: {e}"}


def _build_result(town_id: int, js_data: dict) -> dict:
    """Transform raw JS data into the standardized result dict."""
    sys = js_data.get("system", {})
    current_day = sys.get("day")

    def _as_dict(val, default=None):
        """Return val if it's a dict, otherwise default (handles [] from empty fields)."""
        return val if isinstance(val, dict) else (default or {})

    return {
        "error": None,
        "meta": {
            "town_name": sys.get("gamename", "Unknown"),
            "town_id": sys.get("gameid", town_id),
            "day": current_day,
            "season": sys.get("season"),
            "region": sys.get("region"),
            "game_type": sys.get("gametype"),
            "owner": sys.get("owner_name"),
            "data_time": sys.get("datatime"),
            "chaos": bool(sys.get("chaos")),
            "devastated": bool(sys.get("devast")),
        },
        "defense": _as_dict(js_data.get("defense")),
        "water": _as_dict(js_data.get("water")),
        "gate": "open" if js_data.get("door") == 1 else "closed",
        "estimations": _parse_estimations(js_data, current_day),
        "citizens": _parse_citizens(js_data, sys),
        "deaths": _parse_deaths(js_data, current_day),
        "bank": _parse_bank(js_data),
        "buildings": _parse_buildings(js_data),
        "scout": _parse_scout(js_data),
        "zones": _parse_map(js_data),
    }


# ---------------------------------------------------------------------------
# JS data extraction — brace-matching (the JSON is ~350KB, regex is unreliable)
# ---------------------------------------------------------------------------

def _extract_js_data(html: str) -> dict | None:
    """Extract the `var data = {...}` JSON object using brace-matching."""
    marker = html.find("var data = {")
    if marker == -1:
        marker = html.find("var data={")
    if marker == -1:
        return None

    brace_start = html.index("{", marker)
    depth = 0
    i = brace_start
    while i < len(html):
        ch = html[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        elif ch == '"':
            # Skip string contents to avoid counting braces inside strings
            i += 1
            while i < len(html) and html[i] != '"':
                if html[i] == "\\":
                    i += 1  # skip escaped char
                i += 1
        i += 1

    try:
        return json.loads(html[brace_start : i + 1])
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Parsers — transform JS data into clean dicts
# ---------------------------------------------------------------------------

def _parse_citizens(js_data: dict, sys_data: dict) -> list[dict]:
    """Parse citizen positions from the citizens dict."""
    citizens_raw = js_data.get("citizens", {})
    if not isinstance(citizens_raw, dict):
        citizens_raw = {}
    roles = sys_data.get("roles", {})
    if not isinstance(roles, dict):
        roles = {}
    shaman_id = roles.get("shaman")
    citizens = []
    for cid, c in citizens_raw.items():
        if c.get("dead"):
            continue
        rx = c.get("rx", 0)
        ry = c.get("ry", 0)
        inside = (rx == 0 and ry == 0) and not c.get("out", 0)
        citizens.append({
            "id": int(cid),
            "name": c.get("name", "Unknown"),
            "job": JOB_NAMES.get(c.get("job", ""), c.get("job", "unknown")),
            "coords": f"[{rx}|{ry}]",
            "inside_town": inside,
            "is_shaman": str(cid) == str(shaman_id),
            "last_update_day": c.get("lastUpdateDay"),
        })
    citizens.sort(key=lambda c: c["name"].lower())
    return citizens


def _parse_deaths(js_data: dict, current_day: int | None) -> list[dict]:
    """Parse cadaver list. Each entry in cadavers[] is a dict of deaths for one day.
    Index 0 = day 0, index 1 = day 1, etc."""
    cadavers = js_data.get("cadavers", [])
    deaths = []
    for day_idx, day_group in enumerate(cadavers):
        if not isinstance(day_group, dict):
            continue
        for pid, c in day_group.items():
            deaths.append({
                "name": c.get("name", "Unknown"),
                "cause": DEATH_TYPES.get(c.get("dtype"), f"Unknown ({c.get('dtype')})"),
                "last_coords": f"[{c.get('rx', '?')}|{c.get('ry', '?')}]",
                "day": day_idx,
            })
    # Sort by day descending (most recent first)
    deaths.sort(key=lambda d: d["day"], reverse=True)
    return deaths


def _parse_estimations(js_data: dict, current_day: int | None) -> dict:
    """Parse attack estimations. Keys are day numbers as strings."""
    est_raw = js_data.get("estimations", {})
    if not isinstance(est_raw, dict):
        est_raw = {}
    today = {}
    tomorrow = {}
    if current_day and str(current_day) in est_raw:
        e = est_raw[str(current_day)]
        today = {"min": e.get("min"), "max": e.get("max"), "maxed": e.get("maxed")}
    next_day = str(current_day + 1) if current_day else None
    if next_day and next_day in est_raw:
        e = est_raw[next_day]
        tomorrow = {"min": e.get("min"), "max": e.get("max"), "maxed": e.get("maxed")}
    return {"today": today, "tomorrow": tomorrow, "history": est_raw}


def _parse_bank(js_data: dict) -> list[dict]:
    """Parse bank inventory, resolving item IDs to names."""
    bank_raw = js_data.get("bank", {})
    if not isinstance(bank_raw, dict):
        bank_raw = {}
    items_dict = js_data.get("items", {})
    if not isinstance(items_dict, dict):
        items_dict = {}
    bank = []
    for item_id, info in bank_raw.items():
        count = info.get("count", 0)
        if count == 0:
            continue
        item_def = items_dict.get(str(item_id), {})
        name_dict = item_def.get("name", {})
        name = name_dict.get("en") or name_dict.get("fr") or f"Item #{item_id}"
        bank.append({
            "id": int(item_id),
            "name": name,
            "count": count,
            "broken": info.get("broken", 0),
            "category": item_def.get("category", "Unknown"),
            "heavy": bool(item_def.get("heavy")),
            "guard": bool(item_def.get("guard")),
            "deco": bool(item_def.get("deco")),
        })
    bank.sort(key=lambda i: i["name"].lower())
    return bank


def _parse_buildings(js_data: dict) -> list[dict]:
    """Extract building list from bpsAndConstructions.

    The `constructions` dict tells us which buildings are built and their
    current upgrade level (if upgradeable).

    `dailyConstructions` is the authoritative source for build days:
      dailyConstructions[day_str].built = [building_id, ...]

    `constructionHistory[bid].voted` encodes upgrade events as
    {vote_index_str: game_day_int} — vote index == new level reached,
    value == game day when the vote happened. We transform this to
    {game_day_int: new_level_int} for downstream consumption.
    """
    bps = js_data.get("bpsAndConstructions", {})
    if not isinstance(bps, dict):
        bps = {}
    constructions = js_data.get("constructions", {})
    if not isinstance(constructions, dict):
        constructions = {}
    history = js_data.get("constructionHistory", {})
    if not isinstance(history, dict):
        history = {}

    # Reverse-lookup: bid (str) → built_day (int), from dailyConstructions
    daily = js_data.get("dailyConstructions", {})
    build_day_lookup: dict[str, int] = {}
    if isinstance(daily, dict):
        for day_str, events in daily.items():
            if not isinstance(events, dict):
                continue
            try:
                day_num = int(day_str)
            except (ValueError, TypeError):
                continue
            for bid_val in events.get("built") or []:
                build_day_lookup[str(bid_val)] = day_num

    built_ids = set(constructions.keys())
    buildings = []
    for bid, b in bps.items():
        name_dict = b.get("name", {})
        name = name_dict.get("en") or name_dict.get("fr") or next(iter(name_dict.values()), f"Building {bid}")
        con = constructions.get(bid, {})
        level = con.get("level")  # None if not upgradeable

        # Transform voted: {vote_index_str: game_day} → {game_day: new_level}
        hist = history.get(bid, {})
        voted_raw = hist.get("voted")
        upgrade_days: dict[int, int] | None = None
        if isinstance(voted_raw, dict) and voted_raw:
            upgrade_days = {}
            for vote_idx_str, game_day in voted_raw.items():
                try:
                    new_level = int(vote_idx_str)  # vote index equals new level
                    day = int(game_day)
                    upgrade_days[day] = new_level
                except (ValueError, TypeError):
                    pass
            if not upgrade_days:
                upgrade_days = None

        # rarity: blueprint tier required (0=none, 1=common, 2=uncommon, 3=rare, 4=very rare)
        rarity = b.get("rarityCurrent")
        try:
            rarity = int(rarity) if rarity is not None else 0
        except (ValueError, TypeError):
            rarity = 0

        # blueprint_found: True = blueprint submitted for this town (buildable despite rarity>0)
        # None/False = blueprint not yet found → building is blocked even if prerequisite met
        blueprint_found = b.get("found") is True

        # parent: prerequisite building ID (0 = no prerequisite)
        parent_id = b.get("parent")
        try:
            parent_id = str(int(parent_id)) if parent_id is not None else None
        except (ValueError, TypeError):
            parent_id = None

        # resources: list of {name, amount} from resourcesCurrent
        resources = []
        for r in b.get("resourcesCurrent") or []:
            rsc = r.get("rsc", {})
            rname = rsc.get("name", {})
            item_name = rname.get("en") or rname.get("fr") or next(iter(rname.values()), "?")
            amount = r.get("amount", 1)
            resources.append({"name": item_name, "amount": amount})

        buildings.append({
            "id": bid,
            "name": name,
            "defense": b.get("def", 0),
            "ap_cost": b.get("paCurrent", 0),
            "temporary": b.get("temporary", False),
            "built": bid in built_ids,
            "level": level,
            "built_day": build_day_lookup.get(bid),
            "upgrade_days": upgrade_days,
            "rarity": rarity,
            "blueprint_found": blueprint_found,
            "parent_id": parent_id,
            "resources": resources,
        })

    # Second pass: resolve parent names now that all buildings are parsed
    id_to_name = {b["id"]: b["name"] for b in buildings}
    for b in buildings:
        pid = b["parent_id"]
        if pid and pid != "0":
            b["parent_name"] = id_to_name.get(pid)
            b["parent_built"] = pid in built_ids
        else:
            b["parent_name"] = None
            b["parent_built"] = True  # no prerequisite = effectively satisfied

    return buildings


def _parse_scout(js_data: dict) -> list[dict]:
    """Extract scout data (zombie counts per zone).

    Zone keys in the scout dict are absolute map coordinates (e.g. y15x-3).
    We normalize to town-relative coords where Y is inverted: rel_y = oy - abs_y.
    This matches the game convention where positive Y is south (lower abs_y).
    """
    scout_raw = js_data.get("scout", {})
    if not isinstance(scout_raw, dict):
        scout_raw = {}
    ox = js_data.get("ox", 0)
    oy = js_data.get("oy", 0)
    zones = []
    for key, info in scout_raw.items():
        m = re.match(r"y(-?\d+)x(-?\d+)", key)
        if not m:
            continue
        abs_y = int(m.group(1))
        abs_x = int(m.group(2))
        rel_x = abs_x - ox
        rel_y = oy - abs_y
        zones.append({
            "coords": f"[{rel_x}|{rel_y}]",
            "zombies": int(info.get("zom", 0)),
            "scouted_by": info.get("updatedBy", "Unknown"),
            "scouted_day": info.get("updatedOnDay"),
        })
    return zones


def _parse_map(js_data: dict) -> list[dict]:
    """Extract detailed zone data from the map dict.

    The map dict uses absolute coords as nested keys: map[yN][xM].
    Each zone has items, zombie count, ruin/building info, danger level, etc.
    Zone coords include rx/ry which are already town-relative.
    """
    map_raw = js_data.get("map", {})
    if not isinstance(map_raw, dict):
        map_raw = {}
    items_dict = js_data.get("items", {})
    if not isinstance(items_dict, dict):
        items_dict = {}
    buildings_dict = js_data.get("buildings", {})
    if not isinstance(buildings_dict, dict):
        buildings_dict = {}
    ox = js_data.get("ox", 0)
    oy = js_data.get("oy", 0)
    zones = []
    for y_key, x_dict in map_raw.items():
        if not isinstance(x_dict, dict):
            continue
        for x_key, zone in x_dict.items():
            if not isinstance(zone, dict):
                continue
            # Use rx/ry if available (already relative), else compute from keys
            if "rx" in zone and "ry" in zone:
                rx = zone["rx"]
                ry = zone["ry"]
            else:
                y_m = re.match(r"y(-?\d+)", y_key)
                x_m = re.match(r"x(-?\d+)", x_key)
                if not y_m or not x_m:
                    continue
                rx = int(x_m.group(1)) - ox
                ry = oy - int(y_m.group(1))

            # Resolve item names
            zone_items = []
            for item in zone.get("items", []):
                item_id = str(item.get("id", ""))
                item_def = items_dict.get(item_id, {})
                name_dict = item_def.get("name", {})
                name = name_dict.get("en") or name_dict.get("fr") or f"Item #{item_id}"
                zone_items.append({
                    "name": name,
                    "count": item.get("count", 0),
                    "broken": item.get("broken", 0),
                })

            # Parse ruin/building
            # blueprint: 0 = available (not yet found), 1 = already found
            ruin = None
            bld = zone.get("building")
            if bld and isinstance(bld, dict):
                ruin = {
                    "name": bld.get("name", "Unknown ruin"),
                    "type_id": bld.get("type"),
                    "digs_remaining": int(bld.get("dig", 0)),
                    "blueprint_available": int(bld.get("blueprint", 0)) == 0,
                    "dried": int(bld.get("dried", 0)),
                }

            entry = {
                "coords": f"[{rx}|{ry}]",
                "zombies": int(zone.get("zm", 0)),
                "zombies_max": int(zone.get("z", 0)),
                "danger": int(zone.get("danger", 0)),
                "dried": int(zone.get("dried", 0)),
                "tag": zone.get("tag"),
                "items": zone_items,
                "ruin": ruin,
                "updated_by": zone.get("updatedBy"),
                "updated_day": zone.get("updatedOnDay"),
            }
            zones.append(entry)
    return zones


# ---------------------------------------------------------------------------
# Formatters — turn parsed data into human-readable strings for the LLM
# ---------------------------------------------------------------------------

def _format_estimate(est: dict) -> str:
    """Format a single attack estimate with confirmed/partial indicator."""
    if est.get("min") is None:
        return "???"
    label = "(confirmed)" if est.get("maxed") else "(partial)"
    return f"{est['min']}-{est['max']} {label}"


def _staleness_tag(last_update_day: int | None, current_day: int | None) -> str:
    """Return a staleness warning if position data is old, empty string otherwise."""
    if last_update_day is None or current_day is None:
        return ""
    age = current_day - last_update_day
    if age >= 1:
        return f" [STALE: day {last_update_day}]"
    return ""


def _zombie_max_estimate(zombies: int, last_day: int | None, current_day: int | None) -> int | None:
    """Return a pessimistic max zombie estimate for a stale zone.

    Assumes +1.75 zombies per night (weighted toward +2 per night).
    Returns None if the zone is current or days elapsed is 0.
    """
    if last_day is None or current_day is None:
        return None
    age = current_day - last_day
    if age <= 0:
        return None
    return int(zombies + age * 1.75)


def _build_spread_map(
    zone_map: dict[tuple[int, int], dict],
    current_day: int | None,
) -> dict[tuple[int, int], tuple[int, int]]:
    """BFS from all known zombie zones to compute minimum spread distance.

    For each cell in zone_map that currently has zombies (zm > 0), we BFS
    outward in 4 directions. The result maps (x, y) -> (bfs_dist, source_zm)
    where bfs_dist is the minimum number of spread steps from any zombie source
    and source_zm is the (pessimistic) zombie count at that source.

    Only cells present in zone_map are seeded — we don't spread into unknown
    territory beyond the explored map. Unknown cells adjacent to zombie zones
    are not included (we can't confirm or deny infection there).

    Used to determine whether a clear zone could plausibly be infected:
    if age >= bfs_dist, zombies could have reached it by now.
    """
    from collections import deque

    # Seed: all zones with confirmed zombies, using their pessimistic current count
    seeds: list[tuple[int, int, int]] = []  # (x, y, effective_zm)
    for (x, y), z in zone_map.items():
        zm = z.get("zombies", -1)
        if zm > 0:
            last_day = z.get("updated_day") or z.get("scouted_day")
            est = _zombie_max_estimate(zm, last_day, current_day)
            effective_zm = est if est is not None else zm
            seeds.append((x, y, effective_zm))

    # BFS: spread only through cells that exist in zone_map (explored territory)
    result: dict[tuple[int, int], tuple[int, int]] = {}
    queue: deque[tuple[int, int, int, int]] = deque()  # (x, y, dist, source_zm)
    for x, y, zm in seeds:
        if (x, y) not in result:
            result[(x, y)] = (0, zm)
            queue.append((x, y, 0, zm))

    while queue:
        x, y, dist, source_zm = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) not in zone_map:
                continue  # only spread through explored cells
            if (nx, ny) in result:
                continue  # already reached via shorter/equal path
            result[(nx, ny)] = (dist + 1, source_zm)
            queue.append((nx, ny, dist + 1, source_zm))

    return result


def _spread_risk_for_clear(
    coords: tuple[int, int],
    age: int,
    spread_map: dict[tuple[int, int], tuple[int, int]],
) -> tuple[int, int] | None:
    """Return (bfs_dist, est_max_zombies) if a clear zone could be infected by spread.

    A clear zone at coords is at risk if age >= bfs_dist (zombies could have
    reached it in that many nights). Returns None if not reachable.
    """
    entry = spread_map.get(coords)
    if entry is None:
        return None
    bfs_dist, source_zm = entry
    if bfs_dist == 0:
        # This cell itself has zombies — should not be called for clear zones
        return None
    if age >= bfs_dist:
        # Worst case: 4 zombies spawned per spread step, capped at source count
        nights_of_growth = age - bfs_dist  # nights the zone could have grown after first infection
        est = min(4 + int(nights_of_growth * 1.75), source_zm)
        return bfs_dist, max(1, est)
    return None


def _zone_threat(zone: dict, current_day: int | None = None, spread_map: dict | None = None, coords: tuple[int, int] | None = None) -> str:
    """Format zombie count or danger estimate for a zone.

    If an exact zombie count was reported (zm >= 0), show it.
    For stale zones with zombies, appends a pessimistic max estimate (+1.75/night).
    For stale clear zones, checks spread_map: if zombie neighbors could have
    reached this cell within the elapsed days, shows a spread risk warning.
    Otherwise fall back to the danger level from in-game map exploration.
    """
    zm = zone.get("zombies", 0)
    if zm is not None and zm >= 0:
        last_day = zone.get("updated_day")
        age = (current_day - last_day) if (current_day and last_day) else 0
        if zm == 0:
            # Check spread risk: could a zombie zone have reached this cell?
            if spread_map is not None and coords is not None and age > 0:
                spread = _spread_risk_for_clear(coords, age, spread_map)
                if spread is not None:
                    bfs_dist, est = spread
                    return f", clear→≤{est} zom (spread risk, {bfs_dist}d away)"
            return ""
        est = _zombie_max_estimate(zm, last_day, current_day)
        if est:
            return f", {zm} zom→≤{est} (est.)"
        return f", {zm} zom"
    # No exact count — use danger level from exploration
    danger = zone.get("danger", 0)
    if danger:
        return f", ~{DANGER_LEVELS.get(danger, f'danger {danger}')}"
    return ""


def _zone_freshness(zone: dict, current_day: int | None) -> str:
    """Return a compact freshness string for a map zone, e.g. ' (by PlayerName, day 32)'."""
    updated_by = zone.get("updated_by")
    updated_day = zone.get("updated_day")
    if not updated_by and updated_day is None:
        return ""
    parts = []
    if updated_by:
        parts.append(f"by {updated_by}")
    if updated_day is not None:
        parts.append(f"day {updated_day}")
    tag = f" ({', '.join(parts)})"
    if current_day is not None and updated_day is not None and current_day - updated_day >= 1:
        tag += " [STALE]"
    return tag

def format_town_overview(data: dict, season_points: int | None = None, detail: str = "full") -> str:
    """Format a complete town overview.

    Args:
        data: Fata Morgana town data dict.
        season_points: Optional season point total from Gest'Hordes, shown in header.
        detail: 'full' (default) includes bank and deaths. 'compact' omits both —
                useful for cron/delta checks where bank is fetched separately.
    """
    if data.get("error"):
        return f"Error fetching town data: {data['error']}"

    meta = data["meta"]
    defense = data["defense"]
    water = data["water"]
    gate = data["gate"]
    est = data["estimations"]
    citizens = data["citizens"]
    deaths = data["deaths"]
    bank = data["bank"]
    current_day = meta.get("day")

    alive = len(citizens)
    inside = sum(1 for c in citizens if c["inside_town"])
    outside = alive - inside

    today_est = est.get("today", {})
    tonight = _format_estimate(today_est)
    tomorrow_est = est.get("tomorrow", {})
    tomorrow = _format_estimate(tomorrow_est)

    season_pts_str = f" | Season pts: {season_points}" if season_points is not None else ""
    lines = [
        f"# {meta.get('town_name', 'Unknown Town')} — Day {meta.get('day', '?')}",
        f"Season {meta.get('season', '?')} | Type: {meta.get('game_type', '?')} | Region: {meta.get('region', '?')}"
        + season_pts_str
        + (" | CHAOS MODE" if meta.get("chaos") else "")
        + (" | DEVASTATED" if meta.get("devastated") else ""),
        f"Data updated: {meta.get('data_time', 'unknown')}",
        "",
        f"## Gate: {gate.upper()}",
        "",
        "## Defense",
        f"  Total: {defense.get('total', '?')}",
        f"  Wall: {defense.get('base', '?')} | Buildings: {defense.get('buildings', '?')} | Items: {defense.get('items', '?')}",
        f"  Guardians: {defense.get('guardians', '?')} | Homes: {defense.get('homes', '?')} | Other: {defense.get('other', '?')}",
        f"  Multiplier: x{defense.get('multiplier', '?')}",
        "",
        "## Attack Estimation",
        f"  Tonight: {tonight} zombies",
        f"  Tomorrow: {tomorrow} zombies",
        "",
        "## Water",
        f"  Well: {water.get('well', '?')} | Bank rations: {water.get('bank', '?')}",
        "",
        f"## Citizens ({alive} alive — {inside} inside, {outside} outside)",
    ]
    # Citizen positions are auto-synced unless town is in chaos/devastated mode
    show_citizen_stale = meta.get("chaos") or meta.get("devastated")
    for c in citizens:
        loc = "IN TOWN" if c["inside_town"] else c["coords"]
        shaman = " [Shaman]" if c["is_shaman"] else ""
        stale = _staleness_tag(c.get("last_update_day"), current_day) if show_citizen_stale else ""
        lines.append(f"  {c['name']} ({c['job']}{shaman}) — {loc}{stale}")

    if detail != "compact":
        if deaths:
            lines.append("")
            lines.append(f"## Deaths ({len(deaths)})")
            for d in deaths:
                lines.append(f"  Day {d['day']}: {d['name']} — {d['cause']} (last at {d['last_coords']})")

        lines.append("")
        lines.append(f"## Bank ({len(bank)} items)")
        for item in bank:
            broken = " [BROKEN]" if item["broken"] else ""
            lines.append(f"  {item['name']}: {item['count']}{broken}")

    return "\n".join(lines)


def format_citizens(data: dict) -> str:
    """Format citizen positions and deaths."""
    if data.get("error"):
        return f"Error: {data['error']}"

    citizens = data["citizens"]
    deaths = data["deaths"]
    gate = data["gate"]
    meta = data["meta"]
    current_day = meta.get("day")
    show_citizen_stale = meta.get("chaos") or meta.get("devastated")

    inside = [c for c in citizens if c["inside_town"]]
    outside = [c for c in citizens if not c["inside_town"]]

    lines = [
        f"Gate: {gate.upper()}",
        f"{len(citizens)} citizens alive — {len(inside)} inside, {len(outside)} outside",
        "",
    ]

    if outside:
        lines.append("### Outside the town:")
        for c in outside:
            shaman = " [Shaman]" if c["is_shaman"] else ""
            stale = _staleness_tag(c.get("last_update_day"), current_day) if show_citizen_stale else ""
            lines.append(f"  {c['name']} ({c['job']}{shaman}) at {c['coords']}{stale}")
    else:
        lines.append("Everyone is inside the town.")

    if inside:
        lines.append("")
        lines.append("### Inside the town:")
        for c in inside:
            shaman = " [Shaman]" if c["is_shaman"] else ""
            lines.append(f"  {c['name']} ({c['job']}{shaman})")

    if deaths:
        lines.append("")
        lines.append(f"### Dead citizens ({len(deaths)}):")
        current_day = None
        for d in deaths:
            if d["day"] != current_day:
                current_day = d["day"]
                lines.append(f"  Day {current_day}:")
            lines.append(f"    {d['name']} — {d['cause']} (last at {d['last_coords']})")

    return "\n".join(lines)


def format_bank(data: dict) -> str:
    """Format bank inventory grouped by category."""
    if data.get("error"):
        return f"Error: {data['error']}"

    bank = data["bank"]
    meta = data["meta"]

    if not bank:
        return "The bank is empty."

    # Group by category
    by_cat: dict[str, list[dict]] = {}
    for item in bank:
        by_cat.setdefault(item["category"], []).append(item)

    lines = [
        f"## Bank Inventory — {meta.get('town_name', '?')} Day {meta.get('day', '?')}",
        f"{len(bank)} item types in the bank",
        "",
    ]
    for cat in sorted(by_cat.keys()):
        lines.append(f"### {cat}")
        for item in by_cat[cat]:
            broken = " [BROKEN]" if item["broken"] else ""
            lines.append(f"  {item['name']}: {item['count']}{broken}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bank summary — strategic grouping for context-efficient overview
# ---------------------------------------------------------------------------

# Items classified by strategic role.  Keys are English item names (as they
# come from Fata Morgana).  An item can appear in multiple buckets — that's
# fine, the summary sections are independent.
#
# Source: knowledge_base/processed/entities.json (wiki data).
# Damage tiers from killmin/killmax properties.

_FOOD_7AP = {
    # Max + 1 (7 AP) — wiki-verified
    "Apple", "Burnt Marshmallows", "Crawling crumble", "Egg",
    "Handful of Sweets", "Impressive Pumpkin", "Intestine Melon",
    "Sawdust Steak", "Spicy Chinese Noodles",
    "Tasty Homemade Dish", "Tasty-looking Steak",
    # Max + 2 (8 AP)
    "Christmas candy", "Overly tempting apple",
}
_FOOD_6AP = {
    # Max (6 AP) — wiki-verified
    "Chinese Noodles", "Chocolate log", "Dodgy Homemade Dish",
    "Dried Chewing Gum", "Fleshroom Puree", "Fleshroom Puree (infected)",
    "Half-eaten Chicken Wings", "Human Flesh", "Meaty Bone",
    "Mouldy Ham Sandwich", "Mouldy Twinkies",
    "Open Can", "Open Can (infected)",  # also counted as clean water
    "Out-of-Date Jaffa Cakes", "Packet of Soft Crisps",
    "Rancid Shortbread Pack", "Sandy Pretzel",
    "Seasonned fistful of insects",
    "Stale Tart", "Suspicious-looking Vegetable",
    "Suspicious-looking Vegetable (infected)",
    "Unspecified Meat",
}
_ALCOHOL = {
    # 6 AP + morale boost — can be drunk in ADDITION to eating food
    "Vodka Marinostov", "Stale Beer", "Sticky Pint",
    "Ergot Homebrew", "Mug of lukewarm liquid",
    "\u201cWake The Dead\u201d", '"Wake The Dead"',
}
_CLEAN_WATER = {
    # Items that provide clean water rations
    "Water Ration", "Purified Stagnant Water",
    "Open Can", "Open Can (infected)",
    "Water Cooler Bottle (1 ration)", "Water Cooler Bottle (2 rations)",
    "Water Cooler Bottle (3 rations)",
}
# Stagnant Water Can only counts as clean water when a Water Filter or
# Water Purifier building is present — handled dynamically in the formatter.
_CONDITIONAL_WATER = {"Stagnant Water Can"}
_FOOD_CONTAINERS = {
    # Openable containers that yield food (not food themselves)
    "Doggy Bag", "Food Parcel",
}
_AP_DRUGS = {
    "Anabolic Steroids", "Anabolic Steroids (infected)",
}
_HEALING = {
    "Bandage", "Paracetoid 7g",
}
_STATUS_DRUGS = {
    "Valium Shot", "Hydratone 100mg",
    "Little Book of Calm", "Unlabelled Drug",
    "Water Purifying Tablets", "Cyanohydric Capsule",
    "Twinoid Capsule", "Iodine Tincture",
}
_DEFENSE_ITEMS = {
    "Old Door", "Sheet Metal",
    "Trestle", "Solid Wooden Board", "Unshaped Concrete Blocks",
}
_METAL = {"Wrought Iron", "Scrap Metal", "Metal Support"}
_WOOD = {"Rotting Log", "Twisted Plank", "Patchwork Beam"}
_KEY_RESOURCES = {
    "Copper Pipe", "Handful of nuts and bolts", "Duct Tape",
    "Semtex", "Compact detonator",
    "Wire Reel", "Convex Lens", "Laser Diode",
    "Battery", "Mechanism", "Electronic component",
    "Broken Electronic Device", "Belt",
    "Bag of Cement", "Sheet of Plywood",
    "Sheet Metal (parts)", "Repair Kit",
    # Not resources, but important consumables to track
    "Flash Grenade", "Full Jerrycan",
    "Ness-Quick Weedkiller", "Pharmaceutical Products",
}
# killmax >= 2 — wiki-verified damage tiers
# Includes unloaded/empty variants: still strong once charged.
_STRONG_WEAPONS = {
    # Melee 2-2
    "Machete", "Lawnmower",
    # Battery 2-2 to 3-3 (loaded + empty)
    "Devastator (loaded)", "Devastator (empty)",
    "Chainsaw (loaded)", "Chainsaw (empty)",
    "Burning Laser Pointer (1 charge)", "Burning Laser Pointer (2 charges)",
    "Burning Laser Pointer (3 charges)", "Burning Laser Pointer (4 charges)",
    # Watergun 3-3 / 5-5 (loaded + empty)
    "Kalashni-Splash", "Kalashni-Splash (empty)",
    "Aqua-Splash (1 shot)", "Aqua-Splash (2 shots)",
    "Aqua-Splash (3 shots)", "Aqua-Splash (4 shots)",
    "Aqua-Splash (5 shots)", "Aqua-Splash (empty)",
    "Jerrycan Gun (ready)", "Jerrycan Gun (empty)",
    # Grenades 1-2 to 6-10
    "Exploding Water Bomb", "Exploding Grapefruit",
    "Water Bomb", "Mobile Phone",
}
# Construction blueprints — grouped by rarity tier
_BP_COMMON = {"Construction Blueprint (common)"}
_BP_UNCOMMON = {"Construction Blueprint (uncommon)"}
_BP_RARE = {"Construction Blueprint (rare)"}
_BP_VERY_RARE = {"Construction Blueprint (very rare!)"}
# Explorable ruin blueprints — unlock access to special ruins (higher priority)
_BP_RUIN = {
    "Bunker Construction Blueprint (uncommon)",
    "Bunker Construction Blueprint (rare)",
    "Bunker Construction Blueprint (very rare!)",
    "Hospital Construction Blueprint (uncommon)",
    "Hospital Construction Blueprint (rare)",
    "Hospital Construction Blueprint (very rare!)",
    "Hotel Construction Blueprint (uncommon)",
    "Hotel Construction Blueprint (rare)",
    "Hotel Construction Blueprint (very rare!)",
}
_ALL_BLUEPRINTS = _BP_COMMON | _BP_UNCOMMON | _BP_RARE | _BP_VERY_RARE | _BP_RUIN


def _sum_items(bank: list[dict], names: set[str], *, include_broken: bool = False) -> tuple[int, list[tuple[str, int, int]]]:
    """Return (total_count, [(name, count, broken), ...]) for items matching *names*.

    Merges multiple stacks of the same item (e.g. intact + broken Machete).
    """
    merged: dict[str, list[int]] = {}  # name -> [count, broken]
    for item in bank:
        if item["name"] in names:
            entry = merged.setdefault(item["name"], [0, 0])
            entry[0] += item["count"]
            entry[1] += item["broken"]
    matches: list[tuple[str, int, int]] = []
    total = 0
    for name, (count, broken) in merged.items():
        if not include_broken and count == 0:
            matches.append((name, 0, broken))
            continue
        matches.append((name, count, broken))
        total += count
    matches.sort(key=lambda t: (-t[1], t[0]))
    return total, matches


def _fmt_bucket(label: str, total: int, items: list[tuple[str, int, int]], *, show_items: bool = True) -> list[str]:
    """Format one summary bucket."""
    lines = [f"**{label}:** {total}"]
    if show_items and items:
        parts = []
        for name, count, broken in items:
            s = f"{name} ×{count}" if count else f"{name} (broken)"
            if broken and count:
                s += f" (+{broken} broken)"
            parts.append(s)
        lines.append("  " + ", ".join(parts))
    return lines


def format_bank_summary(data: dict) -> str:
    """Format a context-efficient bank summary with strategic groupings."""
    if data.get("error"):
        return f"Error: {data['error']}"

    bank = data["bank"]
    meta = data["meta"]

    if not bank:
        return "The bank is empty."

    total_items = sum(i["count"] for i in bank)
    total_types = len(bank)

    lines = [
        f"## Bank Summary — {meta.get('town_name', '?')} Day {meta.get('day', '?')}",
        f"{total_types} item types, {total_items} total items",
        "",
    ]

    # Clean water — check if Water Filter / Water Purifier is built
    buildings = data.get("buildings", [])
    has_purifier = any(
        b["built"] and b["name"] in ("Water Filter", "Water Purifier")
        for b in buildings
    )
    water_names = _CLEAN_WATER | (_CONDITIONAL_WATER if has_purifier else set())
    twater, itemswater = _sum_items(bank, water_names)
    purifier_note = " (incl. purifiable)" if has_purifier else ""
    lines.extend(_fmt_bucket(f"Clean water{purifier_note}", twater, itemswater))

    # Food
    t7, items7 = _sum_items(bank, _FOOD_7AP)
    t6, items6 = _sum_items(bank, _FOOD_6AP)
    tfc, itemsfc = _sum_items(bank, _FOOD_CONTAINERS)
    lines.extend(_fmt_bucket("Food 7+ AP", t7, items7))
    lines.extend(_fmt_bucket("Food 6 AP", t6, items6))
    if tfc:
        lines.extend(_fmt_bucket("Food containers", tfc, itemsfc))

    # Alcohol — separate category, can be drunk in addition to eating
    talc, itemsalc = _sum_items(bank, _ALCOHOL)
    lines.extend(_fmt_bucket("Alcohol (bonus to food)", talc, itemsalc))

    # Drugs & Meds
    tap, itemsap = _sum_items(bank, _AP_DRUGS)
    theal, itemsheal = _sum_items(bank, _HEALING)
    tstat, itemsstat = _sum_items(bank, _STATUS_DRUGS)
    lines.extend(_fmt_bucket("AP drugs", tap, itemsap))
    lines.extend(_fmt_bucket("Healing", theal, itemsheal))
    lines.extend(_fmt_bucket("Status drugs", tstat, itemsstat))

    # Defense consumables
    tdef, itemsdef = _sum_items(bank, _DEFENSE_ITEMS)
    lines.extend(_fmt_bucket("Defense items", tdef, itemsdef))

    # Construction materials — metal and wood summed, then other key resources
    tmetal, _ = _sum_items(bank, _METAL)
    twood, _ = _sum_items(bank, _WOOD)
    lines.append(f"**Metal:** {tmetal} (Iron + Scrap + Support)")
    lines.append(f"**Wood:** {twood} (Log + Plank + Beam)")
    tres, itemsres = _sum_items(bank, _KEY_RESOURCES)
    top5 = ", ".join(f"{n} ×{c}" for n, c, _ in itemsres[:5])
    lines.append(f"**Other resources:** {tres} ({top5}, …)")

    # Blueprints
    tbp_ruin, itemsbp_ruin = _sum_items(bank, _BP_RUIN)
    tbp_common, _ = _sum_items(bank, _BP_COMMON)
    tbp_uncommon, _ = _sum_items(bank, _BP_UNCOMMON)
    tbp_rare, _ = _sum_items(bank, _BP_RARE)
    tbp_vrare, _ = _sum_items(bank, _BP_VERY_RARE)
    if tbp_ruin or tbp_common or tbp_uncommon or tbp_rare or tbp_vrare:
        ruin_detail = ""
        if tbp_ruin:
            ruin_names = ", ".join(n.replace(" Construction Blueprint", "") for n, *_ in itemsbp_ruin)
            ruin_detail = f"; ruin: {tbp_ruin} ({ruin_names})"
        bp_parts = []
        for tier, count in (("common", tbp_common), ("uncommon", tbp_uncommon), ("rare", tbp_rare), ("very rare", tbp_vrare)):
            bp_parts.append(f"{tier} {count}")
        lines.append(f"**Blueprints:** {', '.join(bp_parts)}{ruin_detail}")

    # Weapons
    tweap, itemsweap = _sum_items(bank, _STRONG_WEAPONS, include_broken=True)
    lines.extend(_fmt_bucket("Strong weapons", tweap, itemsweap))
    # Count weak weapons: anything in Weapon category not in strong set
    weak_count = sum(i["count"] for i in bank
                     if i["category"] == "Weapon" and i["name"] not in _STRONG_WEAPONS)
    lines.append(f"**Weak weapons:** {weak_count}")

    # Furniture — count only
    tfurn = sum(i["count"] for i in bank if i["category"] == "Furniture")
    lines.append(f"**Furniture:** {tfurn} items")

    # Boxes / containers — count only
    boxes = [i for i in bank if i["category"] == "Box"]
    if boxes:
        tbox = sum(i["count"] for i in boxes)
        names = ", ".join(f"{i['name']} ×{i['count']}" for i in boxes)
        lines.append(f"**Containers:** {tbox} ({names})")

    # Uncategorised remainder — items not captured in any bucket above
    accounted = (_CLEAN_WATER | _CONDITIONAL_WATER
                 | _FOOD_7AP | _FOOD_6AP | _ALCOHOL | _FOOD_CONTAINERS
                 | _AP_DRUGS | _HEALING | _STATUS_DRUGS
                 | _DEFENSE_ITEMS | _METAL | _WOOD | _KEY_RESOURCES
                 | _STRONG_WEAPONS | _ALL_BLUEPRINTS)
    remainder = [i for i in bank
                 if i["name"] not in accounted
                 and i["category"] not in ("Weapon", "Furniture", "Box")]
    if remainder:
        lines.append(f"**Other:** {len(remainder)} types not shown (use detail='full' to see all)")

    lines.append("")
    lines.append("_Use get_bank_inventory(detail='full') for the complete item list._")

    return "\n".join(lines)


_RARITY_LABEL = {0: None, 1: "bp:common", 2: "bp:uncommon", 3: "bp:rare", 4: "bp:very rare"}


def _building_line(b: dict, show_day: bool = False) -> str:
    name = b["name"]
    if b.get("level") is not None:
        name += f" [Lv.{b['level']}]"
    parts = [f"  {name}"]
    details = []
    if show_day and b.get("built_day"):
        details.append(f"Day {b['built_day']}")
    if b["defense"]:
        details.append(f"+{b['defense']} def")
    if b["temporary"]:
        details.append("temporary")
    if details:
        parts.append(", ".join(details))
    return " — ".join(parts) if len(parts) > 1 else parts[0]


def _available_line(b: dict, locked: bool = False, include_resources: bool = False) -> str:
    parts = [f"  {b['name']}"]
    details = []
    if b["ap_cost"]:
        details.append(f"{b['ap_cost']} AP")
    if b["defense"]:
        details.append(f"+{b['defense']} def")
    if b["temporary"]:
        details.append("temporary")
    rarity_tag = _RARITY_LABEL.get(b.get("rarity", 0))
    if rarity_tag:
        details.append(f"[{rarity_tag}]")
    if locked and b.get("parent_name"):
        details.append(f"[needs: {b['parent_name']}]")
    if include_resources and b.get("resources"):
        res_str = ", ".join(f"{r['name']} ×{r['amount']}" for r in b["resources"])
        details.append(f"[{res_str}]")
    if details:
        parts.append(", ".join(details))
    return " — ".join(parts) if len(parts) > 1 else parts[0]


def _build_history_lines(built: list) -> list[str]:
    """Return lines for the full day-by-day construction history."""
    has_history = any(b.get("built_day") is not None for b in built)
    total_def = sum(b["defense"] for b in built)

    if not has_history:
        built_sorted = sorted(built, key=lambda b: b["name"].lower())
        lines = [f"### Built ({len(built)}, total defense: {total_def})"]
        for b in built_sorted:
            lines.append(_building_line(b))
        return lines

    day_builds: dict[int, list] = {}
    day_upgrades: dict[int, list] = {}

    for b in built:
        bd = b.get("built_day")
        if bd is not None:
            try:
                key = int(bd)
            except (ValueError, TypeError):
                key = 0
            day_builds.setdefault(key, []).append(b)

        udays = b.get("upgrade_days")
        if udays:
            for day_str, new_level in udays.items():
                try:
                    uday = int(day_str)
                    nlevel = int(new_level)
                except (ValueError, TypeError):
                    continue
                day_upgrades.setdefault(uday, []).append((b["name"], nlevel - 1, nlevel))

    all_days = sorted(set(day_builds.keys()) | set(day_upgrades.keys()))
    lines = [f"### Built — construction history (total defense from buildings: {total_def})"]
    for day_key in all_days:
        label = f"**Day {day_key}**" if day_key > 0 else "**Day ? (unknown)**"
        lines.append(label)
        for name, old_lv, new_lv in sorted(day_upgrades.get(day_key, []), key=lambda x: x[0].lower()):
            lines.append(f"  *(free vote)* {name}: Lv.{old_lv} → Lv.{new_lv}")
        for b in sorted(day_builds.get(day_key, []), key=lambda x: x["name"].lower()):
            lines.append(_building_line(b))
        lines.append("")
    return lines


def format_buildings(data: dict, mode: str = "summary", include_private: bool = False, include_resources: bool = False) -> str:
    """Format building list.

    mode:
      "summary"   — buildings constructed today only + running defense total
      "history"   — all built buildings grouped by construction day
      "available" — unbuilt buildings with AP cost, defense, blueprint requirement
    include_private: if False, exclude buildings with rarity>=5 (private/custom town only).
    include_resources: if True, append resource requirements to each available building line.
    """
    if data.get("error"):
        return f"Error: {data['error']}"

    buildings = data["buildings"]
    meta = data["meta"]

    if not buildings:
        return "No building data available."

    if not include_private:
        buildings = [b for b in buildings if b.get("rarity", 0) < 5]

    current_day = meta.get("day")
    built = [b for b in buildings if b["built"]]
    available = [b for b in buildings if not b["built"]]
    total_def = sum(b["defense"] for b in built)

    header = f"## Buildings — {meta.get('town_name', '?')} Day {current_day}"

    if mode == "summary":
        today = [b for b in built if b.get("built_day") == current_day]
        # Also collect upgrades that happened today
        today_upgrades: list[tuple[str, int, int]] = []
        for b in built:
            udays = b.get("upgrade_days") or {}
            for day_key, new_level in udays.items():
                if int(day_key) == current_day:
                    today_upgrades.append((b["name"], new_level - 1, new_level))

        lines = [header, f"{len(built)} built total — defense from buildings: {total_def}", ""]
        if not today and not today_upgrades:
            lines.append("No constructions today yet.")
        else:
            lines.append(f"### Built today (Day {current_day})")
            for name, old_lv, new_lv in sorted(today_upgrades, key=lambda x: x[0].lower()):
                lines.append(f"  *(free vote)* {name}: Lv.{old_lv} → Lv.{new_lv}")
            for b in sorted(today, key=lambda x: x["name"].lower()):
                lines.append(_building_line(b))
        return "\n".join(lines)

    if mode == "history":
        lines = [header, f"{len(built)} built, {len(available)} not yet built", ""]
        lines.extend(_build_history_lines(built))
        return "\n".join(lines)

    if mode == "available":
        available_sorted = sorted(available, key=lambda b: b["ap_cost"])
        # Split by prerequisite first
        prereq_ok = [b for b in available_sorted if b.get("parent_built", True)]
        prereq_locked = [b for b in available_sorted if not b.get("parent_built", True)]
        # Among prerequisite-ok: split by blueprint status
        # no_bp: rarity==0 (no blueprint needed at all)
        # bp_found: rarity>0 but blueprint already submitted → buildable
        # bp_blocked: rarity>0 and blueprint not yet found → NOT buildable
        no_bp = [b for b in prereq_ok if b.get("rarity", 0) == 0]
        bp_found = [b for b in prereq_ok if b.get("rarity", 0) > 0 and b.get("blueprint_found", False)]
        bp_blocked = [b for b in prereq_ok if b.get("rarity", 0) > 0 and not b.get("blueprint_found", False)]
        unlocked_count = len(no_bp) + len(bp_found)
        locked_count = len(bp_blocked) + len(prereq_locked)
        lines = [header, f"{len(built)} built — {unlocked_count} unlocked, {locked_count} locked — defense from buildings: {total_def}", ""]
        lines.append(f"### Unlocked — no blueprint needed ({len(no_bp)})")
        for b in no_bp:
            lines.append(_available_line(b, include_resources=include_resources))
        if bp_found:
            lines.append("")
            lines.append(f"### Unlocked — blueprint found ({len(bp_found)})")
            for b in bp_found:
                lines.append(_available_line(b, include_resources=include_resources))
        if bp_blocked:
            lines.append("")
            lines.append(f"### Locked — blueprint not found ({len(bp_blocked)})")
            for b in bp_blocked:
                lines.append(_available_line(b, locked=False, include_resources=include_resources))
        if prereq_locked:
            lines.append("")
            lines.append(f"### Locked — prerequisite not built ({len(prereq_locked)})")
            for b in prereq_locked:
                lines.append(_available_line(b, locked=True, include_resources=include_resources))
        return "\n".join(lines)

    return f"Unknown mode '{mode}'. Use: summary, history, available."


def format_scout(data: dict) -> str:
    """Format zombie counts per zone from scout data or map data.

    Prefers the `scout` dict when available, falls back to `zones` (map data).
    Map data uses zm: -1 = not scouted, 0 = clear, 1+ = zombie count.
    Each zone has independent freshness (updatedBy / updatedOnDay).
    """
    if data.get("error"):
        return f"Error: {data['error']}"

    meta = data["meta"]
    current_day = meta.get("day")

    # Combine map data (explored zones with danger levels, items, ruins) with
    # scout estimates (zombie counts for distant zones estimated by Scout profession).
    # Scout estimates cover zones not in the map data.
    map_zones = data.get("zones", [])
    scout_zones = data.get("scout", [])

    if not map_zones and not scout_zones:
        return "No scout or map data available."

    # Merge: scout zones that aren't already in map data
    map_coords = {z["coords"] for z in map_zones}
    scout_only = [z for z in scout_zones if z["coords"] not in map_coords]

    # Use map data — zm: -1 = not scouted, 0 = clear, 1+ = zombie count
    scouted = [z for z in map_zones if z["zombies"] >= 0]
    unscouted = [z for z in map_zones if z["zombies"] < 0]
    with_zombies = [z for z in scouted if z["zombies"] > 0]
    clear = [z for z in scouted if z["zombies"] == 0]
    total_zombies = sum(z["zombies"] for z in with_zombies)

    lines = [
        f"## Scout Map — {meta.get('town_name', '?')} Day {current_day}",
        f"{len(map_zones)} zones explored | {len(scouted)} scouted | {len(unscouted)} unscouted | {len(scout_only)} scout estimates | {total_zombies} zombies spotted",
        "",
    ]

    if with_zombies:
        with_zombies.sort(key=lambda z: z["zombies"], reverse=True)
        lines.append(f"### Zones with zombies ({len(with_zombies)})")
        for z in with_zombies:
            stale = _staleness_tag(z.get("updated_day"), current_day)
            who = f", by {z['updated_by']}" if z.get("updated_by") else ""
            lines.append(f"  {z['coords']}: {z['zombies']} zombies (day {z.get('updated_day', '?')}{who}){stale}")
        lines.append("")

    if clear:
        # Group clear zones by freshness
        fresh = [z for z in clear if z.get("updated_day") == current_day]
        older = [z for z in clear if z.get("updated_day") != current_day and z.get("updated_day") is not None]
        lines.append(f"### Clear zones ({len(clear)}: {len(fresh)} today, {len(older)} older)")
        if fresh:
            coords_list = ", ".join(z["coords"] for z in sorted(fresh, key=lambda z: z["coords"]))
            lines.append(f"  Today: {coords_list}")
        if older:
            # Show with day info
            older.sort(key=lambda z: z.get("updated_day", 0), reverse=True)
            by_day: dict[int, list[str]] = {}
            for z in older:
                d = z.get("updated_day", 0)
                by_day.setdefault(d, []).append(z["coords"])
            for d in sorted(by_day.keys(), reverse=True):
                coords_list = ", ".join(by_day[d])
                lines.append(f"  Day {d}: {coords_list}")
        lines.append("")

    if unscouted:
        # Split unscouted into those with danger info vs completely unknown
        with_danger = [z for z in unscouted if z.get("danger")]
        no_info = [z for z in unscouted if not z.get("danger")]
        lines.append(f"### Unscouted zones ({len(unscouted)})")
        if with_danger:
            # Group by danger level, show highest first
            with_danger.sort(key=lambda z: (-z["danger"], z["coords"]))
            for z in with_danger:
                dlevel = z["danger"]
                label = DANGER_LEVELS.get(dlevel, f"danger {dlevel}")
                lines.append(f"  {z['coords']}: ~{label}")
        if no_info:
            coords_list = ", ".join(z["coords"] for z in sorted(no_info, key=lambda z: z["coords"]))
            lines.append(f"  No data: {coords_list}")

    if scout_only:
        lines.append("")
        scout_only.sort(key=lambda z: z["zombies"], reverse=True)
        lines.append(f"### Scout estimates ({len(scout_only)} zones beyond explored map)")
        for z in scout_only:
            stale = _staleness_tag(z.get("scouted_day"), current_day)
            lines.append(f"  {z['coords']}: ~{z['zombies']} zombies (by {z['scouted_by']}, day {z['scouted_day']}){stale}")

    return "\n".join(lines)


def format_zones(data: dict) -> str:
    """Format detailed map zone data — ruins, items, zombies, danger."""
    if data.get("error"):
        return f"Error: {data['error']}"

    zones = data.get("zones", [])
    meta = data["meta"]

    if not zones:
        return "No map data available."

    # Separate ruins from regular zones
    ruin_zones = [z for z in zones if z.get("ruin")]
    item_zones = [z for z in zones if z.get("items") and not z.get("ruin")]

    lines = [
        f"## Zone Map — {meta.get('town_name', '?')} Day {meta.get('day', '?')}",
        f"{len(zones)} zones explored, {len(ruin_zones)} ruins found",
        "",
    ]

    current_day = meta.get("day")

    if ruin_zones:
        ruin_zones.sort(key=lambda z: z["ruin"]["name"])
        lines.append(f"### Ruins ({len(ruin_zones)})")
        for z in ruin_zones:
            r = z["ruin"]
            bp = " [BLUEPRINT]" if r.get("blueprint_available") else ""
            dried = " (dried)" if r.get("dried") else ""
            digs = f", {r['digs_remaining']} digs left" if r.get("digs_remaining") not in (None, "0", 0) else ""
            threat = _zone_threat(z)
            fresh = _zone_freshness(z, current_day)
            lines.append(f"  {z['coords']}: {r['name']}{bp}{dried}{digs}{threat}{fresh}")
            if z.get("items"):
                item_list = ", ".join(
                    f"{i['name']}x{i['count']}" + (" [B]" if i["broken"] else "")
                    for i in z["items"]
                )
                lines.append(f"    Items: {item_list}")
        lines.append("")

    # Show zones with items (non-ruin)
    if item_zones:
        item_zones.sort(key=lambda z: z["coords"])
        lines.append(f"### Zones with ground items ({len(item_zones)})")
        for z in item_zones:
            dried = " (dried)" if z.get("dried") else ""
            threat = _zone_threat(z)
            fresh = _zone_freshness(z, current_day)
            lines.append(f"  {z['coords']}{dried}{threat}{fresh}:")
            item_list = ", ".join(
                f"{i['name']}x{i['count']}" + (" [B]" if i["broken"] else "")
                for i in z["items"]
            )
            lines.append(f"    {item_list}")

    return "\n".join(lines)


def _parse_coords(zone: dict) -> tuple[int, int] | None:
    """Extract (rx, ry) integers from a zone's coords string '[rx|ry]'."""
    m = re.match(r"\[(-?\d+)\|(-?\d+)\]", zone.get("coords", ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def format_zone_path(
    data: dict,
    x1: int, y1: int,
    x2: int, y2: int,
    max_ap: int | None = None,
) -> str:
    """Format zones within a bounding box, sorted by AP cost then loot value.

    Useful for planning expeditions between two coordinates — shows AP cost per
    cell, items, ruins, zombie counts, and flags cells that exceed the AP budget.
    """
    if data.get("error"):
        return f"Error: {data['error']}"

    zones = data.get("zones", [])
    meta = data["meta"]

    if not zones:
        return "No map data available."

    # Bounding box: include all cells within the rectangle defined by (x1,y1)-(x2,y2)
    min_x, max_x = min(x1, x2), max(x1, x2)
    min_y, max_y = min(y1, y2), max(y1, y2)

    in_range = []
    for z in zones:
        coords = _parse_coords(z)
        if coords is None:
            continue
        rx, ry = coords
        if min_x <= rx <= max_x and min_y <= ry <= max_y:
            ap = abs(rx) + abs(ry)
            in_range.append((ap, z, rx, ry))

    current_day = meta.get("day")
    town = meta.get("town_name", "?")
    day = meta.get("day", "?")

    # Build full zone_map for spread simulation (all explored zones, not just bbox)
    zone_map: dict[tuple[int, int], dict] = {}
    for z in zones:
        c = _parse_coords(z)
        if c:
            zone_map[c] = z
    spread_map = _build_spread_map(zone_map, current_day if isinstance(current_day, int) else None)

    header_parts = [f"## Zone Path [{x1}|{y1}] → [{x2}|{y2}] — {town} Day {day}"]
    if max_ap is not None:
        header_parts.append(f"AP budget: {max_ap}")
    lines = [" | ".join(header_parts), ""]

    if not in_range:
        lines.append("No explored zones in this area.")
        return "\n".join(lines)

    # Sort by AP cost (cheapest first), then by loot count descending
    in_range.sort(key=lambda t: (t[0], -len(t[1].get("items", []))))

    over_budget = [t for t in in_range if max_ap is not None and t[0] > max_ap]
    in_budget = [t for t in in_range if max_ap is None or t[0] <= max_ap]

    def _render_zone(ap: int, z: dict, rx: int, ry: int, budget_exceeded: bool = False) -> list[str]:
        budget_flag = " [OVER BUDGET]" if budget_exceeded else ""
        threat = _zone_threat(z, current_day, spread_map=spread_map, coords=(rx, ry))
        fresh = _zone_freshness(z, current_day)
        dried = " (dried)" if z.get("dried") else ""
        ruin = z.get("ruin")

        if ruin:
            bp = " [BLUEPRINT]" if ruin.get("blueprint_available") else ""
            digs = f", {ruin['digs_remaining']} digs left" if ruin.get("digs_remaining") not in (None, "0", 0) else ""
            label = f"{ruin['name']}{bp}{digs}"
        else:
            label = "open zone"

        entry = [f"  {z['coords']} ({ap} AP){budget_flag}{dried}: {label}{threat}{fresh}"]
        if z.get("items"):
            item_list = ", ".join(
                f"{i['name']}x{i['count']}" + (" [B]" if i["broken"] else "")
                for i in z["items"]
            )
            entry.append(f"    Items: {item_list}")
        return entry

    if in_budget:
        lines.append(f"### Zones in range ({len(in_budget)})")
        for ap, z, rx, ry in in_budget:
            lines.extend(_render_zone(ap, z, rx, ry))
        lines.append("")

    if over_budget:
        lines.append(f"### Beyond AP budget ({len(over_budget)})")
        for ap, z, rx, ry in over_budget:
            lines.extend(_render_zone(ap, z, rx, ry, budget_exceeded=True))

    return "\n".join(lines)


# Risk weight assigned to cells with no scout data, only a danger level estimate.
# Midpoints of each danger band (0 zombies / 1-2 / 3-5 / 6+).
_DANGER_RISK = {0: 0, 1: 1.5, 2: 4.0, 3: 6.0}

# Risk penalty for cells with no information at all (unexplored).
# Set above the highest danger band so known-clear paths are preferred,
# but unknown cells are still traversable when no other route exists.
_UNKNOWN_RISK = 8.0

MAX_PATH_AP = 40

# CP-aware trap penalties (added to base zombie risk in safest-path Dijkstra).
_TRAP_PENALTY_CERTAIN = 50.0   # Fresh data confirms zombies >= group_cp
_TRAP_PENALTY_STALE = 20.0     # Stale/estimated zombies >= group_cp

# Scout detection cost: detection_probability * this = risk added per cell.
_SCOUT_DETECTION_COST = 50.0


def _scout_detection(zone_zombies: int, total_cp: int) -> tuple[float, float]:
    """Estimate scout camouflage detection probability (day, night).

    Returns (day_pct, night_pct) as floats in [0.0, 1.0].
    Assumes scout_level=0 (worst case — actual level unavailable from Fata Morgana).
    """
    import math
    if zone_zombies <= total_cp:
        return (0.0, 0.0)
    zeds_above = zone_zombies - total_cp
    delta_base = math.floor(zeds_above * 1.3)

    def _calc(night: bool) -> float:
        d = delta_base
        if night:
            d -= 5
        if d <= 6:
            d *= 0.5
        return max(0.0, d) / 100.0

    return (_calc(False), _calc(True))


def _classify_cell(
    zone: dict | None,
    current_day: int | None,
    coords: tuple[int, int] | None,
    spread_map: dict | None,
    group_cp: int,
) -> dict:
    """Classify a cell for CP-aware pathfinding.

    Returns a dict with:
      tag: "CLEAR" | "SAFE" | "TRAPPED" | "TRAP_RISK" | "STALE" | "UNKNOWN"
      zombies: int | None — best zombie estimate (current or projected)
      fresh: bool — whether data is from the current day
      age: int — days since last update (-1 if unknown)
    """
    if zone is None:
        return {"tag": "UNKNOWN", "zombies": None, "fresh": False, "age": -1}

    zm = zone.get("zombies", -1)

    # Explored but unscouted — only danger level available
    if zm < 0:
        danger = zone.get("danger", 0)
        est = {0: 0, 1: 1, 2: 4, 3: 6}.get(danger)
        tag = "TRAP_RISK" if est is not None and est > group_cp else "STALE"
        return {"tag": tag, "zombies": est, "fresh": False, "age": -1}

    last_day = zone.get("updated_day") or zone.get("scouted_day")
    age = (current_day - last_day) if (current_day and last_day) else 0
    fresh = age == 0

    if zm == 0:
        # Check spread risk
        if spread_map is not None and coords is not None and age > 0:
            spread = _spread_risk_for_clear(coords, age, spread_map)
            if spread is not None:
                _, est = spread
                if est > group_cp:
                    return {"tag": "TRAP_RISK", "zombies": est, "fresh": False, "age": age}
                return {"tag": "SAFE", "zombies": est, "fresh": False, "age": age}
        return {"tag": "CLEAR", "zombies": 0, "fresh": fresh, "age": age}

    # zm > 0: compute pessimistic estimate
    est = _zombie_max_estimate(zm, last_day, current_day)
    effective = est if est is not None else zm

    if effective > group_cp:
        if fresh:
            return {"tag": "TRAPPED", "zombies": effective, "fresh": True, "age": 0}
        return {"tag": "TRAP_RISK", "zombies": effective, "fresh": False, "age": age}

    return {"tag": "SAFE", "zombies": effective, "fresh": fresh, "age": age}


def _cell_risk(
    zone: dict | None,
    current_day: int | None = None,
    coords: tuple[int, int] | None = None,
    spread_map: dict | None = None,
    *,
    group_cp: int = 2,
    scout_mode: bool = False,
    mode: str = "safest",
) -> float:
    """Return the risk cost for a single cell.

    Modes:
      "safest"  — minimise zombie exposure; trapped cells get heavy penalty.
      "shortest" — minimise AP (cost=1 per cell); trapped cells are inf
                   unless scout_mode (then detection cost). Flash consumption
                   is handled by the Dijkstra caller, not here.

    When group_cp/scout_mode are at defaults, behavior matches the original
    zombie-exposure-only model.
    """
    classification = _classify_cell(zone, current_day, coords, spread_map, group_cp)
    tag = classification["tag"]
    zombies = classification["zombies"]

    # Base zombie risk (used by safest mode and as tiebreaker)
    if zone is None:
        base_risk = _UNKNOWN_RISK
    elif zombies is not None:
        base_risk = float(zombies)
    else:
        danger = zone.get("danger", 0) if zone else 0
        base_risk = _DANGER_RISK.get(danger, _UNKNOWN_RISK)

    if mode == "shortest":
        # Shortest mode: cost = 1 per cell (pure AP), with trap handling
        if tag in ("TRAPPED", "TRAP_RISK"):
            if scout_mode:
                zm_est = zombies if zombies is not None else int(base_risk)
                day_pct, _ = _scout_detection(zm_est, group_cp)
                return 1.0 + day_pct * _SCOUT_DETECTION_COST * 0.01
            # Non-scout trapped: caller handles flash logic; return inf to block
            return float("inf")
        return 1.0 + base_risk * 0.001  # epsilon tiebreaker

    # Safest mode
    if tag == "TRAPPED":
        if scout_mode:
            zm_est = zombies if zombies is not None else int(base_risk)
            day_pct, _ = _scout_detection(zm_est, group_cp)
            return base_risk + max(day_pct, 0.01) * _SCOUT_DETECTION_COST
        return base_risk + _TRAP_PENALTY_CERTAIN
    if tag == "TRAP_RISK":
        if scout_mode:
            zm_est = zombies if zombies is not None else int(base_risk)
            day_pct, _ = _scout_detection(zm_est, group_cp)
            return base_risk + max(day_pct, 0.01) * _SCOUT_DETECTION_COST * 0.5
        return base_risk + _TRAP_PENALTY_STALE
    if tag == "UNKNOWN":
        return _UNKNOWN_RISK

    return base_risk


def find_safe_path(
    data: dict,
    x1: int, y1: int,
    x2: int, y2: int,
    *,
    group_cp: int = 2,
    escape_items: int = 0,
    scout_mode: bool = False,
) -> str:
    """Find paths between two map coordinates using CP-aware Dijkstra.

    Returns up to two paths:
      - Safest: minimises zombie exposure, avoids traps entirely.
      - Shortest: minimises AP, using escape items to pass through traps.
    If both paths are identical, only one is shown.

    Args:
        group_cp: Total Control Points of the party (default 2 = solo citizen).
        escape_items: Flash-grenade-equivalent items carried (each neutralises one trap).
        scout_mode: Scout with Camouflage Vest — traps become passable at detection risk.
    """
    if data.get("error"):
        return f"Error: {data['error']}"

    meta = data["meta"]
    current_day = meta.get("day", "?")
    town = meta.get("town_name", "?")

    # -- Shared pre-computation (used by both Dijkstra runs) --
    zone_map: dict[tuple[int, int], dict] = {}
    for z in data.get("zones", []):
        coords = _parse_coords(z)
        if coords:
            zone_map[coords] = z
    map_coords = set(zone_map.keys())
    for z in data.get("scout", []):
        coords = _parse_coords(z)
        if coords and coords not in map_coords:
            zone_map[coords] = {"coords": z["coords"], "zombies": z["zombies"], "danger": 0, "items": [], "ruin": None, "scouted_day": z.get("scouted_day")}

    cd = current_day if isinstance(current_day, int) else None
    spread_map = _build_spread_map(zone_map, cd)
    ap_limit = MAX_PATH_AP

    # Pre-classify all cells (shared cache for both runs + output formatting)
    cell_class: dict[tuple[int, int], dict] = {}
    for c, z in zone_map.items():
        cell_class[c] = _classify_cell(z, cd, c, spread_map, group_cp)

    # Bounding box + margin for unknown-cell traversal
    margin = 3
    box_min_x, box_max_x = min(x1, x2) - margin, max(x1, x2) + margin
    box_min_y, box_max_y = min(y1, y2) - margin, max(y1, y2) + margin

    def _in_box(nx: int, ny: int) -> bool:
        return box_min_x <= nx <= box_max_x and box_min_y <= ny <= box_max_y

    # -- Dijkstra runner --
    def _run_dijkstra(
        mode: str,
        flash_budget: int = 0,
    ) -> tuple[float, int, list[tuple[int, int]], int, set[tuple[int, int]]] | None:
        """Returns (cost, ap, path, flashes_used, flash_cells) or None."""
        # State: (primary_cost, secondary_cost, x, y, path, flashes_used)
        heap: list[tuple[float, float, int, int, list[tuple[int, int]], int]] = []
        heapq.heappush(heap, (0.0, 0.0, x1, y1, [(x1, y1)], 0))
        # Visited: (x, y, flashes_used) -> (best_primary, best_secondary)
        visited: dict[tuple[int, int, int], tuple[float, float]] = {}

        best: tuple[float, float, list[tuple[int, int]], int] | None = None

        while heap:
            pri, sec, x, y, path, flashes = heapq.heappop(heap)

            if (x, y) == (x2, y2):
                if best is None or (pri, sec) < (best[0], best[1]):
                    best = (pri, sec, path, flashes)
                continue

            vkey = (x, y, flashes)
            if vkey in visited:
                prev_pri, prev_sec = visited[vkey]
                if pri >= prev_pri and sec >= prev_sec:
                    continue
            visited[vkey] = (pri, sec)

            ap_so_far = int(sec) if mode == "safest" else int(pri)
            if ap_so_far >= ap_limit:
                continue

            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                next_zone = zone_map.get((nx, ny))
                if next_zone is None and not _in_box(nx, ny):
                    continue

                cc = cell_class.get((nx, ny), {"tag": "UNKNOWN"})
                is_trap = cc["tag"] in ("TRAPPED", "TRAP_RISK")

                # Determine cost and whether a flash is consumed
                new_flashes = flashes
                if mode == "shortest":
                    if is_trap and not scout_mode:
                        if flashes < flash_budget:
                            new_flashes = flashes + 1
                            step_pri = 1.0  # AP cost
                            step_sec = 0.0  # no extra risk (flash clears it)
                        else:
                            continue  # impassable without flash or scout
                    else:
                        risk = _cell_risk(next_zone, cd, coords=(nx, ny), spread_map=spread_map,
                                          group_cp=group_cp, scout_mode=scout_mode, mode="shortest")
                        if risk == float("inf"):
                            continue
                        step_pri = 1.0   # AP
                        step_sec = risk  # risk as tiebreaker
                    next_pri = pri + step_pri
                    next_sec = sec + step_sec
                else:  # safest
                    risk = _cell_risk(next_zone, cd, coords=(nx, ny), spread_map=spread_map,
                                      group_cp=group_cp, scout_mode=scout_mode, mode="safest")
                    step_pri = risk   # risk
                    step_sec = 1.0    # AP as tiebreaker
                    next_pri = pri + step_pri
                    next_sec = sec + step_sec

                new_ap = int(next_sec) if mode == "safest" else int(next_pri)
                if new_ap > ap_limit:
                    continue

                heapq.heappush(heap, (next_pri, next_sec, nx, ny, path + [(nx, ny)], new_flashes))

        if best is None:
            return None
        pri, sec, path, flashes = best
        # Determine which cells consumed a flash (shortest mode only)
        flash_cells: set[tuple[int, int]] = set()
        if flash_budget > 0 and flashes > 0:
            # Walk the path and identify trap cells (first N traps = flash cells)
            count = 0
            for px, py in path:
                if count >= flashes:
                    break
                cc = cell_class.get((px, py), {"tag": "UNKNOWN"})
                if cc["tag"] in ("TRAPPED", "TRAP_RISK"):
                    flash_cells.add((px, py))
                    count += 1
        total_risk = sec if mode == "safest" else pri  # secondary is AP for safest
        total_ap = int(sec) if mode == "safest" else int(pri)
        total_risk_val = pri if mode == "safest" else sec
        return (total_risk_val, total_ap, path, flashes, flash_cells)

    # -- Run both Dijkstra passes --
    safest = _run_dijkstra("safest")
    shortest = _run_dijkstra("shortest", flash_budget=escape_items) if escape_items > 0 or scout_mode else None

    # If shortest would be identical to safest, skip it
    if shortest is not None and safest is not None:
        if shortest[2] == safest[2]:
            shortest = None

    # -- Format output --
    lines = [f"## Pathfinding [{x1}|{y1}] → [{x2}|{y2}] — {town} Day {current_day}"]
    params = [f"Group CP: {group_cp}"]
    if scout_mode:
        params.append("Scout: Yes")
    if escape_items > 0:
        params.append(f"Flash items: {escape_items}")
    lines.append(" | ".join(params))
    lines.append("")

    # Summary
    if safest is None and shortest is None:
        lines.append(f"No path found within {ap_limit} AP.")
        return "\n".join(lines)

    lines.append("### Summary")
    if safest is not None:
        s_risk, s_ap, s_path, _, _ = safest
        trap_count = sum(1 for p in s_path if cell_class.get(p, {}).get("tag") in ("TRAPPED", "TRAP_RISK"))
        lines.append(f"Safest: {s_ap} AP, {s_risk:.0f} exposure, {trap_count} trap zones on route")
    if shortest is not None:
        sh_risk, sh_ap, sh_path, sh_flashes, _ = shortest
        lines.append(f"Shortest: {sh_ap} AP, {sh_risk:.1f} exposure, {sh_flashes} flash items used")
    elif safest is not None:
        lines.append("Shortest path is identical to safest.")
    lines.append("")

    def _format_zom_str(z: dict | None, px: int, py: int) -> str:
        if z is None:
            return "unexplored"
        zm = z.get("zombies", -1)
        if zm >= 0:
            last_day = z.get("updated_day") or z.get("scouted_day")
            age = (cd - last_day) if (cd and last_day) else 0
            if zm == 0:
                spread = _spread_risk_for_clear((px, py), age, spread_map) if age > 0 else None
                if spread is not None:
                    bfs_dist, est = spread
                    return f"clear→≤{est} zom (spread risk, {bfs_dist}d away)"
                return "clear"
            est = _zombie_max_estimate(zm, last_day, cd)
            return f"{zm} zom→≤{est} (est.)" if est is not None else f"{zm} zom"
        danger = z.get("danger", 0)
        return f"~{DANGER_LEVELS.get(danger, 'unknown')}"

    def _format_step(
        i: int, px: int, py: int,
        flash_cells: set[tuple[int, int]] | None = None,
        total_flashes: int = 0,
        flash_counter: list[int] | None = None,
    ) -> str:
        z = zone_map.get((px, py))
        ap_here = abs(px) + abs(py)
        coord_str = f"[{px}|{py}]"
        zom_str = _format_zom_str(z, px, py)

        # CP status tag
        cc = cell_class.get((px, py), {"tag": "UNKNOWN"})
        tag = cc["tag"]

        if flash_cells and (px, py) in flash_cells:
            if flash_counter is not None:
                flash_counter[0] += 1
            idx = flash_counter[0] if flash_counter else 1
            tag_str = f" [NEEDS FLASH {idx}/{total_flashes}]"
        elif tag == "TRAPPED":
            if scout_mode:
                zm_est = cc.get("zombies") or 0
                day_pct, night_pct = _scout_detection(zm_est, group_cp)
                tag_str = f" [SCOUT OK: {night_pct:.0%}-{day_pct:.0%}]"
            else:
                tag_str = " [TRAPPED]"
        elif tag == "TRAP_RISK":
            if scout_mode:
                zm_est = cc.get("zombies") or 0
                day_pct, night_pct = _scout_detection(zm_est, group_cp)
                if day_pct > 0:
                    tag_str = f" [SCOUT OK: {night_pct:.0%}-{day_pct:.0%}]"
                else:
                    tag_str = " [TRAP RISK]"
            else:
                tag_str = " [TRAP RISK]"
        elif tag == "CLEAR":
            tag_str = " [CLEAR]"
        elif tag == "SAFE":
            tag_str = " [SAFE]"
        elif tag == "UNKNOWN":
            tag_str = ""
        else:
            tag_str = ""

        stale = _staleness_tag(z.get("updated_day"), cd) if z else ""

        ruin = z.get("ruin") if z else None
        ruin_str = f" | {ruin['name']}" if ruin else ""
        items = z.get("items", []) if z else []
        items_str = ""
        if items:
            items_str = " | Items: " + ", ".join(
                f"{it['name']}x{it['count']}" + (" [B]" if it["broken"] else "")
                for it in items
            )

        return f"  {i:>2}. {coord_str} ({ap_here} AP from gate) — {zom_str}{tag_str}{ruin_str}{items_str}{stale}"

    def _render_path(
        label: str,
        result: tuple,
    ) -> None:
        risk, ap, path, flashes, flash_cells = result
        lines.append(f"### {label}")
        counter = [0]  # mutable counter for flash numbering
        for i, (px, py) in enumerate(path):
            lines.append(_format_step(i, px, py, flash_cells=flash_cells, total_flashes=flashes, flash_counter=counter))
        lines.append("")

    if safest is not None:
        if shortest is None:
            _render_path("Path (safest = shortest)" if escape_items == 0 and not scout_mode else "Safest Path", safest)
        else:
            _render_path("Safest Path", safest)

    if shortest is not None:
        _render_path("Shortest Path", shortest)

    return "\n".join(lines)


def format_defense(data: dict, gh_defense: dict | None = None) -> str:
    """Format defense breakdown and attack estimation.

    Args:
        data: Fata Morgana town data dict.
        gh_defense: Optional Gest'Hordes current-day defence breakdown from
                    gesthordes.extract_current_defense(). Adds watchers,
                    temporary, and dead_bonus lines that Fata lumps into 'other'.
    """
    if data.get("error"):
        return f"Error: {data['error']}"

    defense = data["defense"]
    est = data["estimations"]
    gate = data["gate"]

    total = defense.get("total", 0)
    today_est = est.get("today", {})
    low = today_est.get("min")
    high = today_est.get("max")
    tonight = _format_estimate(today_est)

    tomorrow_est = est.get("tomorrow", {})
    tomorrow = _format_estimate(tomorrow_est)

    survival = ""
    if low is not None and high is not None:
        if total >= high:
            survival = " -> SAFE (defense exceeds max estimate)"
        elif total >= low:
            survival = f" -> AT RISK (defense covers min, {high - total} short of max)"
        else:
            survival = f" -> DANGER ({low - total} defense short of minimum estimate)"

    lines = [
        f"## Defense Analysis — Gate: {gate.upper()}{survival}",
        "",
        f"Total defense: {total}",
        f"  Wall base: {defense.get('base', '?')}",
        f"  Buildings: {defense.get('buildings', '?')}",
        f"  Defense items: {defense.get('items', '?')} (x{defense.get('multiplier', '?')} multiplier)",
        f"  Guardians: {defense.get('guardians', '?')}",
        f"  Homes: {defense.get('homes', '?')}",
        f"  Upgrades: {defense.get('upgrades', '?')}",
    ]

    other = defense.get("other", 0) or 0
    if gh_defense is not None:
        watchers = gh_defense.get("watchers", 0)
        temporary = gh_defense.get("temporary", 0)
        dead_bonus = gh_defense.get("dead_bonus", 0)
        lines.append(f"  Watchmen: {watchers}")
        lines.append(f"  Temporary bonuses: {temporary}")
        lines.append(f"  Dead-citizen bonus: {dead_bonus}")
        gh_accounted = watchers + temporary + dead_bonus
        remainder = other - gh_accounted
        if remainder != 0:
            lines.append(f"  Other (unaccounted): {remainder}")
        lines.append("  (Gest'Hordes breakdown)")
    else:
        lines.append(f"  Other sources: {other}")

    lines += [
        "",
        f"Tonight's attack: {tonight} zombies",
        f"Tomorrow's attack: {tomorrow} zombies",
    ]

    # Add estimation history
    history = est.get("history", {})
    if history:
        lines.append("")
        lines.append("### Attack history:")
        for day_str in sorted(history.keys(), key=int):
            e = history[day_str]
            lines.append(f"  Day {day_str}: {_format_estimate(e)}")

    return "\n".join(lines)
