"""Shared zone helpers: coordinates, data freshness, zombie spread and threat estimates."""

from datetime import datetime

from ..utils.clock import age_text, data_datetime, fmt_epoch, now
from .geo import EP_MIN_KM, NEIGHBOURS8, km, moves, xy

# Evening alerts. By day an open gate, citizens far out and defense below the
# estimate are all normal; they become alarms as the attack (23:59, game time)
# gets close. Thresholds are the player's (2026-10-16).
GATE_WARN_FROM = (23, 0)
OUTSIDE_WARN_FROM = (22, 0)   # time to walk back before the gate closes
DEFENSE_WARN_FROM = (23, 0)
ATTACK_AT = "23:59"


def _evening(data: dict, warn_from: tuple[int, int], at: datetime | None) -> tuple[str, str] | None:
    """None before warn_from or on a past day's snapshot. Else (when, note): when the
    reading is from (`23:05`, or `the last update (22:30, 50 min ago)`), and a note
    that the data predates the warning window, since the state is only known as of
    Fata's last update."""
    meta = data["meta"]
    if meta.get("live") is False:
        return None
    clock = at or now()
    if (clock.hour, clock.minute) < warn_from:
        return None
    seen = data_datetime(meta)
    if seen and seen.date() == clock.date() and (seen.hour, seen.minute) >= warn_from:
        return f"at {seen:%H:%M}", ""
    when = f"{seen:%H:%M}, {age_text(seen, clock)} ago" if seen else "time unknown"
    return f"at the last update ({when})", "; data is old: check the game"


def gate_alert(data: dict, at: datetime | None = None) -> str | None:
    """The warning for an open gate, or None (only from 23:00, only on live data)."""
    if data.get("gate") != "open":
        return None
    ev = _evening(data, GATE_WARN_FROM, at)
    if ev is None:
        return None
    when, old = ev
    return f"⚠ Gate OPEN {when} — close it before the attack ({ATTACK_AT}){old}"


def gate_line(data: dict, at: datetime | None = None) -> str:
    """'Gate: …' for tool headers, with the context that keeps an open gate by day
    from reading as an alarm."""
    if data.get("gate") != "open":
        return "Gate: closed"
    if data["meta"].get("live") is False:
        return "Gate: open (snapshot of a past day)"
    return gate_alert(data, at) or "Gate: open (normal by day; closed after 23:00, before 23:59)"


def outside_alert(data: dict, at: datetime | None = None, farthest: int = 5) -> str | None:
    """Citizens still outside from 22:00, farthest first (moves = AP to walk home)."""
    out = [c for c in data.get("citizens", []) if not c["inside_town"] and xy(c)]
    if not out:
        return None
    ev = _evening(data, OUTSIDE_WARN_FROM, at)
    if ev is None:
        return None
    when, old = ev
    rows = sorted(((moves((x, y)), km(x, y), c) for c in out for x, y in [xy(c)]),
                  key=lambda r: -r[0])
    reach = teleport_range(platform_level(data))
    near = sum(1 for _, k, _ in rows if k <= reach) if reach else 0
    names = ", ".join(f"{c['name']} {c['coords']} {m} moves" for m, _, c in rows[:farthest])
    more = f", +{len(rows) - farthest} more" if len(rows) > farthest else ""
    tele = ""
    if near:
        tele = (f"; {near} within the platform teleport ({reach} km)" if data.get("gate") == "open"
                else f"; {near} within the platform teleport range, but the gate is closed: no teleport")
    return f"⚠ {len(rows)} citizens outside {when} — farthest: {names}{more}{tele}{old}"


def defense_status(data: dict) -> tuple[str, int] | None:
    """('SAFE' | 'AT RISK' | 'DANGER', gap) against tonight's estimate, or None."""
    today = (data.get("estimations") or {}).get("today") or {}
    low, high = today.get("min"), today.get("max")
    total = (data.get("defense") or {}).get("total")
    if low is None or high is None or total is None:
        return None
    if total >= high:
        return "SAFE", 0
    if total >= low:
        return "AT RISK", high - total
    return "DANGER", low - total


def defense_alert(data: dict, at: datetime | None = None) -> str | None:
    """Defense below tonight's estimate, from 23:00."""
    st = defense_status(data)
    if st is None or st[0] == "SAFE":
        return None
    ev = _evening(data, DEFENSE_WARN_FROM, at)
    if ev is None:
        return None
    when, old = ev
    total = data["defense"]["total"]
    today = data["estimations"]["today"]
    if st[0] == "DANGER":
        return f"⚠ Defense {total} {when}: {st[1]} short of tonight's minimum ({today['min']}){old}"
    return f"⚠ Defense {total} {when}: covers the minimum, {st[1]} short of the maximum ({today['max']}){old}"


def night_alerts(data: dict, at: datetime | None = None, *, gate: bool = True) -> list[str]:
    """The evening alerts that apply now: gate (optional), citizens outside, defense."""
    alerts = [gate_alert(data, at) if gate else None, outside_alert(data, at), defense_alert(data, at)]
    return [a for a in alerts if a]


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


# Nightly growth (MapMaker::spreadCycleMH, day >= 2): a zone with zombies gets +1 (90%), +0 (5%)
# or +2 (5%); an empty zone next to a zone with more zombies gets 1-2 (or none); an empty zone
# without infected neighbours stays empty. The 8 surrounding zones are neighbours.
# Average +1.0 per night, worst case +2. One place for every estimate (map, route risks, kills).
GROWTH_AVG = 1.0
GROWTH_MAX = 2


def zombie_growth(zombies: int, nights: int) -> tuple[int, float, int]:
    """(min, avg, max) zombies in a zone counted with `zombies` (> 0) `nights` nights ago."""
    n = max(0, nights)
    return zombies, zombies + GROWTH_AVG * n, zombies + GROWTH_MAX * n


def _zombie_max_estimate(zombies: int, last_day: int | None, current_day: int | None) -> int | None:
    """Return a pessimistic max zombie estimate for a stale zone (+2 per night, the
    game's worst case, see zombie_growth).

    Returns None if the zone is current or days elapsed is 0.
    """
    if last_day is None or current_day is None:
        return None
    age = current_day - last_day
    if age <= 0:
        return None
    return zombie_growth(zombies, age)[2]




def _build_spread_map(
    zone_map: dict[tuple[int, int], dict],
    current_day: int | None,
) -> dict[tuple[int, int], tuple[int, int]]:
    """BFS from all known zombie zones to compute minimum spread distance.

    For each cell in zone_map that currently has zombies (zm > 0), we BFS
    outward in 8 directions (the game's neighbours). The result maps (x, y) -> (bfs_dist, source_zm)
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
        for dx, dy in NEIGHBOURS8:
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
        # Worst case: the first night spawns 2 (1-2), then +2 per night, capped at source count
        nights_of_growth = age - bfs_dist  # nights the zone could have grown after first infection
        est = min(GROWTH_MAX + GROWTH_MAX * nights_of_growth, source_zm)
        return bfs_dist, max(1, est)
    return None


def _zone_threat(zone: dict, current_day: int | None = None, spread_map: dict | None = None, coords: tuple[int, int] | None = None) -> str:
    """Format zombie count or danger estimate for a zone.

    If an exact zombie count was reported (zm >= 0), show it.
    For stale zones with zombies, appends a pessimistic max estimate (+2/night).
    For stale clear zones, checks spread_map: if zombie neighbors could have
    reached this cell within the elapsed days, shows a spread risk warning.
    Otherwise fall back to the danger level from in-game map exploration.
    """
    if zone.get("danger_today"):
        # Today's estimate beats the count from an older update.
        danger = zone.get("danger", 0)
        return f", ~{DANGER_LEVELS.get(danger, f'danger {danger}')} today" if danger else ", clear today"
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
    """Compact freshness for a zone line: ' (updated d7)', ' (updated d4, STALE)', or for
    a zone seen today through the platform radius ' (zombies today, items d7)' — zombies
    are today's, items and depletion from that day. Who updated it is left out (token cost)."""
    updated_day = zone.get("updated_day")
    if updated_day is None:
        return ""
    if zone.get("danger_today"):
        return f" (zombies today, items d{updated_day})"
    stale = current_day is not None and current_day - updated_day >= 1
    return f" (updated d{updated_day}" + (", STALE)" if stale else ")")


# Heavy parts that assemble into a defensive object; Fata files them under Miscellaneous.
DEFENSE_PARTS = {"Sheet Metal (parts)", "Crate Lid", "Bag of Cement", "Flatpacked Furniture",
                 "Car Door (incomplete)"}


def is_defense(item: dict) -> bool:
    """A defensive object (Fata category Armor) or a part that assembles into one."""
    return item.get("category") == "Armor" or item["name"] in DEFENSE_PARTS


def _item_tags(item: dict) -> str:
    """' (heavy, defense)' — what limits carrying it and what it is worth to the bank."""
    tags = ["heavy"] if item.get("heavy") else []
    if item.get("category") == "Armor":
        tags.append("defense")
    elif item["name"] in DEFENSE_PARTS:
        tags.append("defense part")
    return f" ({', '.join(tags)})" if tags else ""


def fmt_items(items: list[dict]) -> str:
    """'Battery ×2, Old Door (heavy, defense), Screwdriver [B]' — ×1 left out."""
    return ", ".join(i["name"] + _item_tags(i) + (f" ×{i['count']}" if i["count"] != 1 else "")
                     + (" [B]" if i.get("broken") else "") for i in items)


def _zone_status(zone: dict) -> str:
    """Scavenging and presence notes from /towndata, e.g. ', abundant, excavated day 7, CP 6 at last update'."""
    parts = []
    if not zone.get("dried") and zone.get("scav_level"):
        parts.append(zone["scav_level"])
    if zone.get("excavated"):
        parts.append(f"Scavenger-excavated d{zone['excavated_day']}" if zone.get("excavated_day")
                     else "Scavenger-excavated")
    if zone.get("cp"):
        parts.append(f"CP {zone['cp']} at last update")
    return "".join(f", {p}" for p in parts)


# ---------------------------------------------------------------------------
# Trapped citizens (zombies outnumber the citizens' control points)
# ---------------------------------------------------------------------------

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


def _skill_needed(table: dict[int, int], dist: int, prefix: str) -> str:
    level = next((lvl for lvl, reach in table.items() if dist <= reach), None)
    top = max(table.values())
    if level is None:
        return f"out of range ({dist} km, max {top} km)"
    if level == 1:
        return f"yes, any level ({prefix}1+: {table[1]} km)"
    return f"needs {prefix}{level}+ ({table[level]} km)"


def zone_reach(data: dict, x: int, y: int) -> list[str]:
    """How far [x|y] is from town and which ways home reach it, as tool lines."""
    dist = km(x, y)
    level = platform_level(data)
    reach = teleport_range(level)
    if level is None or reach == 0:
        why = "platform not built" if level is None else f"platform level {level}, teleport from level 3"
        tele = f"no ({why})"
    elif dist <= reach:
        gate = ("gate open at the last update" if data.get("gate") == "open"
                else "gate CLOSED at the last update: no teleport until it opens")
        tele = f"yes (level {level} reaches {reach} km; {gate}; not a move, no thirst)"
    else:
        tele = f"no ({dist} km, level {level} reaches {reach} km)"
    ep = ("yes: moves leaving this zone pay EP first" if dist >= EP_MIN_KM
          else f"no: under {EP_MIN_KM} km, moves from here cost AP")
    heroic = _skill_needed(HEROIC_RETURN_KM, dist, "R")
    if not heroic.startswith("out of range"):
        heroic += "; works with the gate closed"
    return [
        f"Distance: {moves((x, y))} moves from town (AP/EP to walk it) · {dist} km",
        f"EP zone: {ep}",
        f"Observation Platform teleport: {tele}",
        f"Heroic Return (Reclusive): {heroic}",
        f"Rescue from town (University): {_skill_needed(RESCUE_KM, dist, 'U')}",
    ]


# Global respawn (MapMaker::aboveMinNumberOfZombies, rules.yml modifiers): at night, after
# the attack and before zombies spread, if the whole map holds fewer than
# massive_respawn_threshold × day × massive_respawn_factor zombies (50 × 0.5 = 25 per day;
# small towns 30 × 0.5 = 15), the map regrows from its day-1 layout until it reaches that
# number, and the zombies already there are added on top. The day is the new one:
# NightlyHandler::advance_day increments it before stage3_zones.
RESPAWN_PER_DAY = {"small": 15}
DEFAULT_RESPAWN_PER_DAY = 25


# The danger levels (DANGER_LEVELS) as zombie counts (min, max). "6+" has no top, so it
# counts as 9: above any single citizen's 8 CP. An unknown level has no band: callers pick
# their own fallback (kills: the top band; pathing: none for a zone known only by its band).
DANGER_BAND = {0: (0, 0), 1: (1, 2), 2: (3, 5), 3: (6, 9)}
DANGER_TOP = DANGER_BAND[3]
_DANGER_MIN = {d: lo for d, (lo, _) in DANGER_BAND.items()}


def danger_band(danger, default=None):
    """(min, max) zombies of a danger level, `default` if the level is unknown."""
    return DANGER_BAND.get(danger, default)


def zone_is_today(zone: dict, day) -> bool:
    """Whether a zone's zombie reading is today's: seen today (Fata nvt=false: a visit,
    or the platform radius at night), or, in legacy data without that flag, counted
    on an update made today."""
    if "seen_today" in zone:
        return bool(zone["seen_today"])
    return zone.get("zombies", -1) >= 0 and zone.get("updated_day") == day


def never_visited(data: dict) -> int | None:
    """Zones nobody ever visited (Fata nyv). data['zones'] holds every other zone,
    the town zone included."""
    total = data["meta"].get("map_zones")
    return max(0, total - len(data.get("zones", []))) if total else None


def respawn_totals(data: dict) -> dict | None:
    """Tonight's global-respawn threshold and the zombies Fata can see, or None on a past
    day / without a day. Keys: day, per_day, threshold, known (= seen_n + stale_n), seen,
    seen_n, stale, stale_n, span, never (None if unknown), uncounted, missing."""
    meta = data["meta"]
    day = meta.get("day")
    if not isinstance(day, int) or meta.get("live") is False:
        return None
    per_day = RESPAWN_PER_DAY.get(meta.get("game_type"), DEFAULT_RESPAWN_PER_DAY)
    zones = data.get("zones", [])

    seen = [z for z in zones if zone_is_today(z, day)]
    stale = [z for z in zones if not zone_is_today(z, day) and z["zombies"] >= 0]
    uncounted = [z for z in zones if not zone_is_today(z, day) and z["zombies"] < 0]
    seen_n = sum(_DANGER_MIN.get(z.get("danger", 0), 0) if z["zombies"] < 0 or z.get("danger_today")
                 else z["zombies"] for z in seen)
    stale_n = sum(z["zombies"] for z in stale)
    days = sorted({z["updated_day"] for z in stale if z.get("updated_day") is not None})
    span = f"days {days[0]}–{days[-1]}" if len(days) > 1 else (f"day {days[0]}" if days else "earlier days")
    never = never_visited(data)
    missing = (f"{never} zones never visited, " if never is not None else "") + f"{len(uncounted)} without a count"
    return {"day": day, "per_day": per_day, "threshold": per_day * (day + 1), "known": seen_n + stale_n,
            "seen": seen, "seen_n": seen_n, "stale": stale, "stale_n": stale_n, "span": span,
            "never": never, "uncounted": uncounted, "missing": missing}


def respawn_check(data: dict) -> list[str]:
    """Tonight's global-respawn threshold against the zombies Fata can see. Fata never
    sees the whole map (unvisited zones, counts from older days), so this states what
    is counted and what is not, and gives a verdict only on what is seen."""
    t = respawn_totals(data)
    if t is None:
        return []
    day, per_day, threshold, known = t["day"], t["per_day"], t["threshold"], t["known"]
    seen_n, stale_n, span, missing = t["seen_n"], t["stale_n"], t["span"], t["missing"]
    if known >= threshold:
        verdict = (f"above the threshold on what Fata sees ({known} ≥ {threshold}): no global respawn "
                   "tonight, unless those older counts were killed since")
    else:
        verdict = (f"below the threshold on what Fata sees ({known} < {threshold}), but {missing} are not "
                   "counted: a respawn is possible, not certain")
    return [
        f"### Global respawn check (tonight, end of day {day})",
        f"  Threshold: {threshold} zombies on the whole map ({per_day} × day {day + 1}). Fewer → the map "
        "regrows from its day-1 layout, on top of the zombies already there.",
        f"  Fata counts {known}: {seen_n} in {len(t['seen'])} zones seen today (danger lower bounds), "
        f"{stale_n} in {len(t['stale'])} zones counted on {span} (may have grown or been killed since). "
        f"Not counted: {missing}.",
        f"  → {verdict}",
    ]


def zone_cp(zone: dict, people: list[dict]) -> int | None:
    """The zone's CP reading (/towndata `human`, game-sourced) if it covers the
    citizens now standing there, else None.

    Covers them when each one has a known position time and none moved after
    the zone update. 0 is a real value (terrorised citizens have 0 CP); more
    than 8 per citizen is not, so someone who left must still be counted."""
    cp, t = zone.get("cp"), zone.get("updated_on")
    if cp is None or not t or not people:
        return None
    if any(not c.get("last_update_time") or c["last_update_time"] > t for c in people):
        return None
    if cp > MAX_CP_PER_CITIZEN * len(people):
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
        cell = xy(zone)
        dist = km(*cell) if cell else None
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
        extra = f", {h['ruin']}" if h["ruin"] else ""
        tp = " — platform teleport home available" if h["teleport"] else ""
        if h.get("cp_exact"):
            cp = f"{h['cp_min']} CP{' (terrorised)' if h['cp_min'] == 0 else ''} — TRAPPED"
        else:
            cp = f"≥{h['cp_min']} CP"
        lines.append(f"  {', '.join(h['citizens'])} {h['coords']}{extra}: {h['zombies']} zombies vs {cp} ({when}){tp}")
    return lines


def trapped_lines(data: dict) -> list[str]:
    """The trapped-citizens warning for a town, as tool lines (empty if nobody is)."""
    return format_trapped(trapped_citizens(data), fmt_epoch)
