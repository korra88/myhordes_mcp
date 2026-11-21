"""`plan_camping`: one camping tool for one camper or a group, one night or several.

It picks the engine from the question (2026-11-21, docs/bot-eval-plan.md 6.8):
- ONE camper, ONE night -> `camping.format_camping_odds`: odds now, the upgrade plan, the
  per-term breakdown, the cap margin, Fata's plan block with the MISMATCH drift check, and the
  camp bonus recorded for the zone (`record`).
- a group (two or more campers), several nights (`until_day`), a Tamer or a Survivalist
  override -> `groupcamp.format_group_camping`: hiding order, graves, camp items, steaks, the
  multi-night chain.
With `campers` empty the campers are those of the Fata plan(s) for that night on the zone: one
camper (or none: odds for "anyone") goes to the one-camper engine, more to the group engine.
"""

from .camping import format_camping_odds, resolve_night
from .geo import fmt_xy, xy
from .groupcamp import format_group_camping, parse_group
from .towndata import plans_for_zone

# Overrides the one-camper engine has an argument for (tamer, surv, notomb need the group engine).
_SINGLE_KEYS = {"name", "skill", "nights", "tomb", "items", "vest"}


def _plan_campers(data: dict, cell: tuple | None, night: dict) -> tuple[tuple | None, list[str]]:
    """(zone, names of the living campers) of the Fata plan(s) for the night: on `cell` when given, else on the
    only zone planned that night (None when none or several). A future night without a plan of
    its own falls back to the latest earlier day's plans, as the engines do."""
    day, target = night["day"], night["target"]
    alive = {c["id"]: c["name"] for c in data.get("citizens", [])}
    days = [target] + (list(range(target - 1, day - 1, -1)) if night["future"] and isinstance(day, int) else [])
    for d in days:
        if cell is not None:
            plans = plans_for_zone(data, fmt_xy(cell), d)
        else:
            plans = [p for p in data.get("camp_plans") or [] if p["target_day"] == d]
            zones = {p["coords"] for p in plans}
            if len(zones) > 1:
                return None, []
            if zones:
                cell = xy(next(iter(zones)))
        if plans:
            ids = dict.fromkeys(q["citizen_id"] for p in plans for q in p["players"] if q["citizen_id"] in alive)
            return cell, [alive[i] for i in ids]
    return cell, []


def format_plan_camping(data: dict, *, x: int | None, y: int | None, campers: str = "", day_arg: int = 0,
                        until_day: int = 0, ap: int = -1, defense_items: int = 0, camp_items: int = 0,
                        steaks: int = -1, slots: int = 5, camp_level: int = -1, hidden_before: int = 0,
                        objective: str = "expected", record: bool = True, nearby: bool = False,
                        town_id: int | None = None) -> str:
    if data.get("error"):
        return f"Error: {data['error']}"
    ovs = parse_group(campers)
    if isinstance(ovs, str):
        return ovs
    night = resolve_night(data, day_arg)
    if isinstance(night, str):
        return night
    one_night = not until_day or until_day == night["target"]
    group = dict(x=x, y=y, group=campers, day_arg=day_arg, ap=ap, defense_items=defense_items,
                 camp_items=camp_items, steaks=steaks, slots=slots, camp_level=camp_level,
                 hidden_before=hidden_before, objective=objective, until_day=until_day, town_id=town_id,
                 nearby=nearby)
    if any(not ov["name"] for ov in ovs) and len(ovs) > 1:
        return "Error: a camper without a name (':R4:n1') works only alone: give the citizens' names."
    single = None
    if one_night and len(ovs) == 1 and set(ovs[0]) <= _SINGLE_KEYS and ovs[0].get("tomb", True):
        single = ovs[0]
    elif one_night and not ovs:
        cell = (x, y) if x is not None and y is not None else None
        cell, names = _plan_campers(data, cell, night)
        if cell is not None and len(names) <= 1:
            x, y = cell
            single = {"name": names[0] if names else ""}   # the plan's only camper, or anyone
    elif not ovs and x is not None and y is not None and not _plan_campers(data, (x, y), night)[1]:
        group["group"] = ":"   # several nights, nobody planned there: one camper, "anyone"
    if single is None:
        return format_group_camping(data, **group)
    return format_camping_odds(
        data, x=x, y=y, citizen=single["name"], skill=single.get("skill", "none"),
        camp_level=camp_level, ap=None if ap < 0 else ap, defense_items=defense_items,
        camp_items=single.get("items", 0) + camp_items, hidden_before=hidden_before,
        nights=single.get("nights", -1), tomb=single.get("tomb", False), vest=single.get("vest"),
        record=record, town_id=town_id, day_arg=day_arg)
