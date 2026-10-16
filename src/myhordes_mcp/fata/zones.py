"""Map formatters: scout data, ruins/ground items, zones in a bounding box."""

from ..utils.clock import data_updated
from .risk import (
    DANGER_LEVELS,
    _build_spread_map,
    _parse_coords,
    _staleness_tag,
    _zone_freshness,
    _zone_status,
    _zone_threat,
)


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
        data_updated(meta),
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
    empty_count = len(zones) - len(ruin_zones) - len(item_zones)

    lines = [
        f"## Zone Map — {meta.get('town_name', '?')} Day {meta.get('day', '?')}",
        data_updated(meta),
        f"{len(zones)} zones explored, {len(ruin_zones)} ruins found"
        + (f" ({empty_count} zones with no ruin or ground items omitted)" if empty_count else ""),
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
            lines.append(f"  {z['coords']}: {r['name']}{bp}{dried}{digs}{threat}{_zone_status(z)}{fresh}")
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
            lines.append(f"  {z['coords']}{dried}{threat}{_zone_status(z)}{fresh}:")
            item_list = ", ".join(
                f"{i['name']}x{i['count']}" + (" [B]" if i["broken"] else "")
                for i in z["items"]
            )
            lines.append(f"    {item_list}")

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

        entry = [f"  {z['coords']} ({ap} AP){budget_flag}{dried}: {label}{threat}{_zone_status(z)}{fresh}"]
        if z.get("items"):
            item_list = ", ".join(
                f"{i['name']}x{i['count']}" + (" [B]" if i["broken"] else "")
                for i in z["items"]
            )
            entry.append(f"    Items: {item_list}")
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
            key = (threat, z.get("updated_day"), bool(z.get("dried")), z.get("zombies", -1) < 0)
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
            threat, day, dried, noscout = key
            return (threat == "", noscout, threat, -(day if day is not None else -1))
        for key in sorted(groups, key=_order):
            threat, day, dried, noscout = key
            desc = threat.lstrip(", ") or ("never scouted" if noscout else "clear")
            if dried:
                desc += ", dried"
            when = ""
            if day is not None:
                stale = " STALE" if (isinstance(current_day, int) and current_day - day >= 1) else ""
                when = f" (day {day}{stale})"
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
