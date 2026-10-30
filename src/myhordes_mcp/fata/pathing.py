"""CP-aware Dijkstra pathfinding for expeditions."""

import heapq
from dataclasses import dataclass, field

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
    "revisit": 1.0,           # nothing to dig (walked on this trip, or depleted) when digging:
                              # worth one move per zone still to dig (dig_weight)
    "dried": 0.01,            # depleted, nothing to dig: tiebreak among routes of equal AP
    "scout_detection": 50.0,  # Scout with Camouflage Vest in a trap zone: x detection chance
}
# Zones known only by a danger band, without an estimate (0 / 1-2 / 3-5 / 6+ zombies).
_DANGER_WALK = {0: 0, 1: 1.5, 2: 4.0, 3: 6.0}
# Cost of one move on the walkability scale.
_AP_COST = 1.0


def dig_weight(dig: bool) -> float:
    """Cost of entering a zone with nothing to dig (walked already, or depleted) on legs
    after the first. dig: the player digs on the way, a zone still to dig is worth a move;
    else only a tiebreak among the routes of fewest AP."""
    return WALK["revisit"] if dig else WALK["dried"]


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


@dataclass(frozen=True)
class ZoneGrid:
    """The zones of one `data` snapshot, shared by the path searches: build it once per
    call (`zone_grid(data)`), never cache it across calls. The zone class depends on the
    group CP, so `cell_class(cp)` is computed once per CP and kept on the grid."""
    zone_map: dict
    spread_map: dict
    day: int | None
    bounds: tuple | None
    _classes: dict = field(default_factory=dict, repr=False, compare=False)

    def cell_class(self, cp: int) -> dict:
        classes = self._classes.get(cp)
        if classes is None:
            classes = {c: _classify_cell(z, self.day, c, self.spread_map, cp)
                       for c, z in self.zone_map.items()}
            self._classes[cp] = classes
        return classes


def zone_grid(data: dict) -> ZoneGrid:
    """Scout radar readings fill zones missing from the map data."""
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
    return ZoneGrid(zone_map, _build_spread_map(zone_map, cd), cd, data["meta"].get("map_bounds"))


def _leg_search(grid: ZoneGrid, cp: int, a: tuple[int, int], b: tuple[int, int], f0: int, *, mode: str,
                budget: int, scout_mode: bool, banned: frozenset, seen: set,
                rw: float, dig_leg: bool = False) -> dict[int, tuple]:
    """One leg a -> b, starting with f0 flashes used. Returns {flashes used at b: (pri, sec,
    cells walked after a, flash cells)}, each the cheapest for that count (one entry when
    budget is 0). Cost is the (pri, sec) tuple; AP is capped at MAX_PATH_AP per leg.
    `seen` zones cost rw to enter; on a dig_leg so do depleted zones (no dig either way),
    elsewhere they cost WALK["dried"]."""
    zone_map, spread_map, cd, bounds = grid.zone_map, grid.spread_map, grid.day, grid.bounds
    margin = 3
    bx = (min(a[0], b[0]) - margin, max(a[0], b[0]) + margin)
    by = (min(a[1], b[1]) - margin, max(a[1], b[1]) + margin)
    start = (a[0], a[1], f0)
    heap = [(0.0, 0.0, 0, a[0], a[1], f0)]
    prev: dict[tuple, tuple | None] = {start: None}
    best: dict[tuple, tuple[float, float]] = {start: (0.0, 0.0)}
    found: dict[int, tuple] = {}
    while heap:
        pri, sec, ap, x, y, f = heapq.heappop(heap)
        key = (x, y, f)
        if best.get(key, (float("inf"), 0.0)) < (pri, sec):
            continue
        if (x, y) == b:
            found[f] = (pri, sec, key)
            if budget == 0 or len(found) == budget - f0 + 1:
                break
            continue
        if ap >= MAX_PATH_AP:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n not in zone_map and not (bx[0] <= n[0] <= bx[1] and by[0] <= n[1] <= by[1]):
                continue
            if bounds and not (bounds[0] <= n[0] <= bounds[1] and bounds[2] <= n[1] <= bounds[3]):
                continue   # off the map
            if n in banned:
                continue
            dried = (zone_map.get(n) or {}).get("dried")
            if n in seen or (dig_leg and dried):
                extra = rw
            else:
                extra = WALK["dried"] if dried else 0.0
            nf = f
            if mode == "shortest":
                # AP first, risk as tiebreak; a trap zone needs a flash (which clears it).
                if grid.cell_class(cp).get(n, {}).get("tag") in ("TRAPPED", "TRAP_RISK") and not scout_mode:
                    if f >= budget:
                        continue
                    nf, step = f + 1, (1.0, extra)
                else:
                    step = (1.0, _cell_risk(zone_map.get(n), cd, coords=n, spread_map=spread_map,
                                            group_cp=cp, scout_mode=scout_mode, mode="shortest") + extra)
            else:
                # Risk and moves weighed together (walkability + _AP_COST), AP as tiebreak.
                step = (walkability(zone_map.get(n), cd, coords=n, spread_map=spread_map,
                                    group_cp=cp, scout_mode=scout_mode) + _AP_COST + extra, 1.0)
            cand = (pri + step[0], sec + step[1])
            nkey = (n[0], n[1], nf)
            if cand < best.get(nkey, (float("inf"), 0.0)):
                best[nkey] = cand
                prev[nkey] = (key, nf > f)
                heapq.heappush(heap, (cand[0], cand[1], ap + 1, n[0], n[1], nf))
    out = {}
    for f, (pri, sec, key) in found.items():
        cells, flashed = [], []
        while prev[key] is not None:
            pkey, used = prev[key]
            cells.append((key[0], key[1]))
            if used:
                flashed.append((key[0], key[1]))
            key = pkey
        out[f] = (pri, sec, cells[::-1], flashed)
    return out


def search_route(data: dict, points: list[tuple[int, int]], *, cp: int | list[int] = 2,
                 mode: str = "safest", flash_budget: int = 0, scout_mode: bool = False,
                 banned: frozenset = frozenset(), revisit: frozenset = frozenset(),
                 avoid_revisits: bool = False, revisit_weight: float | None = None,
                 grid: ZoneGrid | None = None) -> dict | None:
    """The one route search: through `points` (start, waypoints..., end) in order.

    mode "safest":   cost = walkability + _AP_COST per move, AP as tiebreak.
    mode "shortest": AP first, risk as tiebreak; a trap zone needs a flash (budget shared
                     by all legs) unless scout_mode, which pays the detection risk instead.
    cp: group CP, an int or one value per leg. `banned` zones are never entered; `revisit`
    zones (and, with avoid_revisits, the zones earlier legs walked) cost WALK["revisit"] to
    enter again, or `revisit_weight` (a tiny one = fewest zones walked again among the
    shortest routes). On those legs (with `revisit`, or after the first with avoid_revisits)
    depleted zones cost the same: they give no dig either. Elsewhere they are a tiebreak.

    Returns {route (start included), ap, flashes, flash_cells, risk} or None if a leg has
    no path. risk = summed walkability of the zones entered (not counting revisit costs).
    grid: a ZoneGrid of `data` to reuse (built here when omitted).
    """
    legs = len(points) - 1
    cps = list(cp) if isinstance(cp, (list, tuple)) else [cp] * legs
    if len(cps) != legs:
        raise ValueError("cp needs one value per leg")
    rw = WALK["revisit"] if revisit_weight is None else revisit_weight
    grid = grid or zone_grid(data)
    # states: flashes used so far -> (pri, sec, route, flash cells, cells walked per leg)
    states = {0: (0.0, 0.0, [points[0]], [], [])}
    for i, (a, b) in enumerate(zip(points, points[1:])):
        nxt: dict[int, tuple] = {}
        for f0, (pri, sec, route, flashed, lens) in states.items():
            seen = (revisit | (set(route) if avoid_revisits else set())) - {(0, 0), a, b}
            res = _leg_search(grid, cps[i], a, b, f0, mode=mode, budget=flash_budget,
                              scout_mode=scout_mode, banned=banned, seen=seen, rw=rw,
                              dig_leg=bool(revisit) or (avoid_revisits and i > 0))
            for f, (lp, ls, cells, lf) in res.items():
                cand = (pri + lp, sec + ls, route + cells, flashed + lf, lens + [len(cells)])
                if f not in nxt or cand[:2] < nxt[f][:2]:
                    nxt[f] = cand
        if not nxt:
            return None
        states = nxt
    f, (_, _, route, flashed, lens) = min(states.items(), key=lambda kv: (kv[1][0], kv[1][1], kv[0]))
    # Exposure: walkability of each zone entered, with the CP of its leg.
    risk, k = 0.0, 1
    for c, n in zip(cps, lens):
        for cell in route[k:k + n]:
            risk += _cell_risk(grid.zone_map.get(cell), grid.day, coords=cell, spread_map=grid.spread_map,
                               group_cp=c, scout_mode=scout_mode, mode="safest")
        k += n
    return {"route": route, "ap": len(route) - 1, "flashes": f, "flash_cells": set(flashed),
            "risk": risk}


def safest_route(data: dict, points: list[tuple[int, int]], group_cp: int | list[int] = 2,
                 banned: frozenset = frozenset(), revisit: frozenset = frozenset(),
                 avoid_revisits: bool = False,
                 revisit_weight: float | None = None) -> list[tuple[int, int]] | None:
    """The safest route through `points` (search_route, mode "safest"): the zones walked,
    start included, or None if a leg has no path. group_cp: int, or one value per leg."""
    res = search_route(data, points, cp=group_cp, banned=banned, revisit=revisit,
                       avoid_revisits=avoid_revisits, revisit_weight=revisit_weight)
    return res["route"] if res else None


def loop_return(data: dict, out: list[tuple[int, int]], group_cp: int = 2,
                dig: bool = False) -> dict | None:
    """The way back of a trip that walked `out` (start first, destination last).

    A zone can be dug once a day, so the way back avoids the outbound zones and depleted
    zones (no dig either) when that costs at most dig_weight(dig) moves per zone (they stay
    walkable): with dig a zone still to dig is worth a move, without it only a tiebreak
    among the ways back of fewest AP. When the
    trip starts in town and the Observation Platform teleports (level 3+), the walk ends
    on the teleport zone that is cheapest to reach: walking costs |x|+|y| but the
    teleport works by km, so the best end is off row 0 / column 0 ([2|1] at level 4).

    The way back is the safest route (moves + walkability, as the way out). Returns
    {route, teleport_from, saved_ap, level, reused, retrace_ap} or None if no way back
    exists. `reused` = outbound zones it walks again; retrace_ap = AP to walk the way out
    backwards (to the first teleport zone on it).
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
    dried = {c for z in data.get("zones", []) if z.get("dried") and (c := _parse_coords(z))}
    last = len(out) - 1
    # Walking the way out backwards stops at the first zone the platform teleports from.
    retrace = last - next((j for j in range(last - 1, 0, -1) if reach and km(*out[j]) <= reach), 0)
    rw = dig_weight(dig)
    best = None
    grid = zone_grid(data)
    for end in ends:
        res = search_route(data, [dest, end], cp=group_cp, revisit=walked, revisit_weight=rw,
                           grid=grid)
        if res is None:
            continue
        route = res["route"]
        reused = [c for c in route[1:] if c in walked]
        no_dig = sum(1 for c in route[1:] if c in walked or c in dried)
        key = (len(route) - 1 + rw * no_dig, res["risk"],
               -(abs(end[0]) + abs(end[1])))
        if best is None or key < best[0]:
            best = (key, route, end, reused)
    if best is None:
        return None
    _, route, end, reused = best
    tele = end if reach else None
    return {"route": route, "teleport_from": tele,
            "saved_ap": abs(end[0]) + abs(end[1]) if tele else 0, "level": level,
            "reused": reused, "retrace_ap": retrace}


def reach_indices(route: list[tuple[int, int]], points: list[tuple[int, int]]) -> list[int | None]:
    """Index in `route` where each of `points` is reached, in order (None = not on the route,
    e.g. cut off by a teleport). points[0] is index 0."""
    out: list[int | None] = [0]
    pos = 0
    for p in points[1:]:
        nxt = next((i for i in range(pos + 1, len(route)) if route[i] == p), None)
        out.append(nxt)
        if nxt is not None:
            pos = nxt
    return out


RISKY_TAGS = ("TRAPPED", "TRAP_RISK", "UNKNOWN")


def route_risks(data: dict, route: list[tuple[int, int]], points: list[tuple[int, int]],
                group_cp: int | list[int] = 2, avoid_revisits: bool = False,
                revisit_weight: float | None = None) -> list[dict]:
    """Stretches of `route` where the group may get blocked: zombies above its CP (seen
    today = TRAPPED, estimated from old data or spread = TRAP_RISK), or no data at all
    (UNKNOWN; consecutive unknown zones form one stretch).

    Each: zones, the moves that enter them, the zombie estimate, the kills needed to get
    control back (zombies - CP), and the extra AP of the safest route that avoids the
    stretch (None = no way around within the 40 AP cap per leg, or a waypoint).
    group_cp: an int, or one value per leg of `points` (CP drops after a Guardian lowers
    the shield); each risk carries the "cp" of the leg that enters it. avoid_revisits /
    revisit_weight: as the route was searched (search_route)."""
    legs = len(points) - 1
    cps = list(group_cp) if isinstance(group_cp, (list, tuple)) else [group_cp] * legs
    grid = zone_grid(data)
    classes = {c: grid.cell_class(c) for c in set(cps)}
    reached = reach_indices(route, points)
    base = safest_route(data, points, cps, avoid_revisits=avoid_revisits, revisit_weight=revisit_weight)

    def leg_cp(move: int) -> int:
        """CP of the leg whose walk enters route[move]."""
        done = sum(1 for r in reached[1:] if r is not None and r < move)
        return cps[min(done, legs - 1)]

    groups: list[dict] = []
    prev_move = None
    for move, cell in enumerate(route[1:], start=1):
        cp = leg_cp(move)
        cc = classes[cp].get(cell, {"tag": "UNKNOWN", "zombies": None, "age": -1})
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
                           "age": cc.get("age", -1), "cp": cp,
                           "kills": max(0, z - cp) if z is not None else None})
        prev_move = move

    # The way back often crosses the same zones: one entry per set of zones.
    merged: list[dict] = []
    for g in groups:
        same = next((m for m in merged if set(m["zones"]) == set(g["zones"])), None)
        if same:
            same["moves"] += g["moves"]
            if g["cp"] < same["cp"]:  # entered again with fewer CP: that is the worse case
                same["cp"] = g["cp"]
                same["kills"] = max(0, same["zombies"] - g["cp"]) if same["zombies"] is not None else None
        else:
            merged.append(g)

    for g in merged:
        g["zone"] = g["zones"][0]
        g["detour_ap"] = None
        g["waypoint"] = bool(set(g["zones"]) & set(points))
        if base is not None and not g["waypoint"]:
            alt = safest_route(data, points, cps, banned=frozenset(g["zones"]),
                               avoid_revisits=avoid_revisits, revisit_weight=revisit_weight)
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
    waypoints: list[tuple[int, int]] | None = None,
    dig: bool = False,
) -> str:
    """Find paths between two map coordinates (through waypoints, if any) using CP-aware Dijkstra.

    Returns up to two paths:
      - Safest: minimises zombie exposure, avoids traps entirely.
      - Shortest: minimises AP, using escape items to pass through traps.
    If both paths are identical, only one is shown.

    Args:
        group_cp: Total Control Points of the party (default 2 = solo citizen).
        escape_items: Flash-grenade-equivalent items carried (each neutralises one trap).
        scout_mode: Scout with Camouflage Vest — traps become passable at detection risk.
        cp_breakdown: Lines explaining where group_cp came from (party CP log).
        waypoints: Zones to pass through, in order, between the two points.
        dig: The player digs on the way: later legs and the way back may take up to one
             more move per zone still to dig (dig_weight). Else fewest AP.
    """
    if data.get("error"):
        return f"Error: {data['error']}"

    meta = data["meta"]
    current_day = meta.get("day", "?")
    town = meta.get("town_name", "?")

    # -- Shared pre-computation (formatting) and the two searches --
    grid = zone_grid(data)
    zone_map, spread_map, cd = grid.zone_map, grid.spread_map, grid.day
    cell_class = grid.cell_class(group_cp)
    ap_limit = MAX_PATH_AP
    points = [(x1, y1)] + list(waypoints or []) + [(x2, y2)]
    wp_set = set(waypoints or [])
    # Several legs: zones an earlier leg walked cost a little to walk again (one dig a day).
    avoid = len(points) >= 3
    safest = search_route(data, points, cp=group_cp, scout_mode=scout_mode, avoid_revisits=avoid,
                          revisit_weight=dig_weight(dig), grid=grid)
    shortest = (search_route(data, points, cp=group_cp, mode="shortest", flash_budget=escape_items,
                             scout_mode=scout_mode, grid=grid)
                if escape_items > 0 or scout_mode else None)

    # If shortest would be identical to safest, skip it
    if shortest is not None and safest is not None:
        if shortest["route"] == safest["route"]:
            shortest = None

    # -- Format output --
    chain = " → ".join(f"[{x}|{y}]" for x, y in points)
    lines = [f"## Pathfinding {chain} — {town} Day {current_day}", data_updated(meta)]
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
        lines.append(f"No path found within {ap_limit} AP" + (" per leg." if waypoints else "."))
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
        s_ap, s_path = safest["ap"], safest["route"]
        trap_count = sum(1 for p in s_path if cell_class.get(p, {}).get("tag") in ("TRAPPED", "TRAP_RISK"))
        lines.append(f"Safest: {s_ap} AP, {trap_count} trap zones; {_zombies_on(s_path)}")
    if shortest is not None:
        sh_ap, sh_path, sh_flashes = shortest["ap"], shortest["route"], shortest["flashes"]
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
        ruin_str = " [WAYPOINT]" if (px, py) in wp_set else ""
        if ruin:
            ruin_str += f" | {ruin['name']}" + (" [BLUEPRINT]" if ruin.get("blueprint_available") else "")
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
        why = ("over zones still to dig when that is worth the AP" if dig
               else "fewest AP; at equal AP over zones still to dig")
        head = [f"### Way back ({why}: the way out is already dug, depleted zones have nothing)",
                f"Round trip {out_ap} + {walk} = {out_ap + walk} AP walked; {how}. "
                f"Retracing the way out would cost {back['retrace_ap']} AP."]
        if back["reused"]:
            head.append("Walks again (avoiding them costs more moves): "
                        + ", ".join(f"[{x}|{y}]" for x, y in back["reused"]) + " — already dug today.")
        rows = [_format_step(i, px, py) for i, (px, py) in enumerate(back["route"], start=out_ap)]
        return head + rows + [""]

    def _render_path(
        label: str,
        result: dict,
    ) -> None:
        path, flashes, flash_cells = result["route"], result["flashes"], result["flash_cells"]
        lines.append(f"### {label}")
        counter = [0]  # mutable counter for flash numbering
        for i, (px, py) in enumerate(path):
            lines.append(_format_step(i, px, py, flash_cells=flash_cells, total_flashes=flashes, flash_counter=counter))
        lines.append("")

    first = safest if safest is not None else shortest
    back = (loop_return(data, list(first["route"]), group_cp, dig=dig)
            if round_trip and first is not None else None)
    if step_table and first is not None:
        route = list(first["route"])
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
        lines.extend(_render_back(back, first["route"]))
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
