"""CP-aware Dijkstra pathfinding for expeditions."""

import heapq

from .risk import (
    DANGER_LEVELS,
    _build_spread_map,
    _parse_coords,
    _spread_risk_for_clear,
    _staleness_tag,
    _zombie_max_estimate,
    km,
)


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
                 banned: frozenset = frozenset()) -> list[tuple[int, int]] | None:
    """Safest path through `points` in order (Dijkstra on zombie risk, AP as tiebreak),
    as the list of zones walked, start included. `banned` zones are never entered.
    None if a leg has no path."""
    zone_map, _, spread_map, cd = _zone_grid(data, group_cp)
    route = [points[0]]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
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
                step = _cell_risk(zone_map.get(n), cd, coords=n, spread_map=spread_map,
                                  group_cp=group_cp, mode="safest")
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


RISKY_TAGS = ("TRAPPED", "TRAP_RISK", "UNKNOWN")


def route_risks(data: dict, route: list[tuple[int, int]], points: list[tuple[int, int]],
                group_cp: int = 2) -> list[dict]:
    """Stretches of `route` where the group may get blocked: zombies above its CP (seen
    today = TRAPPED, estimated from old data or spread = TRAP_RISK), or no data at all
    (UNKNOWN; consecutive unknown zones form one stretch).

    Each: zones, the moves that enter them, the zombie estimate, the kills needed to get
    control back (zombies - CP), and the extra AP of the safest route that avoids the
    stretch (None = no way around within the 40 AP cap per leg, or a waypoint)."""
    _, cell_class, _, _ = _zone_grid(data, group_cp)
    base = safest_route(data, points, group_cp)

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
            alt = safest_route(data, points, group_cp, banned=frozenset(g["zones"]))
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
    for b in cp_breakdown or []:
        lines.append(f"  {b}")
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
        ruin_str = ""
        if ruin:
            ruin_str = f" | {ruin['name']}" + (" [BLUEPRINT]" if ruin.get("blueprint_available") else "")
        if z and z.get("dried"):
            ruin_str += " | depleted"
        elif z and z.get("scav_level"):
            ruin_str += f" | {z['scav_level']}"
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

    first = safest if safest is not None else shortest
    if step_table and first is not None:
        route = list(first[2])
        if round_trip:
            route += list(reversed(route[:-1]))
        lines.extend(format_step_table(route, start_ap, start_ep, thirst_counter))
        lines.append("")

    if safest is not None:
        if shortest is None:
            _render_path("Path (safest = shortest)" if escape_items == 0 and not scout_mode else "Safest Path", safest)
        else:
            _render_path("Safest Path", safest)

    if shortest is not None:
        _render_path("Shortest Path", shortest)

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
