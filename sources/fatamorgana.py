"""Fata Morgana spy page scraper — httpx only, no browser needed.

Fetches the spy page for a given town ID and extracts the embedded
`var data = {...}` JavaScript object which contains all town state:
- Town metadata (name, day, season, game type)
- Defense breakdown and attack estimations
- Water supply
- Gate status (door)
- Citizen positions and jobs
- Dead citizens (cadavers) with cause of death
- Bank inventory with item names
- Scout data (zombie counts per zone)
- Buildings and construction history
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

# Fata job key → display name
JOB_NAMES = {
    "basic": "Resident",
    "guardian": "Guardian",
    "hunter": "Scavenger",
    "collec": "Collector",
    "scout": "Scout",
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
    town_x = js_data.get("ox", 0)
    town_y = js_data.get("oy", 0)
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
    """Extract building list from bpsAndConstructions."""
    bps = js_data.get("bpsAndConstructions", {})
    if not isinstance(bps, dict):
        bps = {}
    constructions = js_data.get("constructions", {})
    if not isinstance(constructions, dict):
        constructions = {}
    built_ids = set(constructions.keys())
    buildings = []
    for bid, b in bps.items():
        name_dict = b.get("name", {})
        name = name_dict.get("en") or name_dict.get("fr") or next(iter(name_dict.values()), f"Building {bid}")
        buildings.append({
            "id": bid,
            "name": name,
            "defense": b.get("def", 0),
            "ap_cost": b.get("paCurrent", 0),
            "temporary": b.get("temporary", False),
            "built": bid in built_ids,
        })
    return buildings


def _parse_scout(js_data: dict) -> list[dict]:
    """Extract scout data (zombie counts per zone)."""
    scout_raw = js_data.get("scout", {})
    if not isinstance(scout_raw, dict):
        scout_raw = {}
    zones = []
    for key, info in scout_raw.items():
        m = re.match(r"y(-?\d+)x(-?\d+)", key)
        if not m:
            continue
        zones.append({
            "coords": f"[{m.group(2)}|{m.group(1)}]",
            "zombies": int(info.get("zom", 0)),
            "scouted_by": info.get("updatedBy", "Unknown"),
            "scouted_day": info.get("updatedOnDay"),
        })
    return zones


# ---------------------------------------------------------------------------
# Formatters — turn parsed data into human-readable strings for the LLM
# ---------------------------------------------------------------------------

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
    bank = data["bank"]

    alive = len(citizens)
    inside = sum(1 for c in citizens if c["inside_town"])
    outside = alive - inside

    today_est = est.get("today", {})
    tonight = f"{today_est['min']}-{today_est['max']}" if today_est.get("min") is not None else "???"
    tomorrow_est = est.get("tomorrow", {})
    tomorrow = f"{tomorrow_est['min']}-{tomorrow_est['max']}" if tomorrow_est.get("min") is not None else "???"

    lines = [
        f"# {meta.get('town_name', 'Unknown Town')} — Day {meta.get('day', '?')}",
        f"Season {meta.get('season', '?')} | Type: {meta.get('game_type', '?')} | Region: {meta.get('region', '?')}",
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
    for c in citizens:
        loc = "IN TOWN" if c["inside_town"] else c["coords"]
        shaman = " [Shaman]" if c["is_shaman"] else ""
        lines.append(f"  {c['name']} ({c['job']}{shaman}) — {loc}")

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
            lines.append(f"  {c['name']} ({c['job']}{shaman}) at {c['coords']}")
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
            parts = [f"  {b['name']}"]
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
    """Format scout data showing zombie counts per zone."""
    if data.get("error"):
        return f"Error: {data['error']}"

    zones = data["scout"]
    meta = data["meta"]

    if not zones:
        return "No scout data available. Zones haven't been scouted yet."

    # Sort by zombie count descending for threat prioritization
    zones_sorted = sorted(zones, key=lambda z: z["zombies"], reverse=True)
    total_zombies = sum(z["zombies"] for z in zones_sorted)
    scouted_count = len(zones_sorted)

    lines = [
        f"## Scout Map — {meta.get('town_name', '?')} Day {meta.get('day', '?')}",
        f"{scouted_count} zones scouted, {total_zombies} total zombies spotted",
        "",
    ]

    # Group into threat levels
    dangerous = [z for z in zones_sorted if z["zombies"] >= 10]
    moderate = [z for z in zones_sorted if 3 <= z["zombies"] < 10]
    low = [z for z in zones_sorted if 1 <= z["zombies"] < 3]
    clear = [z for z in zones_sorted if z["zombies"] == 0]

    if dangerous:
        lines.append(f"### Dangerous zones ({len(dangerous)}, 10+ zombies)")
        for z in dangerous:
            lines.append(f"  {z['coords']}: {z['zombies']} zombies (scouted by {z['scouted_by']}, day {z['scouted_day']})")
        lines.append("")

    if moderate:
        lines.append(f"### Moderate zones ({len(moderate)}, 3-9 zombies)")
        for z in moderate:
            lines.append(f"  {z['coords']}: {z['zombies']} zombies (day {z['scouted_day']})")
        lines.append("")

    if low:
        lines.append(f"### Low threat zones ({len(low)}, 1-2 zombies)")
        for z in low:
            lines.append(f"  {z['coords']}: {z['zombies']} zombies (day {z['scouted_day']})")
        lines.append("")

    if clear:
        lines.append(f"### Clear zones ({len(clear)})")
        coords_list = ", ".join(z["coords"] for z in clear)
        lines.append(f"  {coords_list}")

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
    tonight = f"{low}-{high}" if low is not None else "???"

    tomorrow_est = est.get("tomorrow", {})
    tomorrow = f"{tomorrow_est['min']}-{tomorrow_est['max']}" if tomorrow_est.get("min") is not None else "???"

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
            maxed = " (confirmed)" if e.get("maxed") else ""
            lines.append(f"  Day {day_str}: {e.get('min')}-{e.get('max')}{maxed}")

    return "\n".join(lines)
