"""Camping odds and the zone upgrade plan.

Rules verified in the game source (myhordes-docker/myhordes), see docs/camping-plan.md §1.2:
`CitizenHandler::getCampingOdds` / `getCampingValues` (sum of the terms / 100, clamped to
[0, cap]) and `getZoneBuildingBonus`. The odds are frozen the moment the citizen hides.

The pure functions (`camping_terms`, `camping_odds`, `plan_upgrades`) take plain values;
`format_camping_odds` reads a parsed Fata town (`data`) and prints the answer.
"""

from ..utils.fmt import header, plural, ruin_label
from . import camp_zones, camplog
from .cp import citizen_key
from .geo import fmt_xy, km, xy, zone_map
from .risk import DANGER_BAND, zone_is_today

# Previous campings (index = camping nights survived, capped at the end of the whole table).
_TAIL = [-50, -100, -200, -400, -1000, -2000, -5000]
PREVIOUS = {
    (False, False): [80, 60, 35, 15, 0] + _TAIL,
    (False, True): [80, 70, 60, 40, 30, 20, 0] + _TAIL,
    (True, False): [50, 30, 20, 10, 0] + _TAIL,        # Pandemonium town
    (True, True): [50, 45, 40, 30, 20, 10, 0] + _TAIL,
}
PRO_CAMPER_LIMIT = 6          # nights; the pro table applies only while nights < 6
PANDA_TOWN_BONUS = -30        # rules.yml `panda: modifiers.camping.default_bonus`
CROWD = [0, 0, -10, -30, -50, -70]
DISTANCE = [-100, -75, -50, -25, -10, 0, 0, 0, 0, 0, 0, 0, 5, 7, 10, 15, 20]
LIGHTHOUSE_UID = "small_lighthouse_#00"
SKILLS = ("none", "procamp", "reclusive1", "reclusive2", "reclusive3", "reclusive4")

IMPROVE_LEVEL, INSTALL_LEVEL, MAX_LEVEL_TO_ACT = 5, 9, 50   # actions allowed while level < 50

TERM_LABELS = {
    "previous": "previous nights", "tomb": "tomb", "town": "town type", "zone": "camp bonus",
    "zoneBuilding": "ruin", "lighthouse": "lighthouse", "campitems": "camp items",
    "zombies": "zombies", "campers": "crowd", "night": "night", "distance": "distance",
    "devastated": "devastated town",
}


def is_pro_camper(skill: str, nights: int) -> bool:
    """procamp (legacy skill, no limit) or any Reclusive level (limit 6 nights)."""
    if skill == "procamp":
        return True
    return skill.startswith("reclusive") and nights < PRO_CAMPER_LIMIT


def odds_cap(job: str, skill: str) -> float:
    """Survivalist 1.0; Reclusive top level (reclusive4) 0.99; everyone else 0.9."""
    cap = 0.9
    if skill == "reclusive4":
        cap = max(cap, 0.99)
    if job == "Survivalist":
        cap = max(cap, 1.0)
    return cap


def ruin_term(ruin: dict | None, hidden_before: int) -> int:
    """No ruin or ruin full: -25. Slot free: ruin bonus, buried ruin +15."""
    if not ruin:
        return -25
    slots = ruin.get("camp_slots")
    if slots is not None and slots >= 0 and hidden_before >= slots:
        return -25
    if int(ruin.get("digs_remaining") or 0) > 0:
        return 15
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
        "tomb": 8 if tomb else 0,
        "town": PANDA_TOWN_BONUS if panda else 0,
        "zone": level,
        "zoneBuilding": ruin_term(ruin, hidden_before),
        "lighthouse": 25 if lighthouse else 0,
        "campitems": 5 * camp_items,
        "zombies": zombies * (-3 if vest else -7),
        "campers": CROWD[min(len(CROWD) - 1, max(0, hidden_before))],
        "night": 10 if night else 0,
        "distance": DISTANCE[min(len(DISTANCE) - 1, max(0, distance))],
        "devastated": -50 if devastated else 0,
    }


def camping_odds(terms: dict[str, int], cap: float) -> float:
    return max(0.0, min(sum(terms.values()) / 100.0, cap))


def plan_upgrades(level: int, base_sum: int, cap: float, ap: int, items: int) -> dict:
    """Best sequence of improve (+5, 1 AP) and install (+9, 1 AP + 1 item) for a zone.

    `base_sum` = sum of the terms without the zone level. An action is allowed only while
    the level is below 50 (the last one may cross it). Counts (i improves, j installs) are
    searched exhaustively; improves first then installs is the order that allows the most
    (the biggest step last). Objective: highest capped odds, then fewest AP, then fewest items.
    Returns {improve, install, ap, items, level, odds}.
    """
    best = None
    for i in range(0, max(ap, 0) + 1):
        for j in range(0, min(items, ap - i) + 1):
            total = level + IMPROVE_LEVEL * i + INSTALL_LEVEL * j
            last = INSTALL_LEVEL if j else IMPROVE_LEVEL
            if (i or j) and total - last >= MAX_LEVEL_TO_ACT:
                continue
            odds = max(0.0, min((base_sum + total) / 100.0, cap))
            key = (-round(odds, 6), i + j, j)
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
            total = level + IMPROVE_LEVEL * i + INSTALL_LEVEL * j
            last = INSTALL_LEVEL if j else IMPROVE_LEVEL
            if (i or j) and total - last >= MAX_LEVEL_TO_ACT:
                continue
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


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _find_citizen(data: dict, name: str) -> dict | None:
    key = citizen_key(name)
    return next((c for c in data.get("citizens", []) if citizen_key(c["name"]) == key), None)


def lighthouse_built(data: dict) -> bool:
    return any(b.get("built") and b.get("uid") == LIGHTHOUSE_UID for b in data.get("buildings", []))


def is_panda(meta: dict) -> bool:
    """Pandemonium: the game type name is 'panda'; Fata's `hard` flag (meta.hardcore) is the
    same thing (the game's own XML API exports `hard` = type panda)."""
    return meta.get("game_type") == "panda" or bool(meta.get("hardcore"))


def _zombie_reading(z: dict | None, day) -> tuple[int, str]:
    """(zombies counted, note about the reading)."""
    if not z:
        return 0, "zone never visited by anyone on Fata: zombies assumed 0"
    n = z.get("zombies", -1)
    if z.get("danger_today") or n < 0:
        lo, hi = DANGER_BAND.get(z.get("danger"), (0, 9))
        band = f"{lo}-{hi}" if lo != hi else f"{lo}"
        return hi, f"no count today, danger level {band}: counted {hi}" + ("" if lo == hi else " (worst case)")
    if zone_is_today(z, day):
        return n, f"counted today (d{z.get('updated_day')})"
    return n, (f"counted on d{z.get('updated_day')}, NOT today: zombies grow every night, "
               "the real count is probably higher")


def format_camping_odds(data: dict, *, x: int | None, y: int | None, citizen: str = "",
                        skill: str = "none", camp_level: int = -1, ap: int = 0,
                        defense_items: int = 0, camp_items: int = 0, hidden_before: int = 0,
                        nights: int = -1, tomb: bool = False, vest: bool | None = None,
                        record: bool = True, town_id: int | None = None) -> str:
    if data.get("error"):
        return f"Error: {data['error']}"
    meta, day = data["meta"], data["meta"].get("day")
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
    if x is None or y is None:
        if cit is None:
            return "Error: give the zone (x, y) or a citizen name."
        cell = xy(cit)
        if cell is None or cit.get("inside_town"):
            return f"Error: {cit['name']} is in town (no position outside): give the zone (x, y)."
    else:
        cell = (x, y)
    if cell == (0, 0):
        return "Error: nobody camps in town: give a zone outside."

    job = cit["job"] if cit else "unknown"
    z = zone_map(data).get(cell)
    ruin = z.get("ruin") if z else None
    zombies, zombie_note = _zombie_reading(z, day)
    if vest is None:
        vest = job == "Scout"
    assumed = []
    if nights < 0:
        nights = 0
        sure = prob = 0
        if cit is not None and town_id is not None:
            sure, prob = camplog.counts(camplog.load_log(town_id), cit["id"])
        if sure + prob:
            nights = sure + prob
            assumed.append(f"camping nights from the log: {sure} sure + {prob} probable = {nights} counted "
                           "(pessimistic; the player can correct with nights=)")
        elif cit is not None and town_id is not None:
            assumed.append("camping nights survived by this citizen: assumed 0, the camping log shows none, "
                           "ask the player")
        else:
            assumed.append("camping nights survived by this citizen: assumed 0, ask the player")
    zone_key = fmt_xy(cell)
    can_record = record and town_id is not None and isinstance(day, int)
    if camp_level >= 0:
        if can_record:
            camp_zones.record_zone(town_id, zone_key, day, camp_level, "reported")
    else:
        est = None
        if town_id is not None and isinstance(day, int):
            est = camp_zones.estimate_level(camp_zones.load_zones(town_id).get(zone_key), day)
        if est:
            camp_level = est[0]
            assumed.append(f"camp bonus +{camp_level}%: {est[1]}"
                           + (" (-15% per night since)" if est[1].startswith("reported") and est[2] != day else ""))
        else:
            camp_level = 0
            assumed.append("camp bonus: assumed +0% (Fata does not know it; it drops 15% every night), ask the player")
    if hidden_before == 0:
        assumed.append("nobody hidden on the zone before the player: assumed")
    assumed.append("hiding between 19:00 and 06:59: night +10 included")
    if cit is None:
        assumed.append("no citizen given: job unknown, cap 90% (100% for a Survivalist)")
    if vest:
        assumed.append("Scout vest worn: zombies count -3 each instead of -7")
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

    where = fmt_xy(cell)
    if ruin:
        where += f", {ruin_label(ruin)}"
    who = f"{cit['name']} ({job})" if cit else "no citizen given"
    lines = [header("Camping odds", meta), f"Zone {where}, {km_} km. Citizen: {who}. "
             f"Skill: {skill}. Cap {_pct(cap)}.", ""]
    lines.append(f"Odds now (camp bonus +{camp_level}%): {_pct(now)}"
                 + (" (cap)" if now >= cap else ""))

    plan_used = False
    if ap > 0:
        plan = plan_upgrades(camp_level, base_sum, cap, ap, defense_items)
        if plan["ap"] == 0:
            lines.append("Plan: nothing to build: odds already at the cap." if now >= cap
                         else "Plan: no upgrade possible (upgrades only while the camp bonus is below 50%).")
        else:
            plan_used = True
            extra = ""
            if plan["ap"] < ap:
                extra = (f" ({plan['ap']} of {ap} AP are enough: odds capped or the camp bonus reaches 50%)"
                         if plan["odds"] >= cap or plan["level"] >= MAX_LEVEL_TO_ACT
                         else f" ({plan['ap']} of {ap} AP: more items needed to use the rest)")
            lines.append(f"Plan: {order_text(plan)}: {plan['ap']} AP, "
                         f"{plural(plan['items'], 'defensive item')}, camp bonus "
                         f"+{camp_level}% -> +{plan['level']}%{extra}")
            lines.append(f"Odds after the plan: {_pct(plan['odds'])}")
            terms = camping_terms(level=plan["level"], **kw)
            if can_record:
                camp_zones.record_zone(town_id, zone_key, day, plan["level"], "planned")
        top = max_level_plan(camp_level, ap, defense_items)
        if top["level"] > plan["level"]:
            lines.append(f"For the next nights: {order_text(top)} ({top['ap']} AP, "
                         f"{plural(top['items'], 'defensive item')}) takes the camp bonus to "
                         f"+{top['level']}% instead: same odds tonight, +{max(0, top['level'] - 15)}% "
                         "left tomorrow (-15% a night), shared by every camper on the zone.")
    else:
        lines.append("No plan (ap=0): ask the player how many AP they can spend on upgrades.")

    shown = ", ".join(f"{TERM_LABELS[k]} {v:+d}%" for k, v in terms.items() if v)
    lines.append(f"Breakdown{' after the plan' if plan_used else ''}: {shown or 'all terms 0'} "
                 f"= {sum(terms.values())}% (capped to 0..{round(cap * 100)}%)")
    lines.append(f"Zombies on the zone: {zombies}, {zombie_note}.")
    if ruin and int(ruin.get("digs_remaining") or 0) > 0:
        lines.append("Buried ruin: +15% until uncovered, then the ruin's own bonus.")
    lines.append("")
    lines.append("Assumptions:")
    lines += [f"- {a}" for a in assumed]
    lines.append("")
    lines.append("Advice: the odds freeze at the moment of hiding: upgrade first, hide last and "
                 "after 19:00; citizens who hide later on the zone take the crowd malus, "
                 "zombies count at hide time.")
    return "\n".join(lines)
