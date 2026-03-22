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

import json
import re
import time

import httpx

FATA_SPY_URL = "https://fatamorgana.md26.eu/spy/town/{town_id}"
FATA_SPY_DAY_URL = "https://fatamorgana.md26.eu/spy/town/{town_id}/{day}"

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

    # Return cached result if fresh
    now = time.monotonic()
    if url in _cache:
        cached_at, cached_data = _cache[url]
        if now - cached_at < CACHE_TTL:
            return cached_data

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return {"error": f"Fata Morgana returned HTTP {e.response.status_code}"}
    except httpx.RequestError as e:
        return {"error": f"Could not reach Fata Morgana: {e}"}

    html = resp.text
    js_data = _extract_js_data(html)
    if not js_data:
        return {"error": "Could not parse town data from Fata Morgana page."}

    sys = js_data.get("system", {})
    current_day = sys.get("day")

    def _as_dict(val, default=None):
        """Return val if it's a dict, otherwise default (handles [] from empty fields)."""
        return val if isinstance(val, dict) else (default or {})

    result = {
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
    _cache[url] = (now, result)
    return result


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
        })
    bank.sort(key=lambda i: i["name"].lower())
    return bank


def _parse_buildings(js_data: dict) -> list[dict]:
    """Extract building list from bpsAndConstructions.

    The `constructions` dict tells us which buildings are built and their
    current upgrade level (if upgradeable). The `constructionHistory` dict
    provides the day each building was built and when each upgrade happened.
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
    built_ids = set(constructions.keys())
    buildings = []
    for bid, b in bps.items():
        name_dict = b.get("name", {})
        name = name_dict.get("en") or name_dict.get("fr") or next(iter(name_dict.values()), f"Building {bid}")
        con = constructions.get(bid, {})
        hist = history.get(bid, {})
        level = con.get("level")  # None if not upgradeable
        buildings.append({
            "id": bid,
            "name": name,
            "defense": b.get("def", 0),
            "ap_cost": b.get("paCurrent", 0),
            "temporary": b.get("temporary", False),
            "built": bid in built_ids,
            "level": level,
            "built_day": hist.get("built"),
            "upgrade_days": hist.get("voted") if isinstance(hist.get("voted"), dict) else None,
        })
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
                    "digs_remaining": bld.get("dig"),
                    "blueprint_available": bld.get("blueprint", 0) == 0,
                    "dried": bld.get("dried", 0),
                }

            entry = {
                "coords": f"[{rx}|{ry}]",
                "zombies": zone.get("zm", 0),
                "zombies_max": zone.get("z", 0),
                "danger": zone.get("danger", 0),
                "dried": zone.get("dried", 0),
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


def _zone_threat(zone: dict) -> str:
    """Format zombie count or danger estimate for a zone.

    If an exact zombie count was reported (zm >= 0), show it.
    Otherwise fall back to the danger level from in-game map exploration.
    """
    zm = zone.get("zombies", 0)
    if zm is not None and zm >= 0:
        if zm == 0:
            return ""
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

def format_town_overview(data: dict) -> str:
    """Format a complete town overview."""
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

    lines = [
        f"# {meta.get('town_name', 'Unknown Town')} — Day {meta.get('day', '?')}",
        f"Season {meta.get('season', '?')} | Type: {meta.get('game_type', '?')} | Region: {meta.get('region', '?')}"
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


def format_buildings(data: dict) -> str:
    """Format building list with defense values and construction status."""
    if data.get("error"):
        return f"Error: {data['error']}"

    buildings = data["buildings"]
    meta = data["meta"]

    if not buildings:
        return "No building data available."

    built = [b for b in buildings if b["built"]]
    available = [b for b in buildings if not b["built"]]

    lines = [
        f"## Buildings — {meta.get('town_name', '?')} Day {meta.get('day', '?')}",
        f"{len(built)} built, {len(available)} available to build",
        "",
    ]

    if built:
        built.sort(key=lambda b: b["name"].lower())
        total_def = sum(b["defense"] for b in built)
        lines.append(f"### Built ({len(built)}, total defense: {total_def})")
        for b in built:
            name = b["name"]
            if b.get("level") is not None:
                name += f" [Lv.{b['level']}]"
            parts = [f"  {name}"]
            if b["defense"]:
                parts.append(f"+{b['defense']} def")
            if b["temporary"]:
                parts.append("(temporary)")
            lines.append(" — ".join(parts) if len(parts) > 1 else parts[0])
        lines.append("")

    if available:
        available.sort(key=lambda b: b["ap_cost"])
        lines.append(f"### Available to build ({len(available)})")
        for b in available:
            parts = [f"  {b['name']}"]
            details = []
            if b["ap_cost"]:
                details.append(f"{b['ap_cost']} AP")
            if b["defense"]:
                details.append(f"+{b['defense']} def")
            if b["temporary"]:
                details.append("temporary")
            if details:
                parts.append(", ".join(details))
            lines.append(" — ".join(parts) if len(parts) > 1 else parts[0])

    return "\n".join(lines)


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


def format_defense(data: dict) -> str:
    """Format defense breakdown and attack estimation."""
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
        f"  Other sources: {defense.get('other', '?')}",
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
