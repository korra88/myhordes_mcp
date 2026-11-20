"""Camping odds and the zone upgrade plan.

The rules (the odds terms, tables, caps, upgrade levels) are in fata/game.py, "Camping"; see
docs/camping-plan.md §1.2. This module resolves the night, the zombies and the camp level from a
parsed Fata town, searches the upgrades (`plan_upgrades`, `max_level_plan`); `format_camping_odds` reads a parsed Fata
town (`data`) and prints the answer.

Fata v1.3 sends the players' saved camp plans (`data["camp_plans"]`) and a camp-level
estimate per zone (`zone["camp_level"]`): see docs/camping-plan.md "Fata camp plans (v1.3)".
A plan for today on the zone supplies the defaults the caller left open, and `plan_player_odds`
recomputes Fata's own odds for each camper as a drift check.

`day` picks the night: 0 = tonight (the town's current day), a later day = a projection for
that night (its plans, the bonus typed in them or today's bonus minus 15 per night, today's
zombie reading): `format_camping_odds` states every such assumption.
"""

from ..utils.fmt import header, plural, ruin_label
from . import camp_zones, camplog
from .cp import citizen_key
from .geo import fmt_xy, in_bounds, km, map_bounds, spread_steps, xy, zone_map
from .game import (GROWTH_AVG, GROWTH_MAX, IMPROVE_LEVEL, INSTALL_LEVEL, MAX_LEVEL_TO_ACT, NIGHTLY_DROP, SKILLS,
                   camping_odds, camping_terms, danger_band, is_panda, level_after_nights, level_ok, lighthouse_built,
                   odds_cap, zombie_arrival, zombie_sources, zone_estimate, zone_is_today)
from .risk import respawn_totals
from .towndata import plans_for_citizen, plans_for_zone

TERM_LABELS = {
    "previous": "previous nights", "tomb": "tomb", "town": "town type", "zone": "camp bonus",
    "zoneBuilding": "ruin", "lighthouse": "lighthouse", "campitems": "camp items",
    "zombies": "zombies", "campers": "crowd", "night": "night", "distance": "distance",
    "devastated": "devastated town",
}


def skill_label(skill: str) -> str:
    """The hero skill as the player knows it ("" for none)."""
    if skill == "procamp":
        return "Pro camper"
    if skill.startswith("reclusive"):
        return f"Reclusive {skill[len('reclusive'):]}"
    return ""


def plan_upgrades(level: int, base_sum: int, cap: float, ap: int, items: int) -> dict:
    """Best sequence of improve (+5, 1 AP) and install (+9, 1 AP + 1 item) for a zone.

    `base_sum` = sum of the terms without the zone level. An action is allowed only while
    the level is below 50 (the last one may cross it). Counts (i improves, j installs) are
    searched exhaustively; improves first then installs is the order that allows the most
    (the biggest step last). Objective: highest capped odds, then fewest defensive items (they
    are consumed: plain improves preferred, user decision 2026-11-18), then fewest AP.
    Returns {improve, install, ap, items, level, odds}.
    """
    best = None
    for i in range(0, max(ap, 0) + 1):
        for j in range(0, min(items, ap - i) + 1):
            if not level_ok(level, i, j):
                continue
            total = level + IMPROVE_LEVEL * i + INSTALL_LEVEL * j
            odds = max(0.0, min((base_sum + total) / 100.0, cap))
            key = (-round(odds, 6), j, i + j)
            if best is None or key < best[0]:
                best = (key, {"improve": i, "install": j, "ap": i + j, "items": j,
                              "level": total, "odds": odds})
    return best[1]


def max_level_plan(level: int, ap: int, items: int) -> dict:
    """Highest zone level reachable with these AP and items (then fewest AP, fewest items):
    the players' multi-night strategy, since the level carries over (-15% a night) and every
    camper on the zone shares it."""
    best = None
    for i in range(0, max(ap, 0) + 1):
        for j in range(0, min(items, ap - i) + 1):
            if not level_ok(level, i, j):
                continue
            total = level + IMPROVE_LEVEL * i + INSTALL_LEVEL * j
            key = (-total, i + j, j)
            if best is None or key < best[0]:
                best = (key, {"improve": i, "install": j, "ap": i + j, "items": j, "level": total})
    return best[1]


def order_text(plan: dict) -> str:
    parts = []
    if plan["improve"]:
        parts.append(f"{plan['improve']}× improve")
    if plan["install"]:
        parts.append(f"{plan['install']}× install")
    return ", then ".join(parts) if parts else "nothing to do"


def plan_player_odds(plan: dict, idx: int) -> tuple[dict[str, int], int, int]:
    """(terms, uncapped %, capped %) of camper number `idx` (0-based, = people hidden before)
    of a parsed Fata plan (towndata._parse_camp_plans), from the plan's own inputs. Equals
    Fata's `theoretical_chances` / `effective_chances` (60/60 players, town 8299 day 26)."""
    q = plan["players"][idx]
    terms = camping_terms(
        nights=q["nights"], skill=q["skill"], panda=plan["hardcore"], tomb=q["tomb"],
        level=plan["level_after"], ruin=plan["ruin"], hidden_before=idx,
        lighthouse=plan["lighthouse"], camp_items=q["camp_items"], zombies=plan["zombies"],
        vest=q["vest"], night=plan["night"], distance=plan["distance"], devastated=plan["devastated"])
    return terms, sum(terms.values()), round(camping_odds(terms, odds_cap(q["job"], q["skill"])) * 100)


def _plan_block(plans: list[dict], me: dict | None, alive: set, ref: str = "tonight") -> list[str]:
    """The "Fata plan tonight" lines: one per plan, campers in hide order with Fata's odds,
    planned upgrades; a line per camper whose odds our formula does not reproduce."""
    lines = []
    for p in plans:
        lines.append(f"Fata plan {ref} on {p['coords']}" + (f", {p['ruin']['name']}" if p["ruin"] else "")
                     + f" (by {p['creator'] or '?'}): camp bonus {p['level_before']}% -> {p['level_after']}%"
                     f" (+{p['upgrades_pct']}% planned)")
        campers, drift = [], []
        for i, q in enumerate(p["players"]):
            e, t = q["fata_effective"], q["fata_theoretical"]
            campers.append(f"{i + 1}. {q['name']}{'*' if me is q else ''}{'' if q['citizen_id'] in alive else ' (dead)'} {e}%"
                           + (f" (uncapped {t}%)" if t is not None and t != e and t > 100 else ""))
            _, ours_t, ours_e = plan_player_odds(p, i)
            if (e, t) != (ours_e, ours_t):
                drift.append(f"  MISMATCH {q['name']}: our formula {ours_e}% (uncapped {ours_t}%), "
                             f"Fata {e}% (uncapped {t}%): inputs or rules drifted, report it")
        lines.append("  " + ", ".join(campers) + " (Fata's odds, in hiding order" + (", * = asked)" if me else ")"))
        lines += drift
    return lines


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _find_citizen(data: dict, name: str) -> dict | None:
    key = citizen_key(name)
    return next((c for c in data.get("citizens", []) if citizen_key(c["name"]) == key), None)


def _zombie_reading(z: dict | None, day) -> tuple[int, str]:
    """(zombies counted, note about the reading)."""
    if not z:
        return 0, "zone never visited by anyone on Fata: zombies assumed 0"
    n = z.get("zombies", -1)
    if z.get("danger_today") or n < 0:
        lo, hi = danger_band(z.get("danger"), (0, 9))
        band = f"{lo}-{hi}" if lo != hi else f"{lo}"
        return hi, f"no count today, danger level {band}: counted {hi}" + ("" if lo == hi else " (worst case)")
    if zone_is_today(z, day):
        return n, f"counted today (d{z.get('updated_day')})"
    return n, (f"counted on d{z.get('updated_day')}, NOT today: zombies grow every night, "
               "the real count is probably higher")


def resolve_night(data: dict, day_arg: int = 0) -> dict | str:
    """The night asked for: {day, target, future, ref, name}, or the error text.
    `day_arg` 0 = tonight (the town's current day), a later day = that night's projection."""
    day = data["meta"].get("day")
    target = day   # the night asked for (day N = the night of day N -> N+1)
    if day_arg and isinstance(day, int):
        if day_arg < day:
            return f"Error: day {day_arg} is already over (today is day {day}): ask for today or a later day."
        target = day_arg
    future = isinstance(day, int) and target > day
    if not future:
        night_ref, night_name = "tonight", "Tonight"
    elif target == day + 1:
        night_ref, night_name = "tomorrow night", "Tomorrow night"
    else:
        night_ref, night_name = f"the night of day {target}", f"Night of day {target}"
    return {"day": day, "target": target, "future": future, "ref": night_ref, "name": night_name}


def zone_reading(data: dict, cell: tuple, night: dict) -> tuple:
    """(zone, ruin, zombies, zombie note) of a cell for the night: the zone is None when nobody
    visited it; a future night keeps today's count and says so."""
    day, target = night["day"], night["target"]
    z = zone_map(data).get(cell)
    ruin = z.get("ruin") if z else None
    zombies, zombie_note = _zombie_reading(z, day)
    if night["future"]:
        zombies, zombie_note = _project_zombies(data, cell, z, zombies, zombie_note, day, target)
    return z, ruin, zombies, zombie_note


def _project_zombies(data: dict, cell: tuple, z: dict | None, zombies: int, note: str,
                     day: int, target: int) -> tuple[int, str]:
    """Zombies on the zone the night of `target`, from today's reading. Game rules in
    game.py: the number is zone_estimate at the later day (a zone with zombies grows, an empty
    zone gets some only once the spread front, zombie_arrival, reaches it)."""
    if not z or not zone_is_today(z, day) or z.get("danger_today") or z.get("zombies", -1) < 0:
        return zombies, note + "; zombies grow at night, the real count that night is probably higher"
    zones = zone_map(data)
    bounds = map_bounds(data) if data.get("meta") else None
    arrival = zombie_arrival(zones, day, bounds)
    if zombies > 0:
        n = round(zone_estimate(z, cell, day, zones, arrival, at=target).avg)
        return n, (f"{zombies} today (d{day}), +{GROWTH_AVG:g} a night is the usual growth (90%): "
                   f"counted {n} that night")
    first = arrival.get(cell)
    if first is None:
        text, reach = "none today and no zombies known on the map", 2
    else:
        when = first[0]
        near = min(((spread_steps(c, cell), c, seen) for c, seen, _n in zombie_sources(zones, day, danger=True)
                    if c != cell), default=None)
        reach = near[0] if near else 2
        text = ("none today; " + (f"nearest zombies known {plural(reach, 'zone')} away ({fmt_xy(near[1])}, "
                                  f"d{near[2]}); " if near else "")
                + "they spread one zone a night at most and zones seen empty hold them back: "
                + (f"none before the night of day {when}" if target < when else
                   f"they can be here from the night of day {when}, up to {GROWTH_MAX} a night: check before hiding"))
    # Zones nearer than that source and never visited could hold zombies of their own.
    unseen = sum(1 for dx in range(1 - reach, reach) for dy in range(1 - reach, reach)
                 if (c := (cell[0] + dx, cell[1] + dy)) not in zones and c != (0, 0)
                 and (bounds is None or in_bounds(bounds, c)))
    if unseen:
        text += (f"; {plural(unseen, 'zone')} {'closer' if first else 'around'} never visited on Fata "
                 "(may hold zombies)")
    t = respawn_totals(data) if data.get("meta") else None
    if t and t["known"] < t["threshold"]:
        text += "; a global respawn is possible (zombies regrow anywhere)"
    return 0, text


def typed_plan(zone_plans: list[dict], mine: dict | None) -> dict | None:
    """The Fata plan whose typed numbers apply to the zone: the caller's own, else the zone's
    plans when they all agree on the existing bonus."""
    return mine or (zone_plans[0] if zone_plans and len({p["level_before"] for p in zone_plans}) == 1 else None)


def fata_plan_upgrades(plan: dict | None) -> dict | None:
    """The upgrades a Fata plan adds on top of the zone's existing bonus, or None when it adds
    none: {creator, target_day, before, after, pct, improves (pct / 5, 1 AP each)}."""
    if not plan or plan["level_after"] <= plan["level_before"]:
        return None
    pct = plan["level_after"] - plan["level_before"]
    return {"creator": plan["creator"] or "a player", "target_day": plan["target_day"],
            "before": plan["level_before"], "after": plan["level_after"], "pct": pct,
            "improves": round(pct / IMPROVE_LEVEL)}


def plan_upgrade_text(up: dict, future: bool) -> str:
    """The sentence that tells the reader the Fata plan's upgrades are part of the starting level."""
    span = f"upgrades for +{up['pct']}% (+{up['before']}% -> +{up['after']}%)"
    n = plural(up["improves"], "improve")
    if future:
        return (f"Planned in {up['creator']}'s Fata plan for day {up['target_day']}: {span}, counted as done "
                f"({n} = {up['improves']} AP)")
    return (f"Fata plan ({up['creator']}): {span}. Not a game reading: check in game whether they are done; "
            f"if not, do them first ({n} = {up['improves']} AP, fewer with defensive items)")


def resolve_camp_level(data: dict, *, coords: str, z: dict | None, night: dict, camp_level: int,
                       zone_plans: list[dict], mine: dict | None, assumed: list[str],
                       town_id: int | None, can_record: bool, info: dict | None = None) -> int:
    """The zone's camp bonus (%) for the night: the value given (>= 0), else the plan's typed
    bonus, Fata's estimate, the recorded one or 0, minus 15 a night for a future night. Appends
    the source to `assumed`; records a reported value when `can_record`.

    A Fata plan for the night on the zone that adds upgrades (level_after > level_before) gives
    its level_after as the starting level (the upgrades are part of the plan, not re-planned),
    unless `camp_level` is given. `info` (out) receives {"plan": fata_plan_upgrades() or None}."""
    day, target, future = night["day"], night["target"], night["future"]
    if info is not None:
        info["plan"] = None
    zone_key = coords

    decay = NIGHTLY_DROP * (target - day) if future else 0
    if camp_level >= 0:
        if can_record:
            camp_zones.record_zone(town_id, zone_key, day, camp_level, "reported")
    else:
        est = None
        if town_id is not None and isinstance(day, int):
            est = camp_zones.estimate_level(camp_zones.load_zones(town_id).get(zone_key), day)
        fata_level = z.get("camp_level") if z else None
        # The camp bonus a plan for the night starts from, as its author typed it.
        typed = typed_plan(zone_plans, mine)
        up = fata_plan_upgrades(typed)
        # A future night without a plan on this zone: an earlier plan on it carries over.
        before = None
        if future and not typed:
            for d in range(target - 1, day - 1, -1):
                ps = plans_for_zone(data, coords, d)
                if ps and len({p["level_after"] for p in ps}) == 1:
                    before = ps[0]
                    break
        if up:
            camp_level = up["after"]
            if info is not None:
                info["plan"] = up
            assumed.append(f"camp bonus +{camp_level}%: the level after the upgrades of {up['creator']}'s Fata plan "
                           f"(the plan starts from +{up['before']}%), not a game reading")
            if not future and fata_level is not None and fata_level != up["before"]:
                assumed.append(f"Fata's zone estimate (+{fata_level}%) differs from the plan's existing bonus "
                               f"(+{up['before']}%): the plan's numbers are used")
        elif future and typed:
            camp_level = typed["level_before"]
            assumed.append(f"camp bonus +{camp_level}%: the existing bonus typed in "
                           f"{typed['creator'] or 'a player'}'s Fata plan for day {target}, not a game reading")
        elif before:
            nights_left = target - before["target_day"]
            camp_level = level_after_nights(before["level_after"], nights_left)
            assumed.append(f"camp bonus +{camp_level}%: +{before['level_after']}% planned in "
                           f"{before['creator'] or 'a player'}'s Fata plan for day {before['target_day']} minus "
                           f"{NIGHTLY_DROP * nights_left}% ({plural(nights_left, 'night')}), if those upgrades are done; "
                           "no upgrades after it")
        elif fata_level is not None or est:
            if fata_level is not None:
                base = fata_level
                what = "Fata estimate from the players' plans, not a game reading"
            else:
                base, what = est[0], est[1]
            if future:
                camp_level = max(0, base - decay)
                assumed.append(f"camp bonus +{camp_level}%: today's +{base}% ({what}) minus {decay}% "
                               f"({plural(target - day, 'night')} at {NIGHTLY_DROP}%), assuming no upgrades until then")
            else:
                camp_level = base
                assumed.append(f"camp bonus +{camp_level}%: " + (
                    f"{what} (the bonus drops 15% every night)" if fata_level is not None else
                    what + (" (-15% per night since)" if est[1].startswith("reported") and est[2] != day else "")))
        elif typed:
            camp_level = typed["level_before"]
            assumed.append(f"camp bonus +{camp_level}%: the existing bonus typed in "
                           f"{typed['creator'] or 'a player'}'s Fata plan, not a game reading")
        else:
            camp_level = 0
            assumed.append("camp bonus: assumed +0% (no Fata estimate for this zone; it drops 15% every night), ask the player")
    return camp_level


def format_camping_odds(data: dict, *, x: int | None, y: int | None, citizen: str = "",
                        skill: str = "none", camp_level: int = -1, ap: int = 0,
                        defense_items: int = 0, camp_items: int = 0, hidden_before: int = 0,
                        nights: int = -1, tomb: bool = False, vest: bool | None = None,
                        record: bool = True, town_id: int | None = None, day_arg: int = 0) -> str:
    if data.get("error"):
        return f"Error: {data['error']}"
    meta = data["meta"]
    night = resolve_night(data, day_arg)
    if isinstance(night, str):
        return night
    day, target, future = night["day"], night["target"], night["future"]
    night_ref, night_name = night["ref"], night["name"]
    skill = (skill or "none").strip().lower()
    if skill not in SKILLS:
        return f"Error: skill must be one of {', '.join(SKILLS)}."
    for label, v in (("ap", ap), ("defense_items", defense_items), ("camp_items", camp_items),
                     ("hidden_before", hidden_before)):
        if v < 0:
            return f"Error: {label} cannot be negative."

    cit = None
    if citizen.strip():
        cit = _find_citizen(data, citizen)
        if cit is None:
            return f"Error: '{citizen}' is not a living citizen of this town."
    assumed = []
    # A future night without a plan of its own: the citizen's latest plan before it (tonight's
    # first) gives the zone and, assuming they camp as planned until then, the nights.
    earlier = None
    if future and cit is not None and not plans_for_citizen(data, cit["id"], target):
        for d in range(target - 1, day - 1, -1):
            earlier = max(plans_for_citizen(data, cit["id"], d), key=lambda p: len(p["players"]), default=None)
            if earlier:
                break
    if x is None or y is None:
        if cit is None:
            return "Error: give the zone (x, y) or a citizen name."
        cell = xy(cit)
        own = max(plans_for_citizen(data, cit["id"], target), key=lambda p: len(p["players"]), default=None) or earlier
        if own:   # no zone given: the zone of the citizen's own Fata plan for tonight
            cell = xy(own["coords"])
            assumed.append(f"zone {own['coords']}: from {cit['name']}'s Fata plan"
                           + (f" (they stand on {fmt_xy(xy(cit))} now)" if xy(cit) != cell and not cit.get("inside_town") else ""))
        elif cell is None or cit.get("inside_town"):
            return f"Error: {cit['name']} is in town (no position outside): give the zone (x, y)."
    else:
        cell = (x, y)
    if cell == (0, 0):
        return "Error: nobody camps in town: give a zone outside."

    job = cit["job"] if cit else "unknown"
    z, ruin, zombies, zombie_note = zone_reading(data, cell, night)
    coords = fmt_xy(cell)
    zone_plans = plans_for_zone(data, coords, target)
    alive = {c["id"] for c in data.get("citizens", [])}
    mine = me = None   # the citizen's plan on this zone today (the biggest if several) and their entry
    if cit is not None:
        mine = max((p for p in zone_plans if any(q["citizen_id"] == cit["id"] for q in p["players"])),
                   key=lambda p: len(p["players"]), default=None)
        if mine:
            me = next(q for q in mine["players"] if q["citizen_id"] == cit["id"])
            others = [p for p in zone_plans if p is not mine and any(q["citizen_id"] == cit["id"] for q in p["players"])]
            if others:
                assumed.append(f"{cit['name']} is in {len(others) + 1} Fata plans for this zone {night_ref}: the one with "
                               f"the most campers ({mine['creator'] or '?'}'s) was used")
        else:
            elsewhere = [p["coords"] for p in plans_for_citizen(data, cit["id"], target)]
            if elsewhere:
                assumed.append(f"{cit['name']} has a Fata plan {night_ref} on {', '.join(elsewhere)}, not on this zone: "
                               "its values are not used")
    src = f"{mine['creator'] or 'a player'}'s Fata plan" if mine else ""
    # Without a plan for that night, the citizen's own entry in an earlier plan still gives the
    # hero skill, the vest, camp items and tomb (not the hiding order: another night).
    entry = me
    if entry is None and earlier is not None:
        entry = next(q for q in earlier["players"] if q["citizen_id"] == cit["id"])
        src = f"{earlier['creator'] or 'a player'}'s Fata plan for day {earlier['target_day']}"
    if entry:   # plan values fill in what the caller left at the default; explicit arguments win
        if skill == "none" and entry["skill"] != "none":
            skill = entry["skill"]
            assumed.append(f"hero skill {skill_label(skill)}: from {src}")
        if camp_items == 0 and entry["camp_items"]:
            camp_items = entry["camp_items"]
            assumed.append(f"{plural(camp_items, 'camp item')}: from {src}")
        if not tomb and entry["tomb"] and entry is me:
            tomb = True
            assumed.append(f"hidden in a dug grave (tomb +8): from {src}")
        if vest is None:
            vest = entry["vest"]
    if me:
        if hidden_before == 0:
            before = mine["players"][:mine["players"].index(me)]
            hidden_before = sum(1 for q in before if q["citizen_id"] in alive)
            dead = len(before) - hidden_before
            assumed.append(f"{hidden_before} hidden on the zone before the player: from {src}"
                           + (f" ({dead} earlier camper{'s' if dead > 1 else ''} in it died, not counted)" if dead else "")
                           if hidden_before or dead else f"first to hide on the zone: from {src}")
    if vest is None:
        vest = job == "Scout"
    if nights < 0 and me:
        nights = me["nights"]
        assumed.append(f"camping nights survived: {nights}, from {src}")
    elif nights < 0 and earlier:
        q = next(q for q in earlier["players"] if q["citizen_id"] == cit["id"])
        nights = q["nights"] + (target - earlier["target_day"])
        assumed.append(f"camping nights survived: {nights} = {q['nights']} in {earlier['creator'] or 'a player'}'s "
                       f"Fata plan for day {earlier['target_day']} + {target - earlier['target_day']}, assuming "
                       "every night until then is camped as planned (ask the player)")
    elif nights < 0:
        nights = 0
        sure = prob = plnd = 0
        if cit is not None and town_id is not None:
            sure, prob, plnd = camplog.counts(camplog.load_log(town_id), cit["id"])
        if sure + prob + plnd:
            nights = sure + prob + plnd
            assumed.append(f"camping nights from the log: {sure} sure + {prob} probable + {plnd} planned = {nights} "
                           "counted (pessimistic; the player can correct with nights=)")
        elif cit is not None and town_id is not None:
            assumed.append("camping nights survived by this citizen: assumed 0, the camping log shows none, "
                           "ask the player")
        else:
            assumed.append("camping nights survived by this citizen: assumed 0, ask the player")
        if future and not me:
            until = "tonight's camping is" if target == day + 1 else f"nights camped from tonight to day {target - 1} are"
            assumed.append(f"camping nights survived up to now only: {until} not included, ask the player")
    zone_key = coords
    can_record = record and town_id is not None and isinstance(day, int) and not future
    plan_info: dict = {}
    camp_level = resolve_camp_level(data, coords=coords, z=z, night=night, camp_level=camp_level,
                                    zone_plans=zone_plans, mine=mine, assumed=assumed,
                                    town_id=town_id, can_record=can_record, info=plan_info)
    if plan_info.get("plan"):
        assumed.append(plan_upgrade_text(plan_info["plan"], future))
    if hidden_before == 0 and not me:
        assumed.append("nobody hidden on the zone before the player: assumed")
    assumed.append("hiding between 19:00 and 06:59: night +10 included")
    if cit is None:
        assumed.append("no citizen given: job unknown, cap 90% (100% for a Survivalist)")
    if vest:
        assumed.append("Scout vest worn: zombies count -3 each instead of -7" + (f" (from {src})" if me else ""))
    if not z:
        assumed.append(zombie_note)
    if ruin and ruin.get("camp_boost") is None:
        assumed.append("ruin camping bonus missing in this data: counted 0")

    km_ = km(*cell)
    kw = dict(nights=nights, skill=skill, panda=is_panda(meta), tomb=tomb, ruin=ruin,
              hidden_before=hidden_before, lighthouse=lighthouse_built(data),
              camp_items=camp_items, zombies=zombies, vest=vest, night=True, distance=km_,
              devastated=bool(meta.get("devastated")))
    cap = odds_cap(job, skill)
    terms = camping_terms(level=camp_level, **kw)
    now = camping_odds(terms, cap)
    base_sum = sum(terms.values()) - camp_level

    where = coords
    if ruin:
        where += f", {ruin_label(ruin)}"
    hero = skill_label(skill)
    if cit:
        who = f"{cit['name']} ({job}" + (f", hero skill {hero})" if hero else ")")
    else:
        who = "no citizen given" + (f" (hero skill {hero})" if hero else "")
    if not future:
        which = f"Night of day {target} (tonight)." if isinstance(day, int) else "Tonight."
    else:
        which = (f"Night of day {target} ({'tomorrow' if target == day + 1 else f'in {target - day} days'}): "
                 "a projection from today's data.")
    lines = [header("Camping odds", meta), which,
             f"Zone {where}, {km_} km. Citizen: {who}. Cap {_pct(cap)}.", ""]
    lines.append(f"Odds {'now' if not future else 'that night'} (camp bonus +{camp_level}%): {_pct(now)}"
                 + (" (cap)" if now >= cap else ""))

    plan_used = False
    left = (lambda lvl: level_after_nights(lvl, 1))
    nxt = "tomorrow" if not future else "the next night"
    spare = round(sum(terms.values())) - round(cap * 100)
    plan = None
    if now >= cap:
        per = 3 if vest else 7
        k = spare // per
        lines.append(f"{night_name}: no upgrade needed, odds at the cap with {spare} points to spare "
                     f"({plural(k, 'extra zombie')} at hide time keep{'s' if k == 1 else ''} the cap, {k + 1} would not)."
                     if k else
                     f"{night_name}: no upgrade needed, odds at the cap with {spare} points to spare "
                     f"(one more zombie at hide time would drop the odds below the cap).")
        floor_level = camp_level
    elif ap > 0:
        plan = plan_upgrades(camp_level, base_sum, cap, ap, defense_items)
        if plan["ap"] == 0:
            lines.append(f"{night_name}: no upgrade possible (upgrades only while the camp bonus is below 50%).")
        else:
            plan_used = True
            extra = ""
            if plan["ap"] < ap:
                extra = (f" ({plan['ap']} of {ap} AP are enough: odds capped or the camp bonus reaches 50%)"
                         if plan["odds"] >= cap or plan["level"] >= MAX_LEVEL_TO_ACT
                         else f" ({plan['ap']} of {ap} AP: more items needed to use the rest)")
            lines.append(f"{night_name}: {order_text(plan)}: {plan['ap']} AP, "
                         f"{plural(plan['items'], 'defensive item')}, camp bonus "
                         f"+{camp_level}% -> +{plan['level']}%{extra}")
            lines.append(f"Odds after the plan: {_pct(plan['odds'])}")
            terms = camping_terms(level=plan["level"], **kw)
            if can_record:
                camp_zones.record_zone(town_id, zone_key, day, plan["level"], "planned")
        floor_level = plan["level"]
    else:
        lines.append("No plan (ap=0): ask the player how many AP they can spend on upgrades.")
        floor_level = camp_level
    if ap > 0:
        top = max_level_plan(camp_level, ap, defense_items)
        if left(top["level"]) > left(floor_level):
            lines.append(f"Optional, for later nights only (no effect on the odds {'tonight' if not future else 'that night'}): "
                         f"{order_text(top)} ({top['ap']} AP, {plural(top['items'], 'defensive item')}) "
                         f"-> camp bonus +{top['level']}% {'tonight' if not future else 'that night'}, "
                         f"+{left(top['level'])}% left {nxt}. Only the bonus above +{NIGHTLY_DROP}% survives the night.")

    shown = ", ".join(f"{TERM_LABELS[k]} {v:+d}%" for k, v in terms.items() if v)
    lines.append(f"Breakdown{' after the plan' if plan_used else ''}: {shown or 'all terms 0'} "
                 f"= {sum(terms.values())}% (capped to 0..{round(cap * 100)}%)")
    lines.append(f"Zombies on the zone: {zombies}, {zombie_note}.")
    if ruin and int(ruin.get("digs_remaining") or 0) > 0:
        lines.append("Buried ruin: +15% until uncovered, then the ruin's own bonus.")
    if zone_plans:
        lines.append("")
        lines += _plan_block(zone_plans, me, alive, night_ref)
    lines.append("")
    lines.append("Assumptions:")
    lines += [f"- {a}" for a in assumed]
    lines.append("")
    lines.append("Advice: the odds freeze at the moment of hiding: upgrade first, hide last and "
                 "after 19:00; citizens who hide later on the zone take the crowd malus, "
                 "zombies count at hide time.")
    return "\n".join(lines)
