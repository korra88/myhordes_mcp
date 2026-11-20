"""Shared zone helpers: data freshness, night alerts, trapped citizens, threat texts, respawn check.

The rules they apply (zombie spread and estimates, danger bands, CP, Observation Platform) are in fata/game.py."""

from datetime import datetime

from ..utils.clock import age_text, data_datetime, fmt_epoch, now
from ..utils.fmt import plural, updated
from .game import (
    DANGER_LEVELS,
    EP_MIN_KM,
    HEROIC_RETURN_KM,
    MAX_CP_PER_CITIZEN,
    RESCUE_KM,
    skill_level_for,
    CP_PER_CITIZEN,
    Estimate,
    age_days,
    danger_band,
    platform_level,
    respawn_threshold,
    teleport_range,
    zombie_arrival,
    zone_estimate,
    zone_is_today,
)
from .geo import km, map_bounds, moves, xy, zone_map

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


def dried_coords(data: dict) -> set[str]:
    """Coords of depleted zones (no dig left). A citizen's position line carries
    this so "who is outside on depleted zones" needs one tool: measured
    2026-11-10, Haiku 5.5 read depletion only from the desert overview, which
    marks ruins and not plain zones, and answered "none" (4/4) while 5 citizens
    stood on the dried [1|0]."""
    return {z["coords"] for z in data.get("zones", []) if z.get("dried")}


def dried_line(data: dict) -> str | None:
    """'N outside on depleted zones: names', or None."""
    dried = dried_coords(data)
    names = [c["name"] for c in data.get("citizens", [])
             if not c["inside_town"] and c["coords"] in dried]
    if not names:
        return None
    return f"{len(names)} outside on depleted zones (dried: no dig left): {', '.join(sorted(names))}"


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
    names = ", ".join(f"{c['name']} {c['coords']} {plural(m, 'move')}" for m, _, c in rows[:farthest])
    more = f", +{len(rows) - farthest} more" if len(rows) > farthest else ""
    tele = ""
    if near:
        tele = (f"; {near} within the platform teleport ({reach} km)" if data.get("gate") == "open"
                else f"; {near} within the platform teleport range, but the gate is closed: no teleport")
    return f"⚠ {plural(len(rows), 'citizen')} outside {when} — farthest: {names}{more}{tele}{old}"


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


def is_stale(day, current) -> bool:
    """A reading from an earlier day than the current one."""
    age = age_days(day, current)
    return age is not None and age >= 1


def _staleness_tag(last_update_day: int | None, current_day: int | None) -> str:
    """Return a staleness warning if position data is old, empty string otherwise."""
    if is_stale(last_update_day, current_day):
        return " " + updated(last_update_day, True)
    return ""


def threat_text(est: Estimate, style: str = "map") -> str:
    """One text for a zone's zombies. style "map": appended to a zone line (', 3 zom→≤9 (est.)',
    nothing for a clear zone); style "route": the zone's zombie column ('3 zom→≤9 (est.)',
    'clear')."""
    k = est.kind
    if k == "danger_today":
        text = f"~{DANGER_LEVELS.get(est.danger, f'danger {est.danger}')} today" if est.danger else "clear today"
    elif k == "count":
        text = f"{est.count} zom" if est.count else "clear"
    elif k == "grown":
        text = f"{est.count} zom→≤{_n(est.max)} (est.)"
    elif k == "exposed":
        text = f"unexplored, high risk (≤{_n(est.max)} zom)"
    elif k in ("spread", "early"):
        text = (f"clear→≤{_n(est.max)} zom (spread risk, {est.dist}d away)" if est.max
                else "clear")
    elif k in ("band", "band_grown"):
        text = "" if not est.danger and style == "map" else f"~{DANGER_LEVELS.get(est.danger, f'danger {est.danger}')}"
        if k == "band_grown":
            text += f"→≤{_n(est.max)} (est.)"
    else:
        text = "clear"
    if style == "map":
        return f", {text}" if text and text != "clear" else ""
    return text


def _n(x: float) -> str:
    return str(int(x)) if x == int(x) else f"{x:g}"


def zone_threats(data: dict):
    """A function zone -> threat_text(zone_estimate(zone), "map") for the zones of `data`:
    the zombie spread (zombie_arrival) is solved once, here."""
    day = data["meta"].get("day")
    day = day if isinstance(day, int) else None
    zmap = zone_map(data)
    arrival = zombie_arrival(zmap, day, map_bounds(data))
    return lambda z: threat_text(zone_estimate(z, xy(z), day, zmap, arrival), "map")


def _zone_freshness(zone: dict, current_day: int | None) -> str:
    """Compact freshness for a zone line: ' (updated d7)', ' (updated d4, STALE)', or for
    a zone seen today through the platform radius ' (zombies today, items d7)' — zombies
    are today's, items and depletion from that day. Who updated it is left out (token cost)."""
    updated_day = zone.get("updated_day")
    if updated_day is None:
        return ""
    if zone.get("danger_today"):
        return f" (zombies today, items d{updated_day})"
    return " " + updated(updated_day, is_stale(updated_day, current_day))


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

def _skill_needed(table: dict[int, int], dist: int, prefix: str) -> str:
    level = skill_level_for(table, dist)
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
        f"Distance: {plural(moves((x, y)), 'move')} from town (AP/EP to walk it) · {dist} km",
        f"EP zone: {ep}",
        f"Observation Platform teleport: {tele}",
        f"Heroic Return (Reclusive): {heroic}",
        f"Rescue from town (University): {_skill_needed(RESCUE_KM, dist, 'U')}",
    ]


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
    per_day, threshold = respawn_threshold(meta.get("game_type"), day)
    zones = data.get("zones", [])

    seen = [z for z in zones if zone_is_today(z, day)]
    stale = [z for z in zones if not zone_is_today(z, day) and z["zombies"] >= 0]
    uncounted = [z for z in zones if not zone_is_today(z, day) and z["zombies"] < 0]
    seen_n = sum(danger_band(z.get("danger", 0), (0, 0))[0] if z["zombies"] < 0 or z.get("danger_today")
                 else z["zombies"] for z in seen)
    stale_n = sum(z["zombies"] for z in stale)
    days = sorted({z["updated_day"] for z in stale if z.get("updated_day") is not None})
    span = f"days {days[0]}–{days[-1]}" if len(days) > 1 else (f"day {days[0]}" if days else "earlier days")
    never = never_visited(data)
    missing = (f"{plural(never, 'zone')} never visited, " if never is not None else "") + f"{len(uncounted)} without a count"
    return {"day": day, "per_day": per_day, "threshold": threshold, "known": seen_n + stale_n,
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
        f"  Fata counts {known}: {seen_n} in {plural(len(t['seen']), 'zone')} seen today (danger lower bounds), "
        f"{stale_n} in {plural(len(t['stale']), 'zone')} counted on {span} (may have grown or been killed since). "
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
    lines = [f"## ⚠ Trapped or possibly trapped ({plural(len(hits), 'zone')}) — "
             "zombies > CP (exact zone CP when Fata has it, else ≥2 per citizen)"]
    for h in hits:
        when = f"zone updated {fmt_time(h['updated_on'])}" if h["updated_on"] else "zone update time unknown"
        extra = f", {h['ruin']}" if h["ruin"] else ""
        tp = " — platform teleport home available" if h["teleport"] else ""
        if h.get("cp_exact"):
            cp = f"{h['cp_min']} CP{' (terrorised)' if h['cp_min'] == 0 else ''} — TRAPPED"
        else:
            cp = f"≥{h['cp_min']} CP"
        lines.append(f"  {', '.join(h['citizens'])} {h['coords']}{extra}: {plural(h['zombies'], 'zombie')} vs {cp} ({when}){tp}")
    return lines


def trapped_lines(data: dict) -> list[str]:
    """The trapped-citizens warning for a town, as tool lines (empty if nobody is)."""
    return format_trapped(trapped_citizens(data), fmt_epoch)
