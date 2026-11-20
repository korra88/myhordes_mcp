"""The game's rules: constants and pure functions, each checked against the game source.

One place to look when a rule changes or must be verified. Nothing here formats text for the bot,
reads Fata's JSON beyond the plain zone / building dicts a rule needs, or plans anything:
the planners and formatters (risk, camping, supplies, pathing, kills ...) import from here.
Sources: myhordes-docker (v5.0.6) `src/` and docs/source-map.md. Index by topic:
docs/mechanics-in-code.md.

Sections: zombies · camping · action points and thirst · other.
"""

import heapq
from dataclasses import dataclass
from typing import NamedTuple

from ..utils.fmt import plural
from .geo import NEIGHBOURS8, Bounds, Cell, fmt_xy, in_bounds, km, spread_steps


# ===========================================================================
# Zombies
# ===========================================================================

# Zone danger level → human-readable zombie estimate
# These come from in-game map exploration (automatic), not manual scouting.
DANGER_LEVELS = {
    0: "safe (0 zombies)",
    1: "low (1-2 zombies)",
    2: "moderate (3-5 zombies)",
    3: "dangerous (6+ zombies)",
}


# The danger levels (DANGER_LEVELS) as zombie counts (min, max). "6+" has no top, so it
# counts as 9: above any single citizen's 8 CP. An unknown level has no band: callers pick
# their own fallback (kills: the top band; pathing: none for a zone known only by its band).
DANGER_BAND = {0: (0, 0), 1: (1, 2), 2: (3, 5), 3: (6, 9)}
DANGER_TOP = DANGER_BAND[3]


def danger_band(danger, default=None):
    """(min, max) zombies of a danger level, `default` if the level is unknown."""
    return DANGER_BAND.get(danger, default)


def age_days(day, current) -> int | None:
    """Days between a reading's day and the current one (None if either is not a day)."""
    if isinstance(day, int) and isinstance(current, int):
        return current - day
    return None


def zone_is_today(zone: dict, day) -> bool:
    """Whether a zone's zombie reading is today's: seen today (Fata nvt=false: a visit,
    or the platform radius at night), or, in legacy data without that flag, counted
    on an update made today."""
    if "seen_today" in zone:
        return bool(zone["seen_today"])
    return zone.get("zombies", -1) >= 0 and zone.get("updated_day") == day


# Nightly growth (MapMaker::spreadCycleMH, day >= 2): a zone with zombies gets +1 (90%), +0 (5%)
# or +2 (5%); an empty zone next to a zone with more zombies gets 1-2 (or none); an empty zone
# without infected neighbours stays empty. The 8 surrounding zones are neighbours.
# Average +1.0 per night, worst case +2. One place for every estimate (zone_estimate: map, route risks, kills, camping).
GROWTH_AVG = 1.0
GROWTH_MAX = 2


def zombie_growth(zombies: int, nights: int) -> tuple[int, float, int]:
    """(min, avg, max) zombies in a zone counted with `zombies` (> 0) `nights` nights ago."""
    n = max(0, nights)
    return zombies, zombies + GROWTH_AVG * n, zombies + GROWTH_MAX * n


def zombie_sources(zone_map: dict[Cell, dict], current_day: int | None, *,
                   danger: bool = False) -> list[tuple[Cell, int | None, int]]:
    """Zones known to hold zombies: (cell, day of the reading, pessimistic count now).

    A zone counted with zombies (> 0) on an earlier day is grown to its worst case since
    (zombie_growth). danger=True also takes zones known only by a danger level > 0 (lower
    bound of the band, read today when seen today). The seeds of zombie_arrival, and the
    camping projection's list of nearby zombies."""
    out = []
    for cell, z in zone_map.items():
        if cell == (0, 0):
            continue
        zm = z.get("zombies", -1)
        last_day = z.get("updated_day") or z.get("scouted_day")
        if zm > 0:
            age = age_days(last_day, current_day)
            out.append((cell, last_day, zombie_growth(zm, age)[2] if age and age > 0 else zm))
        elif danger and z.get("danger", 0) > 0 and (zm < 0 or z.get("danger_today")):
            seen = current_day if zone_is_today(z, current_day) else last_day
            out.append((cell, seen, danger_band(z["danger"], DANGER_TOP)[0]))
    return out


class Arrival(NamedTuple):
    """The first day zombies can stand on a zone at hiding time (day), the zone they spread
    from (src) and the day of that zone's reading (seen)."""
    day: int
    src: Cell
    seen: int


def zombie_arrival(zone_map: dict[Cell, dict], current_day: int | None,
                   bounds: Bounds | None = None) -> dict[Cell, Arrival]:
    """For every zone of the grid the earliest day zombies can be on it, from the zones known to
    hold zombies (zombie_sources, danger bands included). Zones nobody can reach are absent.

    THE spread model (MapMaker::spreadCycleMH, NightlyHandler): one spread a night, after the
    camping check, only to the 8 zones around (NEIGHBOURS8). A zone holding zombies on day
    E(n) can pass them to a neighbour for day E(n) + 1, and a zone seen EMPTY on day t gets
    zombies on day t + 1 at the earliest: E(c) = max(t_c + 1, min over neighbours E(n) + 1),
    sources at their reading day. Solved as a shortest path (the max/+1 step keeps it
    monotone). Zones never visited relay the spread (no reading); the town never holds
    zombies. `bounds` limits the grid, else the known zones + 1. Compute it once per data
    snapshot and day; zone_estimate reads it."""
    empty: dict[Cell, int] = {}
    for c, z in zone_map.items():
        zm, danger = z.get("zombies", -1), z.get("danger", 0)
        seen = current_day if zone_is_today(z, current_day) else (z.get("updated_day") or z.get("scouted_day"))
        if seen is not None and (zm == 0 or (zm < 0 and not danger and zone_is_today(z, current_day))):
            empty[c] = seen
    if bounds is None:
        xs = [c[0] for c in zone_map] or [0]
        ys = [c[1] for c in zone_map] or [0]
        bounds = Bounds(min(xs) - 1, max(xs) + 1, min(ys) - 1, max(ys) + 1)
    heap = [(seen, src, src, seen) for src, seen, _n in zombie_sources(zone_map, current_day, danger=True)
            if seen is not None]
    heapq.heapify(heap)
    out: dict[Cell, Arrival] = {}
    while heap:
        e, c, src, seen = heapq.heappop(heap)
        if c in out:
            continue
        out[c] = Arrival(e, src, seen)
        for dx, dy in NEIGHBOURS8:
            n = (c[0] + dx, c[1] + dy)
            if n == (0, 0) or n in out or not in_bounds(bounds, n):
                continue
            heapq.heappush(heap, (max(e + 1, empty.get(n, e) + 1), n, src, seen))
    return out


def earliest_zombie_day(zone_map: dict[Cell, dict], cell: Cell, current_day: int | None,
                        bounds: Bounds | None = None) -> tuple[int, Cell, int] | None:
    """(day, source cell, source reading day) of `cell` in zombie_arrival, or None when no
    dated source reaches it. Without `bounds` the grid is the known zones + `cell` + 1."""
    if bounds is None:
        xs = [c[0] for c in zone_map] + [cell[0]]
        ys = [c[1] for c in zone_map] + [cell[1]]
        bounds = Bounds(min(xs) - 1, max(xs) + 1, min(ys) - 1, max(ys) + 1)
    return zombie_arrival(zone_map, current_day, bounds).get(cell)


@dataclass(frozen=True)
class Estimate:
    """Zombies a zone can hold: min / avg / max, where the numbers come from (`source`, a
    short text) and what they are (`kind`, for threat_text and the callers)."""
    min: float
    avg: float
    max: float
    source: str
    kind: str = "unknown"    # unknown | danger_today | count | grown | clear | early | spread | band |
                             # band_grown | exposed
    killed_today: int = 0    # exact count of a zone partly cleared today (zombies_max - zombies)
    count: int | None = None   # the zombies counted on the reading (kinds count, grown)
    danger: int = 0          # the danger level (kinds danger_today, band, band_grown)
    dist: int | None = None  # zones between the zone and the zombies it can come from (spread)


def _by_arrival(arr: Arrival | None, cell: Cell, target) -> tuple[int, float, int, int | None, str | None]:
    """(nights, avg, max, dist, early text) of a zone no zombie was seen on, from its arrival:
    from day arr.day it can hold 1-2 zombies, then +GROWTH_AVG (at most GROWTH_MAX) a night."""
    if arr is None or not isinstance(target, int):
        return 0, 0, 0, None, None
    dist = spread_steps(arr.src, cell)
    if arr.day > target:
        return 0, 0, 0, dist, f"can't have zombies yet: the nearest are {plural(dist, 'zone')} away"
    n = target - arr.day + 1
    return n, GROWTH_AVG * n, GROWTH_MAX * n, dist, None


def zone_estimate(zone: dict | None, cell: Cell, day, zmap: dict[Cell, dict] | None,
                  arrival: dict[Cell, Arrival], *, final: bool = False, at: int | None = None) -> Estimate:
    """THE zombie estimate of a zone, for the map, the zone details, the route searches, the kill
    runs and the camping projection. `arrival` is zombie_arrival(zmap, day, bounds); `zmap`
    (the zones by cell) is only read for a zone never visited (zone None). `day` is the day of
    the readings; `at` a later day to project to (camping), when no reading is today's.

    - counted today: exact (a zone partly cleared today: the count now, killed_today the rest;
      final: the data is a finished day, so the day's maximum before the kills);
    - counted > 0 on an earlier day: zombie_growth for the nights since;
    - counted 0 on an earlier day: only what zombie_arrival lets reach it: from its arrival day,
      1-2 zombies, then +GROWTH_AVG (at most GROWTH_MAX) a night; before that none;
    - only a danger band: its bounds, grown the same way if not today's;
    - never visited (zone None): see _unvisited (exposed: top danger band at least; enclosed by
      clear zones: the arrival rule)."""
    target = day if at is None else at
    arrival = {} if arrival is None else arrival
    if zone is None:
        return _unvisited(cell, day, zmap or {}, arrival, final, at, target)
    z, zmax = zone.get("zombies", -1), zone.get("zombies_max")
    upd, danger = zone.get("updated_day") or zone.get("scouted_day"), zone.get("danger", 0)
    projected = isinstance(day, int) and isinstance(target, int) and target > day
    nights = target - upd if isinstance(target, int) and upd is not None else 0
    if zone.get("danger_today") and not projected:
        lo, hi = danger_band(danger, DANGER_TOP)
        return Estimate(lo, (lo + hi) / 2, hi, f"danger {danger} today" if danger else "clear today",
                        "danger_today", danger=danger)
    if z >= 0 and not projected and zone_is_today(zone, day):
        if zmax and zmax > z:
            if final:
                return Estimate(zmax, zmax, zmax, f"day {day} (max, before kills)", "count", count=zmax)
            return Estimate(z, z, z, "today", "count", killed_today=zmax - z, count=z)
        return Estimate(z, z, z, "today", "count", count=z)
    if z >= 0:
        if upd is None or nights <= 0:
            return Estimate(z, z, z, f"day {upd}" if upd is not None else "counted", "count", count=z)
        src = f"day {upd} (+{plural(nights, 'night')})"
        if z > 0:
            return Estimate(*zombie_growth(z, nights), src, "grown", count=z)
        _n_, avg, hi, dist, early = _by_arrival(arrival.get(cell), cell, target)
        if early:
            return Estimate(0, 0, 0, early, "early", dist=dist)
        if hi:
            return Estimate(0, avg, hi, src, "spread", dist=dist)
        return Estimate(0, 0, 0, src, "clear")
    lo, hi = danger_band(danger, DANGER_TOP)
    if danger and nights > 0:
        return Estimate(lo, (lo + hi) / 2 + GROWTH_AVG * nights, hi + GROWTH_MAX * nights,
                        f"danger {danger} (+{plural(nights, 'night')})", "band_grown", danger=danger)
    return Estimate(lo, (lo + hi) / 2, hi, f"danger {danger}" if danger else "clear (danger 0)", "band",
                    danger=danger)


def _unvisited(cell: Cell, day, zmap: dict[Cell, dict], arrival: dict[Cell, Arrival], final: bool,
               at: int | None, target) -> Estimate:
    """A zone never visited (zone_estimate). Its own zombies are unknowable (the day-1 spawn
    may be there), so its neighbours decide: next to zombies, to another zone never visited or
    to the map edge (a neighbour missing from `zmap`), it is EXPOSED: max at least the top
    danger band, avg from the neighbours and the spread. Surrounded by visited zones without
    zombies: only what the spread (zombie_arrival) lets reach it."""
    _n_, avg, hi, dist, _early = _by_arrival(arrival.get(cell), cell, target)
    x, y = cell
    around = [(x + dx, y + dy) for dx, dy in NEIGHBOURS8 if (x + dx, y + dy) != (0, 0)]
    near = [zone_estimate(zmap[c], c, day, zmap, arrival, final=final, at=at) for c in around if c in zmap]
    infected = [e for e in near if e.avg > 0]
    open_sides = sum(1 for c in around if c not in zmap)
    if infected or open_sides:
        why = ", ".join(w for w in ((f"{plural(len(infected), 'neighbour')} with zombies" if infected else ""),
                                    (f"{plural(open_sides, 'side')} unexplored or map edge" if open_sides else "")) if w)
        return Estimate(0, max([avg] + ([sum(e.avg for e in infected) / len(infected)] if infected else [])),
                        max([hi, DANGER_TOP[1]] + [e.max for e in infected]),
                        f"never visited, exposed ({why})", "exposed", dist=dist)
    if hi:
        return Estimate(0, avg, hi, f"never visited, spread from {fmt_xy(arrival[cell].src)}", "spread", dist=dist)
    return Estimate(0, 0, 0, "never visited, surrounded by clear zones", "unknown")



# Global respawn (MapMaker::aboveMinNumberOfZombies, rules.yml modifiers): at night, after
# the attack and before zombies spread, if the whole map holds fewer than
# massive_respawn_threshold × day × massive_respawn_factor zombies (50 × 0.5 = 25 per day;
# small towns 30 × 0.5 = 15), the map regrows from its day-1 layout until it reaches that
# number, and the zombies already there are added on top. The day is the new one:
# NightlyHandler::advance_day increments it before stage3_zones.
RESPAWN_PER_DAY = {"small": 15}
DEFAULT_RESPAWN_PER_DAY = 25


def respawn_threshold(game_type: str | None, day: int) -> tuple[int, int]:
    """(zombies per day, threshold) of tonight's global respawn: per_day × (day + 1)."""
    per_day = RESPAWN_PER_DAY.get(game_type, DEFAULT_RESPAWN_PER_DAY)
    return per_day, per_day * (day + 1)


# ===========================================================================
# Beyond: control points, the Observation Platform, hero skills, EP
# ===========================================================================

EP_MIN_KM = 3      # moves leaving a zone 3+ km (km()) from town pay EP first (Zone::getDistance)


def ep_zone(x: int, y: int) -> bool:
    """Whether a move leaving [x|y] is paid with EP first (3+ km from town)."""
    return km(x, y) >= EP_MIN_KM


CP_PER_CITIZEN = 2  # base, used when the zone has no usable CP reading
MAX_CP_PER_CITIZEN = 8


OBSERVATION_PLATFORM = "Observation platform"


def platform_level(data: dict) -> int | None:
    """Observation Platform level, 0 if built without upgrades, None if not built."""
    for b in data.get("buildings", []):
        if b["name"].lower() == OBSERVATION_PLATFORM.lower() and b["built"]:
            return b.get("level") or 0
    return None


def teleport_range(level: int | None) -> int:
    """km (see km()) up to which the platform teleports citizens home
    (BeyondTeleportRadius: level 3 → 1 km, level 4 → 2 km)."""
    if level is None:
        return 0
    return 2 if level >= 4 else 1 if level >= 3 else 0


def platform_return_saving(level: int | None) -> int:
    """AP saved on the way home by the teleport (knowledge/tactics/game-mechanics.md,
    "Return to town"): the walk from the edge of the range, one move more than its km."""
    reach = teleport_range(level)
    return reach + 1 if reach else 0


# km reach of the hero skills (HeroSkillDataService; wiki Heroic Return / Rescue):
# Heroic Return, Reclusive R1–R4, self-teleport home, works with the gate closed;
# Rescue, University U1–U3, cast from town on a citizen outside.
HEROIC_RETURN_KM = {1: 9, 2: 11, 3: 13, 4: 15}
RESCUE_KM = {1: 1, 2: 2, 3: 3}


def skill_level_for(table: dict[int, int], dist: int) -> int | None:
    """The lowest skill level of `table` (HEROIC_RETURN_KM, RESCUE_KM) whose reach covers
    `dist` km, None when even the top level falls short."""
    return next((lvl for lvl, reach in table.items() if dist <= reach), None)



