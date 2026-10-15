"""Shared zone helpers: coordinates, data freshness, zombie spread and threat estimates."""

import re


# Zone danger level → human-readable zombie estimate
# These come from in-game map exploration (automatic), not manual scouting.
DANGER_LEVELS = {
    0: "safe (0 zombies)",
    1: "low (1-2 zombies)",
    2: "moderate (3-5 zombies)",
    3: "dangerous (6+ zombies)",
}


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


def _zone_status(zone: dict) -> str:
    """Scavenging and presence notes from /towndata, e.g. ', abundant, excavated day 7, CP 6 here'."""
    parts = []
    if not zone.get("dried") and zone.get("scav_level"):
        parts.append(zone["scav_level"])
    if zone.get("excavated"):
        parts.append(f"excavated day {zone['excavated_day']}" if zone.get("excavated_day") else "excavated")
    if zone.get("cp"):
        parts.append(f"CP {zone['cp']} here")
    return "".join(f", {p}" for p in parts)


def _parse_coords(zone: dict) -> tuple[int, int] | None:
    """Extract (rx, ry) integers from a zone's coords string '[rx|ry]'."""
    m = re.match(r"\[(-?\d+)\|(-?\d+)\]", zone.get("coords", ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


# ---------------------------------------------------------------------------
# Trapped citizens (zombies outnumber the citizens' control points)
# ---------------------------------------------------------------------------

CP_PER_CITIZEN = 2  # base, used when the zone has no CP reading (max 8/citizen)
OBSERVATION_PLATFORM = "Observation platform"


def platform_level(data: dict) -> int | None:
    """Observation Platform level, 0 if built without upgrades, None if not built."""
    for b in data.get("buildings", []):
        if b["name"].lower() == OBSERVATION_PLATFORM.lower() and b["built"]:
            return b.get("level") or 0
    return None


def teleport_range(level: int | None) -> int:
    """Chebyshev distance from which the platform teleports citizens home
    (Season 19: level 3 → 1 km, level 4 → 2 km; game-mechanics.md)."""
    if level is None:
        return 0
    return 2 if level >= 4 else 1 if level >= 3 else 0


def zone_cp(zone: dict, people: list[dict]) -> int | None:
    """The zone's CP reading (/towndata `human`, game-sourced) if it covers the
    citizens now standing there: none of them moved after the zone update."""
    cp, t = zone.get("cp"), zone.get("updated_on")
    if cp is None or not t:
        return None
    if any((c.get("last_update_time") or 0) > t for c in people):
        return None
    return cp


def trapped_citizens(data: dict) -> list[dict]:
    """Outside citizens on zones where reported zombies exceed the citizens' CP.

    With the zone's CP reading (same zone update as the zombie count) the check
    is exact. Without it, CP is assumed 2 per citizen: a lower bound, so a hit
    means 'possibly trapped'."""
    zones = {z["coords"]: z for z in data.get("zones", [])}
    outside = [c for c in data.get("citizens", []) if not c["inside_town"]]
    per_zone: dict[str, list] = {}
    for c in outside:
        per_zone.setdefault(c["coords"], []).append(c)
    reach = teleport_range(platform_level(data))
    gate_open = data.get("gate") == "open"
    hits = []
    for coords, people in per_zone.items():
        zone = zones.get(coords)
        if not zone or zone.get("zombies", -1) < 0:
            continue
        exact = zone_cp(zone, people)
        cp = exact if exact is not None else CP_PER_CITIZEN * len(people)
        if zone["zombies"] <= cp:
            continue
        xy = _parse_coords(zone)
        dist = max(abs(xy[0]), abs(xy[1])) if xy else None
        hits.append({
            "coords": coords,
            "citizens": [c["name"] for c in people],
            "zombies": zone["zombies"],
            "cp_min": cp,
            "cp_exact": exact is not None,
            "ruin": (zone.get("ruin") or {}).get("name"),
            "updated_on": zone.get("updated_on"),
            "updated_by": zone.get("updated_by"),
            "teleport": bool(reach and dist is not None and dist <= reach and gate_open),
        })
    return sorted(hits, key=lambda h: h["zombies"] - h["cp_min"], reverse=True)


def format_trapped(hits: list[dict], fmt_time) -> list[str]:
    """Warning lines for possibly trapped citizens. fmt_time(epoch) -> str."""
    if not hits:
        return []
    lines = [f"## ⚠ Trapped or possibly trapped ({len(hits)} zone{'s' if len(hits) > 1 else ''}) — "
             "zombies > CP (exact zone CP when Fata has it, else ≥2 per citizen)"]
    for h in hits:
        when = f"zone updated {fmt_time(h['updated_on'])}" if h["updated_on"] else "zone update time unknown"
        if h["updated_by"]:
            when += f" by {h['updated_by']}"
        extra = f", {h['ruin']}" if h["ruin"] else ""
        tp = " — platform teleport home available" if h["teleport"] else ""
        cp = f"{h['cp_min']} CP — TRAPPED" if h.get("cp_exact") else f"≥{h['cp_min']} CP"
        lines.append(f"  {', '.join(h['citizens'])} {h['coords']}{extra}: {h['zombies']} zombies vs {cp} ({when}){tp}")
    return lines
