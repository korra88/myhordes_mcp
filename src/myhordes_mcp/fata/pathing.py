"""CP-aware Dijkstra pathfinding for expeditions."""

import heapq

from ..utils.clock import data_updated
from .risk import (
    DANGER_LEVELS,
    DANGER_MAX_EST,
    _build_spread_map,
    _parse_coords,
    _spread_risk_for_clear,
    _staleness_tag,
    _zombie_max_estimate,
    fmt_items,
    km,
    platform_level,
    teleport_range,
)


MAX_PATH_AP = 40


# ---------------------------------------------------------------------------
# Walkability: how much entering a zone is worth avoiding, in moves of detour (0 = ideal,
# 1 = worth one extra move). Route cost = moves x _AP_COST + walkability of each zone
# entered. Internal only: answers show moves, AP and zombies, never these numbers.
# One weight per reason, so a new reason to avoid a zone is one more entry here.
# ---------------------------------------------------------------------------
WALK = {
    "at_limit": 1.0,          # zombies == CP: one more zombie traps the group
    "stale_zombies": 0.5,     # zombies under CP, counted on an older day (may have grown)
    "over_cp": 2.0,           # per zombie above CP, on top of the trap weight
    "trap": 50.0,             # zombies above CP seen today: blocked
    "trap_risk": 20.0,        # zombies above CP estimated (old count, spread, danger band)
    "unknown": 8.0,           # never explored
    "revisit": 1.0,           # already walked on this trip: its one dig of the day is used
    "scout_detection": 50.0,  # Scout with Camouflage Vest in a trap zone: x detection chance
}
# Zones known only by a danger band, without an estimate (0 / 1-2 / 3-5 / 6+ zombies).
_DANGER_WALK = {0: 0, 1: 1.5, 2: 4.0, 3: 6.0}
# Cost of one move on the walkability scale.
_AP_COST = 1.0


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

    if zone.get("danger_today"):
        # Today's danger estimate (Observation Platform radius): current, not exact.
        est = DANGER_MAX_EST.get(zone.get("danger", 0), DANGER_MAX_EST[3])
        tag = "TRAP_RISK" if est > group_cp else ("CLEAR" if est == 0 else "SAFE")
        return {"tag": tag, "zombies": est, "fresh": True, "age": 0}

    zm = zone.get("zombies", -1)

    # Explored but unscouted — only danger level available
    if zm < 0:
        danger = zone.get("danger", 0)
        est = DANGER_MAX_EST.get(danger)
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


def walkability(
    zone: dict | None,
    current_day: int | None = None,
    coords: tuple[int, int] | None = None,
    spread_map: dict | None = None,
    *,
    group_cp: int = 2,
    scout_mode: bool = False,
    revisit: bool = False,
) -> float:
    """Sum of the WALK weights that apply to entering this zone (0 = nothing to avoid)."""
    c = _classify_cell(zone, current_day, coords, spread_map, group_cp)
    tag, zombies = c["tag"], c["zombies"]
    w = WALK["revisit"] if revisit else 0.0
    if tag == "UNKNOWN":
        return w + WALK["unknown"]
    if zombies is None:
        return w + _DANGER_WALK.get(zone.get("danger", 0), WALK["unknown"])
    if tag in ("TRAPPED", "TRAP_RISK"):
        w += max(0, zombies - group_cp) * WALK["over_cp"]
        if scout_mode:
            day_pct, _ = _scout_detection(zombies, group_cp)
            return w + max(day_pct, 0.01) * WALK["scout_detection"] * (1.0 if tag == "TRAPPED" else 0.5)
        return w + WALK["trap" if tag == "TRAPPED" else "trap_risk"]
    if zombies > 0 and zombies >= group_cp:
        w += WALK["at_limit"]
    if zombies > 0 and not c["fresh"]:
        w += WALK["stale_zombies"]
    return w


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
    """Step cost for one zone.

    "safest"   — walkability (see WALK).
    "shortest" — 1 per move; trap zones are inf (the caller spends a flash item on them)
                 unless scout_mode, which pays the detection risk instead.
    """
    if mode != "shortest":
        return walkability(zone, current_day, coords, spread_map, group_cp=group_cp,
                           scout_mode=scout_mode)
    c = _classify_cell(zone, current_day, coords, spread_map, group_cp)
    if c["tag"] in ("TRAPPED", "TRAP_RISK"):
        if scout_mode:
            day_pct, _ = _scout_detection(c["zombies"] or 0, group_cp)
            return 1.0 + day_pct * WALK["scout_detection"] * 0.01
        return float("inf")
    return 1.0 + walkability(zone, current_day, coords, spread_map, group_cp=group_cp) * 0.001


def _zone_grid(data: dict, group_cp: int):
    """(zone_map, cell_class, spread_map, current_day) shared by the path searches.
    Scout radar readings fill zones missing from the map data."""
    current_day = data["meta"].get("day")
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
    cell_class = {c: _classify_cell(z, cd, c, spread_map, group_cp) for c, z in zone_map.items()}
    return zone_map, cell_class, spread_map, cd


def safest_route(data: dict, points: list[tuple[int, int]], group_cp: int = 2,
                 banned: frozenset = frozenset(), revisit: frozenset = frozenset(),
                 avoid_revisits: bool = False,
                 revisit_weight: float | None = None) -> list[tuple[int, int]] | None:
    """Safest path through `points` in order (Dijkstra on moves + walkability), as the list
    of zones walked, start included. `banned` zones are never entered; `revisit` zones (and,
    with avoid_revisits, the zones earlier legs walked) cost WALK["revisit"] to enter again,
    or `revisit_weight` (a tiny one = fewest zones walked again among the shortest routes).
    None if a leg has no path."""
    rw = WALK["revisit"] if revisit_weight is None else revisit_weight
    zone_map, _, spread_map, cd = _zone_grid(data, group_cp)
    route = [points[0]]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        seen = (revisit | (set(route) if avoid_revisits else set())) - {(0, 0), (x1, y1), (x2, y2)}
        margin = 3
        bx = (min(x1, x2) - margin, max(x1, x2) + margin)
        by = (min(y1, y2) - margin, max(y1, y2) + margin)
        heap = [(0.0, 0, x1, y1)]
        prev: dict[tuple[int, int], tuple[int, int] | None] = {(x1, y1): None}
        best: dict[tuple[int, int], tuple[float, int]] = {(x1, y1): (0.0, 0)}
        while heap:
            risk, ap, x, y = heapq.heappop(heap)
            if (x, y) == (x2, y2):
                break
            if best.get((x, y), (float("inf"), 0)) < (risk, ap) or ap >= MAX_PATH_AP:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n not in zone_map and not (bx[0] <= n[0] <= bx[1] and by[0] <= n[1] <= by[1]):
                    continue
                if n in banned:
                    continue
                step = (walkability(zone_map.get(n), cd, coords=n, spread_map=spread_map,
                                    group_cp=group_cp) + _AP_COST + (rw if n in seen else 0.0))
                cand = (risk + step, ap + 1)
                if cand < best.get(n, (float("inf"), 0)):
                    best[n] = cand
                    prev[n] = (x, y)
                    heapq.heappush(heap, (cand[0], cand[1], n[0], n[1]))
        if (x2, y2) not in prev:
            return None
        leg, cur = [], (x2, y2)
        while cur != (x1, y1):
            leg.append(cur)
            cur = prev[cur]
        route.extend(reversed(leg))
    return route


def _route_exposure(data: dict, route: list[tuple[int, int]], group_cp: int) -> float:
    """Summed safest-mode risk of the zones entered along `route`."""
    zone_map, _, spread_map, cd = _zone_grid(data, group_cp)
    return sum(_cell_risk(zone_map.get(c), cd, coords=c, spread_map=spread_map,
                          group_cp=group_cp, mode="safest") for c in route[1:])


def loop_return(data: dict, out: list[tuple[int, int]], group_cp: int = 2) -> dict | None:
    """The way back of a trip that walked `out` (start first, destination last).

    A zone can be dug once a day, so the way back avoids the outbound zones when that
    costs at most WALK["revisit"] moves per zone (they stay walkable). When the
    trip starts in town and the Observation Platform teleports (level 3+), the walk ends
    on the teleport zone that is cheapest to reach: walking costs |x|+|y| but the
    teleport works by km, so the best end is off row 0 / column 0 ([2|1] at level 4).

    The way back is the safest route (moves + walkability, as the way out). Returns
    {route, teleport_from, saved_ap, level, reused, retrace_ap} or None if no way back
    exists. `reused` = outbound zones it walks again.
    """
    start, dest = out[0], out[-1]
    level = platform_level(data) if start == (0, 0) else None
    reach = teleport_range(level)
    if reach and km(*dest) <= reach:
        return {"route": [dest], "teleport_from": dest, "saved_ap": abs(dest[0]) + abs(dest[1]),
                "level": level, "reused": [], "retrace_ap": len(out) - 1}
    if reach:
        ends = [(x, y) for x in range(-reach, reach + 1) for y in range(-reach, reach + 1)
                if (x, y) != (0, 0) and km(x, y) <= reach]
    else:
        ends = [start]
    walked = frozenset(out[1:-1]) - {start}
    best = None
    for end in ends:
        route = safest_route(data, [dest, end], group_cp, revisit=walked)
        if route is None:
            continue
        reused = [c for c in route[1:] if c in walked]
        key = (len(route) - 1 + WALK["revisit"] * len(reused), _route_exposure(data, route, group_cp),
               -(abs(end[0]) + abs(end[1])))
        if best is None or key < best[0]:
            best = (key, route, end, reused)
    if best is None:
        return None
    _, route, end, reused = best
    tele = end if reach else None
    return {"route": route, "teleport_from": tele,
            "saved_ap": abs(end[0]) + abs(end[1]) if tele else 0, "level": level,
            "reused": reused, "retrace_ap": len(out) - 1}


RISKY_TAGS = ("TRAPPED", "TRAP_RISK", "UNKNOWN")


def route_risks(data: dict, route: list[tuple[int, int]], points: list[tuple[int, int]],
                group_cp: int = 2, avoid_revisits: bool = False) -> list[dict]:
    """Stretches of `route` where the group may get blocked: zombies above its CP (seen
    today = TRAPPED, estimated from old data or spread = TRAP_RISK), or no data at all
    (UNKNOWN; consecutive unknown zones form one stretch).

    Each: zones, the moves that enter them, the zombie estimate, the kills needed to get
    control back (zombies - CP), and the extra AP of the safest route that avoids the
    stretch (None = no way around within the 40 AP cap per leg, or a waypoint)."""
    _, cell_class, _, _ = _zone_grid(data, group_cp)
    base = safest_route(data, points, group_cp, avoid_revisits=avoid_revisits)

    groups: list[dict] = []
    prev_move = None
    for move, cell in enumerate(route[1:], start=1):
        cc = cell_class.get(cell, {"tag": "UNKNOWN", "zombies": None, "age": -1})
        if cell == (0, 0) or cc["tag"] not in RISKY_TAGS:
            prev_move = None
            continue
        g = groups[-1] if groups else None
        if (g and cc["tag"] == "UNKNOWN" and g["tag"] == "UNKNOWN" and prev_move == move - 1):
            if cell not in g["zones"]:
                g["zones"].append(cell)
            g["moves"].append(move)
        else:
            z = cc.get("zombies")
            groups.append({"zones": [cell], "moves": [move], "tag": cc["tag"], "zombies": z,
                           "age": cc.get("age", -1),
                           "kills": max(0, z - group_cp) if z is not None else None})
        prev_move = move

    # The way back often crosses the same zones: one entry per set of zones.
    merged: list[dict] = []
    for g in groups:
        same = next((m for m in merged if set(m["zones"]) == set(g["zones"])), None)
        if same:
            same["moves"] += g["moves"]
        else:
            merged.append(g)

    for g in merged:
        g["zone"] = g["zones"][0]
        g["detour_ap"] = None
        g["waypoint"] = bool(set(g["zones"]) & set(points))
        if base is not None and not g["waypoint"]:
            alt = safest_route(data, points, group_cp, banned=frozenset(g["zones"]),
                               avoid_revisits=avoid_revisits)
            if alt is not None:
                g["detour_ap"] = len(alt) - len(base)
    return merged


def find_safe_path(
    data: dict,
    x1: int, y1: int,
    x2: int, y2: int,
    *,
    group_cp: int = 2,
    escape_items: int = 0,
    scout_mode: bool = False,
    step_table: bool = False,
    round_trip: bool = False,
    start_ap: int = 6,
    start_ep: int = 0,
    thirst_counter: int = 0,
    cp_breakdown: list[str] | None = None,
    show_items: bool = False,
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
        cp_breakdown: Lines explaining where group_cp came from (party CP log).
    """
    if data.get("error"):
        return f"Error: {data['error']}"

    meta = data["meta"]
    current_day = meta.get("day", "?")
    town = meta.get("town_name", "?")

    # -- Shared pre-computation (used by both Dijkstra runs) --
    zone_map, cell_class, spread_map, cd = _zone_grid(data, group_cp)
    ap_limit = MAX_PATH_AP

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
                    step_pri = risk + _AP_COST  # risk, each move weighed against it
                    step_sec = 1.0              # AP
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
        total_risk_val = pri - sec * _AP_COST if mode == "safest" else sec
        return (total_risk_val, total_ap, path, flashes, flash_cells)

    # -- Run both Dijkstra passes --
    safest = _run_dijkstra("safest")
    shortest = _run_dijkstra("shortest", flash_budget=escape_items) if escape_items > 0 or scout_mode else None

    # If shortest would be identical to safest, skip it
    if shortest is not None and safest is not None:
        if shortest[2] == safest[2]:
            shortest = None

    # -- Format output --
    lines = [f"## Pathfinding [{x1}|{y1}] → [{x2}|{y2}] — {town} Day {current_day}", data_updated(meta)]
    params = [f"Group CP: {group_cp}"]
    if scout_mode:
        params.append("Scout: Yes")
    if escape_items > 0:
        params.append(f"Flash items: {escape_items}")
    lines.append(" | ".join(params))
    for b in cp_breakdown or []:
        lines.append(f"  {b}")
    lines.append("")

    # Summary
    if safest is None and shortest is None:
        lines.append(f"No path found within {ap_limit} AP.")
        return "\n".join(lines)

    def _zombies_on(path: list[tuple[int, int]]) -> str:
        """'zombies on route: [3|0] 1, [4|2] ~5' — counts of today, else estimates (~)."""
        parts = []
        for p in path[1:]:
            cc = cell_class.get(p)
            if cc and cc.get("zombies"):
                parts.append(f"[{p[0]}|{p[1]}] {'' if cc.get('fresh') else '~'}{cc['zombies']}")
        unknown = sum(1 for p in path[1:] if p not in cell_class)
        out = "zombies on route: " + (", ".join(parts) if parts else "none")
        return out + (f"; {unknown} never-explored zones" if unknown else "")

    lines.append("### Summary")
    if safest is not None:
        s_risk, s_ap, s_path, _, _ = safest
        trap_count = sum(1 for p in s_path if cell_class.get(p, {}).get("tag") in ("TRAPPED", "TRAP_RISK"))
        lines.append(f"Safest: {s_ap} AP, {trap_count} trap zones; {_zombies_on(s_path)}")
    if shortest is not None:
        sh_risk, sh_ap, sh_path, sh_flashes, _ = shortest
        lines.append(f"Shortest: {sh_ap} AP, {sh_flashes} flash items used; {_zombies_on(sh_path)}")
    elif safest is not None:
        lines.append("Shortest path is identical to safest.")
    lines.append("")

    def _format_zom_str(z: dict | None, px: int, py: int) -> str:
        if z is None:
            return "unexplored"
        if z.get("danger_today"):
            danger = z.get("danger", 0)
            return f"~{DANGER_LEVELS.get(danger, 'unknown')} today" if danger else "clear today"
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
        else:
            tag_str = ""  # CLEAR / SAFE / UNKNOWN: the zombie text already says it

        stale = _staleness_tag(z.get("updated_day"), cd) if z and not z.get("danger_today") else ""

        ruin = z.get("ruin") if z else None
        ruin_str = ""
        if ruin:
            ruin_str = f" | {ruin['name']}" + (" [BLUEPRINT]" if ruin.get("blueprint_available") else "")
        if z and z.get("dried"):
            ruin_str += " | depleted"
        elif z and z.get("scav_level"):
            ruin_str += f" | {z['scav_level']}"
        items = z.get("items", []) if z and show_items else []
        items_str = f" | {fmt_items(items)}" if items else ""

        return f"  {i:>2}. {coord_str} — {zom_str}{tag_str}{ruin_str}{items_str}{stale}"

    def _render_back(back: dict | None, out: list[tuple[int, int]]) -> list[str]:
        if back is None:
            return ["### Way back", f"No way back found within {ap_limit} AP.", ""]
        walk = len(back["route"]) - 1
        tele = back["teleport_from"]
        if tele and not walk:
            how = (f"the Observation Platform (level {back['level']}) teleports you home from here "
                   f"if the gate is open: {back['saved_ap']} AP saved")
        elif tele:
            how = (f"walk {walk} AP to [{tele[0]}|{tele[1]}], then the Observation Platform "
                   f"(level {back['level']}) teleports you home if the gate is open: "
                   f"{back['saved_ap']} AP saved")
        else:
            how = f"walk {walk} AP" + (" (no platform teleport: level 3+ needed)"
                                       if out[0] == (0, 0) else "")
        out_ap = len(out) - 1
        head = [f"### Way back (loop: other zones than the way out, which are already dug)",
                f"Round trip {out_ap} + {walk} = {out_ap + walk} AP walked; {how}. "
                f"Retracing the way out would cost {back['retrace_ap']} AP."]
        if back["reused"]:
            head.append("Walks again (avoiding them costs more moves): "
                        + ", ".join(f"[{x}|{y}]" for x, y in back["reused"]) + " — already dug today.")
        rows = [_format_step(i, px, py) for i, (px, py) in enumerate(back["route"], start=out_ap)]
        return head + rows + [""]

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

    first = safest if safest is not None else shortest
    back = loop_return(data, list(first[2]), group_cp) if round_trip and first is not None else None
    if step_table and first is not None:
        route = list(first[2])
        if back is not None:
            route += back["route"][1:]
        lines.extend(format_step_table(route, start_ap, start_ep, thirst_counter))
        if back is not None and back["teleport_from"]:
            tx, ty = back["teleport_from"]
            lines.append(f"Then teleport home from [{tx}/{ty}]: not a move, no AP, no thirst.")
        lines.append("")

    if safest is not None:
        if shortest is None:
            _render_path("Path (safest = shortest)" if escape_items == 0 and not scout_mode else "Safest Path", safest)
        else:
            _render_path("Safest Path", safest)

    if shortest is not None:
        _render_path("Shortest Path", shortest)

    if round_trip and first is not None:
        lines.extend(_render_back(back, first[2]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step table: AP/EP and thirst counter along a route
# (knowledge/tactics/expedition-planning.md)
# ---------------------------------------------------------------------------

EP_MIN_KM = 3            # EP pays for moves leaving a zone 3+ km (risk.km) from town
THIRSTY_AT, DEHYDRATED_AT, DEATH_AT = 11, 22, 33


def _thirst(counter: int) -> str:
    if counter >= DEATH_AT:
        return "DEAD"
    if counter >= DEHYDRATED_AT:
        return "Dehydrated"
    if counter >= THIRSTY_AT:
        return "Thirsty"
    return "OK"


def step_rows(route: list[tuple[int, int]], start_ap: int = 6, start_ep: int = 0,
              thirst_counter: int = 0) -> list[dict]:
    """Walk a route cell by cell. No consumables are applied: when AP runs out
    the row says so, and AP goes negative to show the total still needed."""
    ap, ep, counter = start_ap, start_ep, thirst_counter
    rows = []
    for (x0, y0), (x1, y1) in zip(route, route[1:]):
        use_ep = ep > 0 and km(x0, y0) >= EP_MIN_KM
        if use_ep:
            ep -= 1
        else:
            ap -= 1
        counter += 1
        rows.append({
            "zone": (x1, y1), "km": km(x1, y1), "paid": "EP" if use_ep else "AP",
            "ap": ap, "ep": ep, "counter": counter, "thirst": _thirst(counter),
            "empty": not use_ep and ap < 0,
        })
    return rows


def format_step_table(route: list[tuple[int, int]], start_ap: int = 6, start_ep: int = 0,
                      thirst_counter: int = 0) -> list[str]:
    rows = step_rows(route, start_ap, start_ep, thirst_counter)
    if not rows:
        return []
    lines = [
        f"### Step table — start {start_ap} AP, {start_ep} EP, thirst counter {thirst_counter}; no consumables applied",
        "",
        "| Step | Zone | km | Paid | AP left | EP left | Counter | Thirst |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        ap = f"{r['ap']}" + (" ⚠" if r["empty"] else "")
        lines.append(f"| {i} | [{r['zone'][0]}/{r['zone'][1]}] | {r['km']} | {r['paid']} | {ap} | {r['ep']} "
                     f"| {r['counter']} | {r['thirst']} |")
    ap_steps = sum(r["paid"] == "AP" for r in rows)
    lines.append("")
    summary = [f"{len(rows)} moves: {ap_steps} paid with AP, {len(rows) - ap_steps} with EP"]
    first_empty = next((i for i, r in enumerate(rows, 1) if r["empty"]), None)
    if first_empty:
        short = -min(r["ap"] for r in rows)
        summary.append(f"AP runs out before step {first_empty}: {short} more AP needed "
                       "(consume food/water/drugs at exactly 0 AP to waste nothing)")
    for limit, label in ((THIRSTY_AT, "Thirsty"), (DEHYDRATED_AT, "Dehydrated — dies at midnight"),
                         (DEATH_AT, "death")):
        hit = next((i for i, r in enumerate(rows, 1) if r["counter"] >= limit), None)
        if hit:
            summary.append(f"counter reaches {limit} at step {hit} → {label} unless water resets it before")
    lines.append(" · ".join(summary) + ".")
    return lines
