"""plan_expedition_supplies: when to drink, eat and use drugs along an expedition route,
and what to carry. The tool declaration (and its docstring, which the bot reads) is in main.py."""

from ..utils.fmt import plural
from . import pickups as pick_mod, supplies
from .bank import expedition_extras
from .client import fetch_town_data
from .cp import resolve_group_cp
from .geo import MAX_PATH_AP, fmt_xy
from .pathing import dig_weight, loop_return, route_risks, safest_route
from ..utils.clock import data_updated


def parse_zones(raws: list[str]) -> list[tuple[int, int]] | str:
    """Town-relative zones from "x,y" texts ("[-7|5]" and "-7/5" work too), or an error text."""
    zones = []
    for raw in raws:
        nums = raw.replace("|", ",").replace("[", "").replace("]", "").replace("/", ",").split(",")
        try:
            x, y = (int(n) for n in nums)
        except ValueError:
            return f"Error: can't read the zone '{raw.strip()}' (use 'x,y', e.g. '-7,5')."
        zones.append((x, y))
    return zones


def walked_again(route: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Zones a route enters more than once (town aside), in order."""
    seen, again = set(), []
    for c in route:
        if c in seen and c != (0, 0) and c not in again:
            again.append(c)
        seen.add(c)
    return again


def day_budget_error(start_ap: int) -> str | None:
    """An error when start_ap is a player's day budget ("19 AP"), not AP at departure."""
    # Twinoid 8 + coffee 4 is the most anyone leaves with.
    if start_ap <= 12:
        return None
    return (f"Error: start_ap={start_ap} is not AP at departure (12 at most). A player's "
            "'N AP' is the day's budget with food and water included: 18 = start_ap=6, "
            "available='water=1, food6=1'; 19 = 'water=1, food7=1'; 20/21 = the same with "
            "scout=True; 24 = add 'steroid=1'. Plan again with start_ap=6.")



def _rucksack_line(result: dict, rows: list[dict], slots: int) -> str:
    """"Does not fit in the rucksack" when the supplies at departure, or the supplies still to
    use plus the items picked up, need more than `slots` (the worst moment is named)."""
    need = supplies.carried(result["used"])
    peak, what = need, f"supplies {need}"
    for r in rows:
        if r["used"] > peak:
            peak = r["used"]
            what = (f"at {fmt_xy(r['pickup'].zone)}: {pick_mod._supplies(r['supplies'])} still to use + "
                    f"{r['picked']} picked up")
    if peak <= slots:
        return ""
    return (f"**Does not fit in the rucksack:** {what} = {plural(peak, 'slot')}, {slots} free: {peak - slots} short. "
            "Bring a bag (more slots), pick up less, or split the route into trips.")


async def plan_supplies(
    tid: int,
    waypoints: str,
    *,
    round_trip: bool = True,
    start: str = "0,0",
    start_ap: int = 6,
    start_ep: int = -1,
    scout: bool = False,
    shoes: bool = False,
    bike: bool = False,
    thirst_counter: int = 0,
    thirst: str = "none",
    already_drank: bool = False,
    already_ate: bool = False,
    drug_taken_today: bool = False,
    drunk_or_hungover: bool = False,
    wounded: bool = False,
    available: str = "",
    slots: int = 5,
    pickups: str = "",
    trolley: bool = False,
    guardian: bool = False,
    step_table: bool = False,
    group_cp: int = -1,
    party: str = "",
    second_wind: int = 0,
    dig: bool = False,
) -> str:
    """The whole answer of the plan_expedition_supplies tool (arguments as documented
    there). Validates first, then fetches the town `tid`."""
    points = parse_zones([start] + waypoints.split(";"))
    if isinstance(points, str):
        return points
    if len(points) < 2:
        return "Error: give at least one waypoint."
    wanted = set(points[1:])
    if round_trip:
        points.append(points[0])
    # "0,0; 14,2; 0,0" with the default start and round_trip would repeat the town.
    points = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
    if len(points) < 2:
        return "Error: give at least one waypoint other than the start."
    level = {"none": 0, "ok": 0, "thirsty": 1, "dehydrated": 2}.get(thirst.strip().lower())
    if level is None:
        return "Error: thirst must be 'none', 'thirsty' or 'dehydrated'."
    parsed = supplies.parse_supplies(available, second_wind)
    if isinstance(parsed, str):
        return parsed
    items, sw_ap, sw_ep = parsed
    if slots < 1:
        return supplies.SLOTS_ERROR
    if err := day_budget_error(start_ap):
        return err
    entries = pick_mod.parse(pickups)
    if isinstance(entries, str):
        return entries
    zones = parse_zones([e[0] for e in entries])
    if isinstance(zones, str):
        return zones
    for (x, y), (_, what, _) in zip(zones, entries):
        if (x, y) not in wanted:
            return (f"Error: pickup '{what}' at {fmt_xy((x, y))}: that zone is not one of the waypoints. "
                    "Add it to waypoints too (the route only goes where the waypoints say).")

    data = await fetch_town_data(tid)
    if data.get("error"):
        return f"Error: {data['error']}"
    group_cp, breakdown = resolve_group_cp(data, tid, group_cp, party)
    picks = pick_mod.resolve(data, [(z, w, n) for z, (_, w, n) in zip(zones, entries)])
    if isinstance(picks, str):
        return picks
    for p in picks:
        p.wp = points.index(p.zone, 1)
    heavy = pick_mod.heavy_check(picks, bike=bike, trolley=trolley, guardian=guardian)
    if isinstance(heavy, str):
        return heavy
    # Per-leg CP: a Guardian carrying a 2nd heavy item has the shield lowered (-2 CP).
    cps = pick_mod.leg_cps(group_cp, len(points) - 1, heavy["drop_from"])
    # Legs after the first avoid zones already walked: their one dig of the day is used.
    avoid = len(points) >= 3
    rw = dig_weight(dig)
    leg = None
    if avoid and points[-1] == points[0]:
        # Round trip: the way back is a loop ending on the best Observation Platform
        # teleport zone, as find_expedition_path.
        out = safest_route(data, points[:-1], cps[:-1], avoid_revisits=True, revisit_weight=rw)
        back = loop_return(data, out, cps[-1], dig=dig) if out else None
        leg = supplies.home_leg(data, out, back) if back is not None else None
    if leg is None:
        route = safest_route(data, points, cps, avoid_revisits=avoid, revisit_weight=rw)
        if route is None:
            return f"Error: no route found between the given zones ({MAX_PATH_AP} AP cap per leg)."
        leg = supplies.home_leg(data, route)
    route, end_ap, note = leg.route, leg.end_ap, leg.note
    teleport = leg.teleport_from is not None
    risks = route_risks(data, route, points, cps, avoid_revisits=avoid, revisit_weight=rw)
    st = supplies.Start(
        ap=start_ap, ep=None if start_ep < 0 else start_ep, counter=thirst_counter, thirst=level,
        drank=already_drank, ate=already_ate, drugged=drug_taken_today,
        no_alcohol=drunk_or_hungover, wounded=wounded, scout=scout, shoes=shoes, bike=bike,
        sw_ap=sw_ap, sw_ep=sw_ep,
    )
    fitted = pick_mod.fit(route, points, picks, slots,
                          lambda n: supplies.plan(route, st, items, end_ap=end_ap, slots=n))
    result = fitted["result"]
    if avoid and dig:
        # Going over zones still to dig is worth it only when it costs no more supplies
        # (compare death, AP short, thirst and items carried) than the shortest routes;
        # among those, the one walking the fewest zones again.
        alt_route = safest_route(data, points, cps, avoid_revisits=True, revisit_weight=dig_weight(False))
        if alt_route is not None:
            alt_leg = supplies.home_leg(data, alt_route)
            alt_route, alt_end, alt_note = alt_leg.route, alt_leg.end_ap, alt_leg.note
            alt_fit = pick_mod.fit(alt_route, points, picks, slots,
                                   lambda n: supplies.plan(alt_route, st, items, end_ap=alt_end, slots=n))
            alt = alt_fit["result"]
            if alt["cost"][supplies.SUPPLY_KEY] < result["cost"][supplies.SUPPLY_KEY]:
                extra = (len(route) - 1) - (len(alt_route) - 1)
                why = ("not feasible with these supplies" if not supplies.feasible(result)
                       else "needs more supplies")
                route, end_ap, result, note, fitted = alt_route, alt_end, alt, alt_note, alt_fit
                teleport = alt_leg.teleport_from is not None
                risks = route_risks(data, route, points, cps, avoid_revisits=True,
                                    revisit_weight=dig_weight(False))
                note = (f"Going over zones still to dig would be {extra} AP longer and {why}. "
                        f"{note}").strip()
    if avoid:
        again = walked_again(route)
        if again:
            note = (f"Walks again (already dug today): {', '.join(fmt_xy(c) for c in again)}. "
                    f"{note}").strip()
    path = " → ".join(fmt_xy(c) for c in points)
    cp_label = None
    if heavy["drop_from"] is None:
        cp_text = f"Route safety computed for {group_cp} CP."
    else:
        low = max(0, group_cp - pick_mod.GUARDIAN_CP_LOSS)
        cause = heavy["at_pickup"]
        where = (f"from the start ({fmt_xy(points[0])})" if cause is None
                 else f"after the pickup at {fmt_xy(cause.zone)}")
        cp_text = (f"Route safety computed for {group_cp} CP, then {low} CP {where} "
                   f"(2nd heavy item: the Guardian lowers the shield).")
        cp_label = f"{group_cp} CP, {low} CP {where}"
    notes = [data_updated(data["meta"]), note, cp_text + (" " + "; ".join(breakdown) if breakdown else "")]
    if not available.strip():
        notes.append(supplies.ASSUMED_DEFAULT_NOTE)
    if slots == 5:
        notes.append("Assumed: 5 free slots.")
    lead, fits = [], ""
    if not supplies.feasible(result):
        # The items (or slots) given are not enough: plan again with every booster the route
        # needs, in any number of slots, and say so first. The rucksack is checked below.
        alt, added, swapped = supplies.with_boosters(route, st, items, end_ap)
        lead.append(supplies.not_feasible_line(route, result, available, added if alt else None, slots, swapped))
        if alt:
            rows = pick_mod.timeline(route, points, picks, alt, slots) if picks else []
            fitted = {"result": alt, "rows": rows, "departure_slots": slots,
                      "missing": max((r["over"] for r in rows), default=0)}
            result = alt
    if supplies.feasible(result):
        fits = _rucksack_line(result, fitted["rows"], slots)
        if fits:
            lead.append(fits)
    options = None
    if supplies.wants_extra_options(available, result):
        options = supplies.extra_options(route, st, items, end_ap=end_ap, slots=fitted["departure_slots"],
                                         stock=expedition_extras(data["bank"]))
    pick_verdict, pick_notes, extra_warn = "", None, [p.warning for p in picks if p.warning]
    if picks:
        if fitted["rows"]:
            pick_verdict = "" if fits else pick_mod.verdict(fitted, slots, heavy)
            pick_notes = pick_mod.pickup_lines(fitted, slots)
        else:
            pick_verdict = "Pickups not checked: the supplies plan is not feasible."
        if heavy["drop_from"] is not None:
            extra_warn.append("2 heavy items: the Guardian must lower the shield (-2 CP for the group "
                              "until the night raises it).")
    return supplies.format_plan(route, st, result, title=f"Supplies plan {path}", notes=notes,
                                slots=slots, end_ap=end_ap, step_table=step_table,
                                teleport=teleport, generic_extras=not available.strip(),
                                risks=risks, cp=group_cp, waypoints=points[1:-1], options=options,
                                pick_verdict=pick_verdict, pick_notes=pick_notes,
                                extra_warn=extra_warn, cp_label=cp_label, lead=lead)
