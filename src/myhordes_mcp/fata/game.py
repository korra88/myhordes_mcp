"""The game's rules: constants and pure functions, each checked against the game source.

One place to look when a rule changes or must be verified. Nothing here formats text for the bot,
reads Fata's JSON beyond the plain zone / building dicts a rule needs, or plans anything:
the planners and formatters (risk, camping, supplies, pathing, kills ...) import from here.
Sources: myhordes-docker (v5.0.6) `src/` and docs/source-map.md. Index by topic:
docs/mechanics-in-code.md.

Sections: zombies · Beyond (CP, Observation Platform, hero skills, EP) · camping · action points,
EP and thirst · other (kill weapons, scout detection, wind, heavy items, town size).
"""

import heapq
import math
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


# ===========================================================================
# Camping (CitizenHandler::getCampingOdds / getCampingValues / getZoneBuildingBonus,
# docs/camping-plan.md 1.2; the odds are frozen the moment the citizen hides)
# ===========================================================================

# Previous campings (index = camping nights survived, capped at the end of the whole table).
_TAIL = [-50, -100, -200, -400, -1000, -2000, -5000]
PREVIOUS = {
    (False, False): [80, 60, 35, 15, 0] + _TAIL,
    (False, True): [80, 70, 60, 40, 30, 20, 0] + _TAIL,
    (True, False): [50, 30, 20, 10, 0] + _TAIL,        # Pandemonium town
    (True, True): [50, 45, 40, 30, 20, 10, 0] + _TAIL,
}
# Nights the Reclusive pro table lasts: Reclusive 1 (super_recluse0) 6, higher levels 8
# (HeroSkillDataService ProCamperUsageLimit; one level per skill group). Matches Fata's planner.
PRO_CAMPER_LIMIT = {"reclusive1": 6, "reclusive2": 8, "reclusive3": 8, "reclusive4": 8}
PANDA_TOWN_BONUS = -30        # rules.yml `panda: modifiers.camping.default_bonus`
CROWD = [0, 0, -10, -30, -50, -70]
DISTANCE = [-100, -75, -50, -25, -10, 0, 0, 0, 0, 0, 0, 0, 5, 7, 10, 15, 20]
LIGHTHOUSE_UID = "small_lighthouse_#00"
SKILLS = ("none", "procamp", "reclusive1", "reclusive2", "reclusive3", "reclusive4")
HIDING_FROM_HOUR = 19   # camping odds get the night bonus from 19:00 (TownConf::isNightTime)
LIGHTHOUSE_BONUS = 25   # a built lighthouse (LIGHTHOUSE_UID)
NIGHT_BONUS = 10        # hiding at night
DEVASTATED_PENALTY = -50
NO_RUIN_TERM = -25      # no ruin on the zone, or its camping slots are taken
BURIED_RUIN_TERM = 15   # ruin still buried (digs left): a fixed bonus instead of the ruin's own
ZOMBIE_PENALTY, ZOMBIE_PENALTY_VEST = -7, -3   # per zombie on the zone (Camouflage Vest)

TOMB_BONUS, CAMP_ITEM_BONUS = 8, 5   # grave (its digger only), each Groundsheet / Festering Flesh carried
IMPROVE_LEVEL, INSTALL_LEVEL, MAX_LEVEL_TO_ACT = 5, 9, 50   # actions allowed while level < 50
NIGHTLY_DROP = 15       # the zone's camp level drops by this much every night (floor 0)

# Items a camper can install on the campsite ('improve' action, ActionDataService).
INSTALLABLE = {"Old Door", "Sheet Metal", "Trestle", "Mattress", "Solid Wooden Board", "Sheet of Plywood",
               "Järpen Table"}
ITEM_UIDS = {"sheet": "Groundsheet", "smelly_meat": "Festering Flesh"}   # camp items (+CAMP_ITEM_BONUS each)
STEAK_UID = "meat"                                                       # boosts a Tamer's dog (+5, no AP)


def is_pro_camper(skill: str, nights: int) -> bool:
    """procamp (legacy skill, no limit) or any Reclusive level (limit 6 nights, 8 from level 2)."""
    if skill == "procamp":
        return True
    return nights < PRO_CAMPER_LIMIT.get(skill, 0)


def odds_cap(job: str, skill: str) -> float:
    """Survivalist 1.0; Reclusive top level (reclusive4) 0.99; everyone else 0.9."""
    cap = 0.9
    if skill == "reclusive4":
        cap = max(cap, 0.99)
    if job == "Survivalist":
        cap = max(cap, 1.0)
    return cap


def ruin_term(ruin: dict | None, hidden_before: int) -> int:
    """No ruin or ruin full: NO_RUIN_TERM. Slot free: ruin bonus, buried ruin BURIED_RUIN_TERM."""
    if not ruin:
        return NO_RUIN_TERM
    slots = ruin.get("camp_slots")
    if slots is not None and slots >= 0 and hidden_before >= slots:
        return NO_RUIN_TERM
    if int(ruin.get("digs_remaining") or 0) > 0:
        return BURIED_RUIN_TERM
    return int(ruin.get("camp_boost") or 0)


def camping_terms(*, nights: int = 0, skill: str = "none", panda: bool = False, tomb: bool = False,
                  level: int = 0, ruin: dict | None = None, hidden_before: int = 0,
                  lighthouse: bool = False, camp_items: int = 0, zombies: int = 0,
                  vest: bool = False, night: bool = True, distance: int = 0,
                  devastated: bool = False) -> dict[str, int]:
    """The twelve terms of the game's odds (percentage points)."""
    table = PREVIOUS[(panda, is_pro_camper(skill, nights))]
    return {
        "previous": table[min(max(nights, 0), len(table) - 1)],
        "tomb": TOMB_BONUS if tomb else 0,
        "town": PANDA_TOWN_BONUS if panda else 0,
        "zone": level,
        "zoneBuilding": ruin_term(ruin, hidden_before),
        "lighthouse": LIGHTHOUSE_BONUS if lighthouse else 0,
        "campitems": CAMP_ITEM_BONUS * camp_items,
        "zombies": zombies * (ZOMBIE_PENALTY_VEST if vest else ZOMBIE_PENALTY),
        "campers": CROWD[min(len(CROWD) - 1, max(0, hidden_before))],
        "night": NIGHT_BONUS if night else 0,
        "distance": DISTANCE[min(len(DISTANCE) - 1, max(0, distance))],
        "devastated": DEVASTATED_PENALTY if devastated else 0,
    }


def camping_odds(terms: dict[str, int], cap: float) -> float:
    """The odds: the terms summed (percentage points), clamped to [0, cap]."""
    return max(0.0, min(sum(terms.values()) / 100.0, cap))


def is_panda(meta: dict) -> bool:
    """Pandemonium: the game type name is 'panda'; Fata's `hard` flag (meta.hardcore) is the
    same thing (the game's own XML API exports `hard` = type panda)."""
    return meta.get("game_type") == "panda" or bool(meta.get("hardcore"))


def lighthouse_built(data: dict) -> bool:
    return any(b.get("built") and b.get("uid") == LIGHTHOUSE_UID for b in data.get("buildings", []))


def level_after_nights(level: int, nights: int) -> int:
    """The zone's camp level after `nights` nights (NIGHTLY_DROP each, never below 0)."""
    return max(0, level - NIGHTLY_DROP * nights)


def level_ok(level0: int, n5: int, n9: int) -> bool:
    """Whether n5 improves (+IMPROVE_LEVEL) and n9 installs (+INSTALL_LEVEL) can all start below
    MAX_LEVEL_TO_ACT, from `level0` (the biggest step last: the last action may cross it)."""
    if not (n5 or n9):
        return True
    return level0 + IMPROVE_LEVEL * n5 + INSTALL_LEVEL * n9 - (INSTALL_LEVEL if n9 else IMPROVE_LEVEL) < MAX_LEVEL_TO_ACT


def improves_left(level_after: int) -> int:
    """Improves that can still be done on a night ending at `level_after`: each must start below 50."""
    return max(0, -(-(MAX_LEVEL_TO_ACT - level_after) // IMPROVE_LEVEL))


def position_terms(n: int, ruin: dict | None, hidden_before: int) -> list[int]:
    """Crowd + ruin-room points for the camper hiding at each position (0 = first of the group)."""
    return [CROWD[min(len(CROWD) - 1, hidden_before + p)] + ruin_term(ruin, hidden_before + p)
            for p in range(n)]


# ===========================================================================
# Action points, EP and thirst (ActionDataService, ActionEffectProvider, ActionRequirementProvider,
# BeyondController, CitizenHandler, ProcessStatusEffect, HeroSkillDataService; myhordes-docker v5.0.6;
# player-facing version: knowledge/tactics/expedition-planning.md)
#
# - A move costs 1 point. Leaving a zone at 3+ km (game.ep_zone) pays EP first, else AP only.
# - Thirst counter: +1 per move (AP or EP). Above 10 the thirst level goes up and the counter
#   restarts: thirsty at move 11, dehydrated at 22, dead at 33. Only water (and midnight) resets it
#   (not food, not Hydratone, not entering town).
# - Water: not thirsty → only if not drunk today and AP < max; AP to max. Thirsty → clears
#   thirst; AP to max only if not drunk today. Dehydrated → becomes thirsty, no AP, so a
#   second ration is needed. A second drink while not thirsty is refused by the game.
# - Food: once a day, only with AP < max. 6 AP food → max AP, 7 AP food → max + 1.
# - Anabolic Steroids → max AP, Twinoid → max + 2. Both are drugs: a second drug the same
#   day makes the citizen an addict, so the planner uses at most one.
# - Alcohol → max AP; not when already drunk or hungover (hungover the next day).
# - Bloody Hot Coffee: +4 AP up to max, +1 EP up to max EP, no daily limit.
# - Second Wind (hero skill, HeroSkillDataService 'super_enduring_N' + effect 'just_ap_sw'):
#   adds AP up to max (never above) and EP even above max; skill levels 0-3 (what players call
#   Enduring 1-4, Master = 4) give +3/+1, +3/+3, +4/+4, +4/+6. It is the day's one heroic action (status tg_hero, cleared at night),
#   shared with Heroic Return and the other hero actions. Not an item: no slot.
# - AP items raise AP to a level, they never add: AP left when using one is wasted.
# - They also refill EP up to the shoes (1) + bike (2) part, never the scout's 2;
#   Twinoid one more. Max AP is 6, 5 when wounded.
# - Observation Platform level 3/4: teleport home from 1/2 km (gate open), no move.
# - Labyrinth: entering town from [0|0] costs 1 AP.
# ===========================================================================

MAX_AP, WOUNDED_MAX_AP = 6, 5   # AP after the night, and the max that water / food / drugs restore
SCOUT_EP, SHOES_EP, BIKE_EP = 2, 1, 2   # EP of the scout's own pool, the shoes part, the bike part
THIRST_STEP = 10      # the counter goes up a level when it passes this: thirsty at move 11, dehydrated at 22
THIRST_DEAD = 3       # the thirst level that kills
LABYRINTH_ENTRY_AP = 1   # entering town from [0|0] through the Labyrinth
SECOND_WIND = {0: (3, 1), 1: (3, 3), 2: (4, 4), 3: (4, 6)}  # skill level 0-3 (Enduring 1-4) → (AP, EP)


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    kind: str   # water | food | drug | alcohol | coffee | hero
    level: int  # AP level relative to max (food/drug/alcohol), or AP added (coffee)


ITEMS = {
    "water": Item("water", "Water Ration", "water", 0),
    "food7": Item("food7", "7 AP food", "food", 1),
    "food6": Item("food6", "6 AP food", "food", 0),
    "alcohol": Item("alcohol", "alcohol", "alcohol", 0),
    "steroid": Item("steroid", "Anabolic Steroids", "drug", 0),
    "twinoid": Item("twinoid", "Twinoid 500mg", "drug", 2),
    "coffee": Item("coffee", "Bloody Hot Coffee", "coffee", 4),
    "secondwind": Item("secondwind", "Second Wind (hero action)", "hero", 0),
}


def ap_max(wounded: bool) -> int:
    """The AP that water, food and drugs restore to."""
    return WOUNDED_MAX_AP if wounded else MAX_AP


def ep_extension(shoes: bool, bike: bool) -> int:
    """EP the shoes and bike parts give; the items that refill EP only refill up to this (never the scout's)."""
    return (BIKE_EP if bike else 0) + (SHOES_EP if shoes else 0)


def ep_max(scout: bool, shoes: bool, bike: bool) -> int:
    return (SCOUT_EP if scout else 0) + ep_extension(shoes, bike)


def refill_ep(ep: int, ext: int, plus: int = 0) -> int:
    """EP after an AP item: refilled up to the shoes + bike part (`ext`), Twinoid one more (`plus`)."""
    return max(ep, ext + plus) if ext > 0 else ep


def pays_ep(ep: int, x: int, y: int) -> bool:
    """A move leaving [x|y] is paid with EP: EP left and the zone 3+ km from town."""
    return ep > 0 and ep_zone(x, y)


def count_move(cnt: int, th: int) -> tuple[int, int, bool]:
    """(counter, thirst level, became dehydrated) after one more move (AP or EP) without water."""
    cnt += 1
    if cnt > THIRST_STEP:
        th, cnt = th + 1, 0
        return cnt, th, th == 2
    return cnt, th, False


def thirst_level(counter: int) -> int:
    """Thirst level after `counter` moves without water (the counter never resets in a step table):
    a level every THIRST_STEP + 1 moves; THIRST_DEAD is death."""
    return counter // (THIRST_STEP + 1)


def thirst_counter_at(level: int) -> int:
    """The counter at which `thirst_level` reaches `level`."""
    return level * (THIRST_STEP + 1)


def drink_water(th: int, drank: bool, ap: int, ep: int, max_ap: int, ext: int):
    """A Water Ration: (ap, ep, thirst, drank, AP wasted), or None when the game refuses it. The
    thirst counter restarts at 0. Not thirsty: only if not drunk today and AP < max, AP to max.
    Thirsty: clears the thirst, AP to max only if not drunk today. Dehydrated: becomes thirsty,
    no AP (a second ration is needed)."""
    waste = 0
    if th == 0:
        if drank or ap >= max_ap:
            return None
        waste = min(ap, max_ap)
        ap, ep, drank = max(ap, max_ap), refill_ep(ep, ext), True
    elif th == 1:
        if not drank:
            waste = min(ap, max_ap)
            ap, ep, drank = max(ap, max_ap), refill_ep(ep, ext), True
        th = 0
    else:
        th = 1
    return ap, ep, th, drank, waste


def eat_food(ate: bool, ap: int, ep: int, max_ap: int, ext: int, level: int):
    """Food (6 AP: level 0, 7 AP: level 1): (ap, ep), or None. Once a day, only at 0 AP."""
    if ate or ap >= max_ap or ap > 0:
        return None
    return max(ap, max_ap + level), refill_ep(ep, ext)


def take_drug(drugged: bool, key: str, ap: int, ep: int, max_ap: int, ext: int, level: int):
    """A drug (Anabolic Steroids level 0, Twinoid 2): (ap, ep), or None. One a day (a second makes
    the citizen an addict), only at 0 AP; a Twinoid refills one EP more."""
    if drugged or ap > 0:
        return None
    return max(ap, max_ap + level), refill_ep(ep, ext, 1 if key == "twinoid" else 0)


def drink_alcohol(drunk: bool, ap: int, ep: int, max_ap: int, ext: int):
    """Alcohol: (ap, ep), or None when drunk or hungover. AP to max, only at 0 AP."""
    if drunk or ap > 0:
        return None
    return max(ap, max_ap), refill_ep(ep, ext)


def drink_coffee(ap: int, ep: int, max_ap: int, max_ep: int, level: int):
    """Bloody Hot Coffee: (ap, ep, AP wasted), or None at max AP. +`level` AP up to max, +1 EP up to
    max EP, no daily limit."""
    if ap >= max_ap:
        return None
    new = min(max(max_ap, ap), ap + level)
    return new, max(ep, min(ep + 1, max_ep)), level - (new - ap)


def use_second_wind(ap: int, ep: int, max_ap: int, max_ep: int, sw_ap: int, sw_ep: int) -> tuple[int, int, int]:
    """Second Wind (hero action): (ap, ep, AP wasted). AP up to max (never above), EP even above max."""
    new = max(ap, min(ap + sw_ap, max_ap))
    return new, min(ep + sw_ep, max_ep + sw_ep), sw_ap - (new - ap)


# ===========================================================================
# Other: killing, scouting, wind, hero carrying, town size
# ===========================================================================

# Kill runs (docs/kill-route-plan.md; the weapons' action effects in ActionDataService)

@dataclass(frozen=True)
class Weapon:
    key: str
    label: str            # Fata name_en, before the " (state)" suffix
    bucket: str           # pair: 2 kills per use; single: 1 kill per use
    kind: str             # counted (N charges / shots, Empty), loaded (loaded / empty), plain
    ready: tuple[float, float] = (0, 0)       # (average, worst) uses of a plain / loaded weapon
    reload: str | None = None                 # item that refills it: battery | water
    reload_cap: tuple[float, float] = (0, 0)  # (average, worst) uses per reload item
    repairable: bool = False


WEAPONS = {w.key: w for w in (
    Weapon("laser", "Burning Laser Pointer", "pair", "counted", reload="battery", reload_cap=(3.25, 2)),
    Weapon("machete", "Machete", "pair", "plain", ready=(4, 1), repairable=True),
    Weapon("launcher", "Battery Launcher Mk. II", "single", "loaded", ready=(5, 1),
           reload="battery", reload_cap=(5, 1)),
    Weapon("knife", "Serrated Knife", "single", "plain", ready=(3, 1), repairable=True),
    Weapon("splash", "Aqua-Splash", "single", "counted", reload="water", reload_cap=(5, 5)),
    Weapon("pistol", "Water Pistol", "single", "counted", reload="water", reload_cap=(3, 3)),
)}


def state_cap(w: Weapon, state: int) -> tuple[float, float]:
    """(average, worst) uses a weapon in this state gives, before any reload or repair."""
    if w.kind == "counted":
        return state, state
    if state == 0:
        return 0, 0
    return w.ready


def kill_buckets(n: float) -> tuple[int, int]:
    """(pairs, singles) for n zombies in one zone (n rounded half up): a 2-kill weapon on a single
    zombie wastes a kill."""
    n = int(n + 0.5)
    return n // 2, n % 2


# Scout with Camouflage Vest: detection chance in a zone with zombies above the group's CP.

def scout_detection(zone_zombies: int, total_cp: int) -> tuple[float, float]:
    """Estimate scout camouflage detection probability (day, night).

    Returns (day_pct, night_pct) as floats in [0.0, 1.0].
    Assumes scout_level=0 (worst case — actual level unavailable from Fata Morgana).
    """
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


# Wind refill (docs/camping-plan.md 1.2; NightlyHandler.php, BuildingQueryListener.php): each
# night one sector; zones in it farther than WIND_DISTANCE km regain digs with this chance by
# Searchtower level (0 = none), x WIND_NOT_DEPLETED if the zone is not depleted.
WIND_REFILL = {0: 0.25, 1: 0.37, 2: 0.49, 3: 0.61, 4: 0.73, 5: 0.85}
WIND_DISTANCE = 2
WIND_NOT_DEPLETED = 0.33


def wind_refill_chance(level: int) -> float:
    """The chance a depleted zone in the wind sector regains digs, by Searchtower level (0-5)."""
    return WIND_REFILL[max(0, min(5, level))]


# A citizen carries one heavy item (a bike or trolley counts); a Guardian with the shield lowered
# carries two, and the group loses the shield's 2 CP from the moment the 2nd is carried.
GUARDIAN_CP_LOSS = 2


def heavy_cap(guardian: bool) -> int:
    return 2 if guardian else 1


TOWN_SIZE = 40   # citizens a standard town needs before its first attack
