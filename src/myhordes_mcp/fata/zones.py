"""Map formatters: scout data, ruins/ground items, zones in a bounding box."""

from ..utils.clock import data_updated
from .bank import summary_lines
from .risk import (
    DANGER_LEVELS,
    _build_spread_map,
    _parse_coords,
    _staleness_tag,
    _zone_freshness,
    _zone_status,
    _zone_threat,
    fmt_items,
    km,
    never_visited,
    respawn_check,
    zone_is_today,
    zone_reach,
)


def _by_day(zs: list[dict], fmt) -> list[str]:
    """'  Day 7: [15|-6] 10, [15|-7] 10' — one line per update day, newest first."""
    days: dict = {}
    for z in zs:
        days.setdefault(z.get("updated_day"), []).append(z)
    return [(f"  Day {d}: " if d is not None else "  No date: ") + ", ".join(fmt(z) for z in days[d])
            for d in sorted(days, key=lambda d: -(d if d is not None else -1))]


def format_scout(data: dict) -> str:
    """Zombie picture of the map: today's readings first, then older counts by day.

    Zones seen today through the Observation Platform radius carry today's danger
    estimate (their zombie count is a placeholder); others keep the count of their
    last update. Clear zones are counted, not listed: a route or an area is
    get_zone_details / find_expedition_path.
    """
    if data.get("error"):
        return f"Error: {data['error']}"

    meta = data["meta"]
    current_day = meta.get("day")
    zones = data.get("zones", [])
    map_coords = {m["coords"] for m in zones}
    scout_only = [z for z in data.get("scout", []) if z["coords"] not in map_coords]
    if not zones and not scout_only:
        return "No scout or map data available."

    today = [z for z in zones if zone_is_today(z, current_day)]
    today_danger = [z for z in today if (z["zombies"] < 0 or z.get("danger_today")) and z.get("danger")]
    today_count = [z for z in today if z["zombies"] > 0 and not z.get("danger_today")]
    today_clear = len(today) - len(today_danger) - len(today_count)
    older = [z for z in zones if not zone_is_today(z, current_day)]
    older_count = sorted((z for z in older if z["zombies"] > 0), key=lambda z: -z["zombies"])
    older_clear = sum(1 for z in older if z["zombies"] == 0)
    older_danger = [z for z in older if z["zombies"] < 0 and z.get("danger")]
    no_info = sum(1 for z in older if z["zombies"] < 0 and not z.get("danger"))
    never = never_visited(data)

    lines = [
        f"## Scout Map — {meta.get('town_name', '?')} Day {current_day}",
        data_updated(meta),
        f"{len(zones)} zones visited" + (f", {never} never" if never is not None else "")
        + f" · today: {len(today)} zones seen ({today_clear} clear) · older: {len(older_count)} with zombies, "
        f"{older_clear} clear, {no_info} no data",
        "",
    ]
    respawn = respawn_check(data)
    if respawn:
        lines += respawn + [""]

    if today_danger or today_count:
        lines.append("### Zombies seen today")
        for level in (3, 2, 1):
            zs = [z for z in today_danger if z["danger"] == level]
            if zs:
                lines.append(f"  ~{DANGER_LEVELS[level]}: " + ", ".join(z["coords"] for z in zs))
        if today_count:
            lines.append("  counted: " + ", ".join(f"{z['coords']} {z['zombies']}" for z in today_count))
        lines.append("")
    if older_count:
        n = sum(z["zombies"] for z in older_count)
        lines.append(f"### Older counts — {n} zombies in {len(older_count)} zones (by day of the count; "
                     "+~1.75/night since)")
        lines += _by_day(older_count, lambda z: f"{z['coords']} {z['zombies']}")
        lines.append("")
    if older_danger:
        lines.append(f"### Older danger estimates ({len(older_danger)})")
        lines += _by_day(older_danger, lambda z: f"{z['coords']} ~{z['danger']}")
        lines.append("")
    if scout_only:
        lines.append(f"### Scout estimates ({len(scout_only)} zones beyond explored map)")
        for z in sorted(scout_only, key=lambda z: -z["zombies"]):
            lines.append(f"  {z['coords']}: ~{z['zombies']} (d{z['scouted_day']})"
                         + _staleness_tag(z.get("scouted_day"), current_day))
    return "\n".join(lines).rstrip()


def _ruin_line(z: dict, current_day) -> str:
    r = z["ruin"]
    bp = " [BLUEPRINT]" if r.get("blueprint_available") else ""
    dried = " (dried)" if r.get("dried") else ""
    digs = f", {r['digs_remaining']} digs left" if r.get("digs_remaining") not in (None, "0", 0) else ""
    x, y = _parse_coords(z)
    return (f"  {z['coords']} {abs(x) + abs(y)} AP: {r['name']}{bp}{dried}{digs}"
            f"{_zone_threat(z)}{_zone_status(z)}{_zone_freshness(z, current_day)}")


def format_zones(data: dict, item: str = "") -> str:
    """Desert overview: what lies on the ground (grouped like the bank), the ruins,
    who is outside. With `item`: the zones where that item lies."""
    if data.get("error"):
        return f"Error: {data['error']}"
    zones = data.get("zones", [])
    meta = data["meta"]
    if not zones:
        return "No map data available."
    if item:
        return _format_item_search(data, item)

    current_day = meta.get("day")
    ruins = sorted((z for z in zones if z.get("ruin")), key=lambda z: (abs(_parse_coords(z)[0]) + abs(_parse_coords(z)[1])))
    item_zones = [z for z in zones if z.get("items")]
    merged: dict = {}
    for z in item_zones:
        for i in z["items"]:
            key = (i["name"], i["broken"])
            if key in merged:
                merged[key]["count"] += i["count"]
            else:
                merged[key] = dict(i)
    ground = sorted(merged.values(), key=lambda i: (i["name"].lower(), i["broken"]))
    outside = [c for c in data.get("citizens", []) if not c["inside_town"] and _parse_coords(c)]

    lines = [
        f"## Desert overview — {meta.get('town_name', '?')} Day {current_day}",
        data_updated(meta),
        f"{len(zones)} zones visited · {len(item_zones)} with ground items · {len(ruins)} ruins · "
        f"{len(outside)} citizens outside",
        "",
        f"### On the ground ({sum(i['count'] for i in ground)} items, as last seen in each zone)",
    ]
    lines += summary_lines(ground, rest_hint="get_zone_details(item='name') shows where any item lies")
    lines += ["Where an item lies: get_zone_details(item='<name>'); an area: x1/y1/x2/y2.", ""]

    if ruins:
        lines.append(f"### Ruins ({len(ruins)}, nearest first)")
        lines += [_ruin_line(z, current_day) for z in ruins]
        lines.append("")
    if outside:
        by_zone: dict = {}
        for c in outside:
            by_zone.setdefault(c["coords"], []).append(c["name"])
        lines.append(f"### Citizens outside ({len(outside)}, farthest first)")
        for coords in sorted(by_zone, key=lambda k: -sum(map(abs, _parse_coords({"coords": k})))):
            x, y = _parse_coords({"coords": coords})
            lines.append(f"  {coords} {abs(x) + abs(y)} AP: {', '.join(by_zone[coords])}")
    return "\n".join(lines).rstrip()


ITEM_ZONES_SHOWN = 25


def _format_item_search(data: dict, item: str) -> str:
    meta = data["meta"]
    q = item.strip().lower()
    current_day = meta.get("day")
    hits = []
    for z in data["zones"]:
        found = [i for i in z.get("items", []) if q in i["name"].lower()]
        if found:
            x, y = _parse_coords(z)
            hits.append((abs(x) + abs(y), z, found))
    hits.sort(key=lambda h: (h[0], h[1]["coords"]))
    total = sum(i["count"] for _, _, f in hits for i in f)
    lines = [f"## '{item}' on the ground — {meta.get('town_name', '?')} Day {current_day}",
             data_updated(meta)]
    if not hits:
        return "\n".join(lines + [f"No zone holds an item matching '{item}' (as last seen)."])
    lines.append(f"{total} in {len(hits)} zones, nearest first (as last seen in each zone):")
    for ap, z, found in hits[:ITEM_ZONES_SHOWN]:
        lines.append(f"  {z['coords']} {ap} AP: {fmt_items(found)}{_zone_freshness(z, current_day)}")
    if len(hits) > ITEM_ZONES_SHOWN:
        far = hits[ITEM_ZONES_SHOWN:]
        lines.append(f"  +{sum(i['count'] for _, _, f in far for i in f)} more in {len(far)} zones at "
                     f"{far[0][0]}–{far[-1][0]} AP (a box with x1/y1/x2/y2 lists them)")
    return "\n".join(lines)


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
    lines = [" | ".join(header_parts), data_updated(meta), ""]
    if (x1, y1) == (x2, y2) != (0, 0):
        lines += ["### From town"] + [f"  {line}" for line in zone_reach(data, x1, y1)] + [""]

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
            label = f" {ruin['name']}{bp}{digs}"
        else:
            label = ""

        entry = [f"  {z['coords']} {ap} AP, {km(rx, ry)} km{budget_flag}{dried}:{label}"
                 f"{threat}{_zone_status(z)}{fresh}".replace(":,", ":")]
        if z.get("items"):
            entry.append(f"    {fmt_items(z['items'])}")
        return entry

    def _split_empty(entries: list) -> tuple[list, dict]:
        """Partition entries into (detailed, empty_groups).

        Zones with a ruin or ground items keep a full line each. Zones with
        nothing on the ground are grouped by (threat, freshness day, dried)
        so identical zones share one line — no information is dropped except
        the name of the player who scouted them.
        """
        detailed, groups = [], {}
        for ap, z, rx, ry in entries:
            if z.get("ruin") or z.get("items"):
                detailed.append((ap, z, rx, ry))
                continue
            threat = _zone_threat(z, current_day, spread_map=spread_map, coords=(rx, ry))
            key = (threat, z.get("updated_day"), bool(z.get("dried")), z.get("zombies", -1) < 0,
                   bool(z.get("danger_today")))
            groups.setdefault(key, []).append((ap, z))
        return detailed, groups

    def _compact_lines(groups: dict) -> list[str]:
        """One line per (threat, day, dried) group of empty zones."""
        if not groups:
            return []
        total = sum(len(v) for v in groups.values())
        out = [f"  Nothing on ground ({total} zones, grouped by threat/freshness):"]
        # Threatened groups first (most dangerous info up top), then clear/no-data
        def _order(key):
            threat, day, dried, noscout, _ = key
            return (threat == "", noscout, threat, -(day if day is not None else -1))
        for key in sorted(groups, key=_order):
            threat, day, dried, noscout, today = key
            desc = threat.lstrip(", ") or ("never scouted" if noscout else "clear")
            if dried:
                desc += ", dried"
            when = ""
            if day is not None and today:
                when = f" (read d{day}; zombies today)"
            elif day is not None:
                stale = " STALE" if (isinstance(current_day, int) and current_day - day >= 1) else ""
                when = f" (d{day}{stale})"
            cells = sorted(groups[key], key=lambda t: (t[0], t[1]["coords"]))
            coords = ", ".join(f"{z['coords']} {ap}AP" for ap, z in cells)
            out.append(f"    {desc}{when}: {coords}")
        return out

    if in_budget:
        detailed, empty_groups = _split_empty(in_budget)
        lines.append(f"### Zones in range ({len(in_budget)})")
        for ap, z, rx, ry in detailed:
            lines.extend(_render_zone(ap, z, rx, ry))
        lines.extend(_compact_lines(empty_groups))
        lines.append("")

    if over_budget:
        detailed, empty_groups = _split_empty(over_budget)
        lines.append(f"### Beyond AP budget ({len(over_budget)})")
        for ap, z, rx, ry in detailed:
            lines.extend(_render_zone(ap, z, rx, ry, budget_exceeded=True))
        lines.extend(_compact_lines(empty_groups))

    return "\n".join(lines)
