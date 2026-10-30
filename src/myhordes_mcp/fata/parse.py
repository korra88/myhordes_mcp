"""Parse the `var data = {...}` object embedded in the Fata Morgana spy page."""

import re

from .geo import fmt_xy
from .towndata import DEATH_TYPES, JOB_NAMES


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
            "coords": fmt_xy((rx, ry)),
            "inside_town": inside,
            "is_shaman": str(cid) == str(shaman_id),
            "last_update_day": c.get("lastUpdateDay"),
            "last_update_time": c.get("lastUpdateTime"),
        })
    citizens.sort(key=lambda c: c["name"].lower())
    return citizens


def _parse_deaths(js_data: dict, current_day: int | None) -> list[dict]:
    """Parse cadaver list. Each entry in cadavers[] is a dict of deaths for one day.

    Index i holds the deaths of game day i+1 (the attack at the end of that day
    for night deaths): citizens who died in the night 5→6 sit at index 4.
    "day" below is that game day.
    """
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
                "day": day_idx + 1,
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
            "coords": fmt_xy((rel_x, rel_y)),
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
                    "category": item_def.get("category", "Unknown"),
                    "heavy": bool(item_def.get("heavy")),
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

            # Zombie fields, confirmed against in-game values (town 8212 [5|-4],
            # day 1 end: z=6, zm=8, danger=3) and getdata's details.z == z:
            #   z      — current count at the last zone update (after kills)
            #   zm     — day's maximum, before kills; -1 (or missing) = unknown
            #   danger — 0 none, 1 = 1-2, 2 = 3-5, 3 = 6+
            # z defaults to 0 on zones nobody reported, so it only counts when
            # the zone has an update. z=0 with danger>0 is ambiguous (3488
            # archived cases): treat as unknown and fall back to danger.
            z = int(zone.get("z") or 0)
            zm = int(zone["zm"]) if zone.get("zm") not in (None, "") else -1
            danger = int(zone.get("danger", 0))
            observed = zone.get("updatedOnDay") is not None or zm >= 0
            if not observed or (z == 0 and danger > 0):
                z = -1

            entry = {
                "coords": fmt_xy((rx, ry)),
                "zombies": z,
                "zombies_max": zm if zm >= 0 else None,
                "danger": danger,
                "dried": int(zone.get("dried", 0)),
                "tag": zone.get("tag"),
                "items": zone_items,
                "ruin": ruin,
                "updated_by": zone.get("updatedBy"),
                "updated_day": zone.get("updatedOnDay"),
                "updated_on": zone.get("updatedOn"),
            }
            zones.append(entry)
    return zones
