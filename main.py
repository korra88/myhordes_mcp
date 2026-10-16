import asyncio
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from myhordes_mcp import fata, gesthordes  # noqa: E402
from myhordes_mcp.fata import supplies  # noqa: E402
from myhordes_mcp.fata.pathing import route_risks, safest_route  # noqa: E402
from myhordes_mcp.knowledgebase import curated, wiki  # noqa: E402
from myhordes_mcp.utils.clock import data_updated  # noqa: E402
from myhordes_mcp.utils.config import CURRENT_TOWN_FILE, FATAMORGANA_TOWN_ID, resolve_town_id  # noqa: E402

# IMPORTANT: MyHordes rules prohibit automated/scheduled API polling.
# All API calls must be triggered by explicit user queries via MCP tools.
# Never add cron jobs, background refresh, or periodic data fetching.
# See: docs/game-rules-for-external-apps.md

mcp = FastMCP("MyHordes Advisor")

if not FATAMORGANA_TOWN_ID and not CURRENT_TOWN_FILE.exists():
    print("Warning: no default town (towns/_current_town or FATAMORGANA_TOWN_ID).", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Fata Morgana tools — live town data from community-maintained spy service
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_bank_inventory(day: int = 0, town_id: int = 0, detail: str = "summary") -> str:
    """
    Fetches the current bank inventory of the MyHordes town.
    The default 'summary' is the right choice for almost every question —
    "do we have water/food/weapons?", "what's in the bank?", build planning.
    It groups items by strategic priority (water, food by AP, drugs, defense
    items, key resources, weapons) with totals per group.
    Use detail='full' ONLY when the user explicitly asks for the complete
    raw item list — it is very long and rarely needed.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
        detail: 'summary' (default, almost always correct) or 'full'
                (complete item list — only on explicit user request).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid, day=day or None)
    if detail == "full":
        return fata.format_bank(data)
    return fata.format_bank_summary(data)


@mcp.tool()
async def get_town_overview(day: int = 0, town_id: int = 0, detail: str = "compact") -> str:
    """
    One-call town status snapshot: day, gate, defense total, attack estimate,
    water supply, citizen positions, deaths count, bank size.
    Use this single tool for "how is the town", "status", "overview" questions —
    the default 'compact' answer is complete for those. Do NOT also call
    get_bank_inventory, get_defense_status or get_citizen_positions unless the
    user asks specifically about bank contents, defense breakdown or deaths.
    Data is crowd-sourced by players and may lag behind real-time game state.

    Args:
        day: Specific day number to inspect (e.g. 5 for day 5). Use 0 or omit for
             the current/latest day. Useful for comparing town progress over time.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
        detail: 'compact' (default, almost always correct) — condensed citizen
                roster, deaths count and bank size only.
                'full' — every citizen on its own line plus the complete bank
                item list and death log; only on explicit user request.
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid, day=day or None)
    # Enrich with season points from Gest'Hordes (current day only)
    season_points = None
    if not (day and day != data.get("meta", {}).get("day")):
        gh_data = await gesthordes.fetch_stats(tid)
        season_points = gesthordes.extract_season_points(gh_data)
    return fata.format_town_overview(data, season_points=season_points, detail=detail)


@mcp.tool()
async def get_citizen_positions(day: int = 0, town_id: int = 0) -> str:
    """
    Fetches citizen positions from Fata Morgana — who is inside the town,
    who is outside (and where), and the list of dead citizens with cause of death.
    Each citizen shows their last known CP (Control Points) when one was read.
    Use this when the user asks who is outside, who is camping, or about deaths.
    For a CP table of the whole town use get_citizen_cp instead.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid, day=day or None)
    return fata.format_citizens(data, fata.load_cp_log(tid))


@mcp.tool()
async def get_citizen_cp(town_id: int = 0) -> str:
    """
    Control Points (CP) of every living citizen: last value seen and best value
    seen, with day and zone. Use this when the user asks how many CP someone
    has, who can hold a zone, or to compose an expedition party.

    CP comes from the zone CP Fata reports (game data, items and status
    included), read when a citizen stood alone on a zone. CP drops with status
    (drugs -1 permanent; drunk -1, thirsty -1, guardian without shield -2
    temporary), so last < max means a malus. Citizens never seen alone on a
    zone show '?': count them as 2 CP. Readings accumulate only when tools
    fetch the town, so the log fills up as the town is checked.

    Args:
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid)
    if data.get("error"):
        return f"Error: {data['error']}"
    meta = data["meta"]
    lines = [f"## Citizen CP — {meta.get('town_name')} Day {meta.get('day')}",
             data_updated(meta),
             "Last = most recent reading, Max = best ever seen. ? = never read alone on a zone (assume 2).", ""]
    lines += fata.format_cp_log(fata.load_cp_log(tid), data["citizens"])
    return "\n".join(lines)


@mcp.tool()
async def get_defense_status(day: int = 0, town_id: int = 0) -> str:
    """
    Fetches the town defense breakdown and attack estimations from Fata Morgana,
    enriched with Gest'Hordes per-source detail for the current day.
    Includes: total defense, per-source breakdown (wall, buildings, items, guardians,
    homes, watchmen, temporary bonuses, dead-citizen bonus), item multiplier,
    tonight's and tomorrow's zombie estimates, and a survival assessment.
    Use this when the user asks about defense, attack survival, or zombie estimates.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid, day=day or None)
    # Enrich current-day defense with Gest'Hordes breakdown (watchmen, temps, dead bonus)
    gh_defense = None
    if not (day and day != data.get("meta", {}).get("day")):
        gh_data = await gesthordes.fetch_stats(tid)
        gh_defense = gesthordes.extract_current_defense(gh_data)
    return fata.format_defense(data, gh_defense=gh_defense)


@mcp.tool()
async def get_buildings(
    day: int = 0,
    town_id: int = 0,
    mode: str = "summary",
    include_private_town_buildings: bool = False,
    include_resources: bool = False,
) -> str:
    """
    Fetches the town's building list from Fata Morgana.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
        mode: Output mode — one of:
            "summary"   (default) Buildings constructed today only, plus running defense total.
                        Use when asked what was built today or current defense from buildings.
            "history"   All built buildings grouped by construction day.
                        Use when asked what was built on past days or full construction history.
            "available" Buildable unbuilt buildings (unlocked or prereq-only locked).
                        Blueprint-locked buildings are excluded — not actionable without the blueprint.
                        Use when asked what to build next, what's available, or build planning.
        include_private_town_buildings: Include buildings only available in private/custom towns
            (Holy Raincloud, Spirit Mirage, Sword of Bokor, XXL Voodoo Doll). Default False.
        include_resources: Include resource requirements for each building. Only useful with
            mode='available'. Use True for build planning when you need to check bank stock.
            Default False to keep output compact.
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid, day=day or None)
    return fata.format_buildings(data, mode=mode, include_private=include_private_town_buildings, include_resources=include_resources)


@mcp.tool()
async def get_build_options(town_id: int = 0, include_resources: bool = False) -> str:
    """
    Ranked construction options for today, computed from live buildings and bank.
    Use this for "what should we build", build plans and construction queues —
    it replaces get_buildings(mode='available') plus bank/defense lookups for that job.
    Returns the situation (defense vs tonight's estimate and buffer, water rations
    per citizen, town AP budget, Defensive Focus multiplier gap) and every buildable
    building grouped as water producers / permanent defense / temporary defense /
    utility, each with AP, defense, def/AP, def/water, def/nuts-and-bolts, and
    whether the bank holds its resources (✓ ready, or ⚠ short with have/need).
    Also lists locked defense/water buildings whose prerequisite is buildable now.
    You decide the order and explain trade-offs; do not recompute these numbers.

    Args:
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
        include_resources: Also list every resource each building needs. Default
            False — shortages are already shown; enable only when the user asks
            for full resource lists.
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid)
    return fata.format_build_options(data, include_resources=include_resources)


@mcp.tool()
async def get_construction_history(town_id: int = 0) -> str:
    """
    Day-by-day construction throughput: paid builds with AP cost, AP spent vs
    town budget (18 AP x citizens alive at day start), share used, citizens alive,
    the night's attack (Gest'Hordes) and deaths, plus free vote upgrades.
    Use for building reports, "how much AP did we spend", build history questions.
    One call is enough; do not also call get_buildings or get_attack_forecast for this.

    Args:
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data, gh = await asyncio.gather(fata.fetch_town_data(tid), gesthordes.fetch_stats(tid))
    return fata.format_construction_history(data, gh)


@mcp.tool()
async def get_town_changes(town_id: int = 0, since: str = "") -> str:
    """
    What changed in town since an earlier moment today: citizen movements with
    AP cost, bank deposits/withdrawals (critical items first), new constructions,
    defense/alive/gate deltas, AP each citizen spent moving today, and warnings
    (possibly trapped citizens, gate open late, citizens on depleted zones).
    Computed in code from snapshots stored on every live data fetch.
    Use for "what happened", "who moved", town snapshots and inspect-town.
    AP figures are lower bounds: moves between two snapshots count as a straight line.

    Args:
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
        since: "" (default) = since the previous get_town_changes call today, and
               moves that marker forward; "day" = since the first snapshot today;
               "HH:MM" = since that game time (French time). Only the default
               moves the marker.
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    return await fata.get_town_changes(tid, since=since)


@mcp.tool()
async def get_night_report(day: int = 0, town_id: int = 0) -> str:
    """
    What the attack at the end of a past day did: survived or failed, defense vs
    actual attack (and the estimate), alive before and after, and each death with
    cause and last position (outside = camping or stranded). Use for close-day,
    "what happened last night", "who died". One call per night.

    Args:
        day: The game day whose night to report (its attack happened at that day's
             end). 0 or omit = yesterday.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data, gh = await asyncio.gather(fata.fetch_town_data(tid), gesthordes.fetch_stats(tid))
    if data.get("error"):
        return f"Error: {data['error']}"
    target = day or (data["meta"].get("day") or 1) - 1
    if target < 1:
        return "The town is on day 1: no night has passed yet."
    day_data = await fata.fetch_town_data(tid, day=target)
    return fata.format_night_report(data, target, gh, day_data)


@mcp.tool()
async def get_expedition_roster(listed: str = "", town_id: int = 0) -> str:
    """
    Who is outside, grouped by exact tile (with ruin names), with Manhattan distance,
    forum class icons, and scrappers (distance 1) counted apart. With `listed`, also
    reconciles an expedition list: unaccounted citizens (outside, distance ≥2, on no
    list), listed names not outside (in town / dead / unknown), and the equation
    listed + scrappers + unaccounted = outside. Use for expedition-report.
    Items carried (bikes, kits) are not visible.

    Args:
        listed: Names on the user's expedition list, comma- or newline-separated.
                "@Name:12345" handles are accepted. Empty = no reconciliation.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    return fata.format_roster(await fata.fetch_town_data(tid), listed)


@mcp.tool()
async def map_bank_to_dump_sheet(sheet_items: str, town_id: int = 0) -> str:
    """
    Map the live bank onto a Garbage Dump spreadsheet's item rows, for the
    update-garbage-dump-list skill. Applies the agreed rules: broken items count,
    Plastic Bag → Water Bomb, emptied weapons fold into their loaded row, truncated
    sheet names match the unique bank name they prefix ("(incomplete)" items never).
    Returns one value per row in order (ready for the column write), decisions to
    confirm, and bank items with no row grouped by category.

    Args:
        sheet_items: Column B of the sheet's item rows, one name per line, in row
                     order (keep blank rows as empty lines so positions line up).
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    return fata.format_dump_mapping(await fata.fetch_town_data(tid), sheet_items)


@mcp.tool()
async def get_scout_map(
    day: int = 0,
    town_id: int = 0,
) -> str:
    """
    Fetches zombie counts per zone from scout data (Fata Morgana).
    Shows which zones have been scouted, how many zombies were spotted,
    and who scouted them. Zones are grouped by threat level.
    Use this when the user asks about zombie positions, safe scavenging routes,
    or where the horde is concentrated.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid, day=day or None)
    return fata.format_scout(data)


@mcp.tool()
async def find_expedition_path(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    group_cp: int = 0,
    party: str = "",
    escape_items: int = 0,
    scout_mode: bool = False,
    step_table: bool = False,
    round_trip: bool = False,
    start_ap: int = 6,
    start_ep: int = 0,
    thirst_counter: int = 0,
    day: int = 0,
    town_id: int = 0,
) -> str:
    """
    Runs CP-aware Dijkstra pathfinding between two map coordinates.
    Returns up to two paths:
    - Safest path: minimises zombie exposure, avoids traps entirely.
    - Shortest path: minimises AP, using escape items to pass through traps.
    Hard cap: 40 AP.
    Use this when planning an expedition route between two points.

    Args:
        x1: X coordinate of the starting point (town-relative).
        y1: Y coordinate of the starting point.
        x2: X coordinate of the destination.
        y2: Y coordinate of the destination.
        group_cp: Total Control Points of the expedition party. Leave 0 to
                  compute it from `party` (or 2 = solo citizen without party).
                  Set it only when the user states the party's CP.
                  Zones with zombies > group_cp are flagged as trap risk.
        party: Comma-separated citizen names of the expedition party, e.g.
               "Alice, Bob". Their CP comes from the town's CP log (last value
               seen; 2 for citizens never read). Prefer this over guessing group_cp.
        escape_items: Number of flash-grenade-equivalent escape items carried.
                      Default 0. Each can neutralize one trapped zone on the
                      shortest path.
        scout_mode: Set True when a Scout with Camouflage Vest is leading.
                    Trapped zones become passable at a detection risk cost
                    instead of being impassable.
        step_table: Set True when planning an actual trip. Adds a step-by-step
                    table for the first path: AP or EP paid per move (EP is used
                    first when leaving a zone 3+ km from town), AP/EP left, thirst
                    counter and status (Thirsty at 11, Dehydrated at 22, death at
                    33). No consumables are applied: for where to drink, eat
                    and take drugs, and what to carry, use plan_expedition_supplies.
        round_trip: With step_table, continue the table back along the same path.
        start_ap: AP at departure (default 6).
        start_ep: EP at departure (Scout 2, shoes +1, bike +2; default 0).
        thirst_counter: Zones already walked since the last water ration.
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid, day=day or None)
    breakdown = None
    if not group_cp:
        group_cp = 2
        if party and not data.get("error"):
            group_cp, breakdown = fata.party_cp(fata.load_cp_log(tid), data["citizens"], party.split(","))
    return fata.find_safe_path(
        data, x1, y1, x2, y2,
        group_cp=group_cp,
        cp_breakdown=breakdown,
        escape_items=escape_items,
        scout_mode=scout_mode,
        step_table=step_table,
        round_trip=round_trip,
        start_ap=start_ap,
        start_ep=start_ep,
        thirst_counter=thirst_counter,
    )


@mcp.tool()
async def plan_expedition_supplies(
    waypoints: str,
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
    free_slots: int = 0,
    step_table: bool = False,
    group_cp: int = 0,
    party: str = "",
    town_id: int = 0,
) -> str:
    """
    Plans when to drink, eat and use drugs along an expedition route, and what to carry.
    Use this whenever a trip needs water/food/drugs: do NOT place consumables yourself —
    report this tool's plan. It applies the game's rules exactly (verified in the game code):
    water and food give AP only once a day and only raise AP to the max (never add), so they
    are used at 0 AP; a second drink while not thirsty is refused by the game; walking 11
    zones makes you Thirsty, 22 Dehydrated, 33 dead, and only water resets that counter;
    EP is spent first when leaving a zone 3+ km from town.

    The route is the safest path (as find_expedition_path) from `start` through the
    waypoints, back to `start` if round_trip. Returning to town uses the Observation
    Platform teleport when built (level 3-4) and accounts for the Labyrinth's 1 AP.
    The plan minimises, in order: death, running out of AP, ending Dehydrated, ending
    Thirsty, items carried (slots), alcohol, drugs, AP wasted. At most one drug and one
    alcohol (warned about). Output: items to bring with slot count, warnings, route risks
    (zones where the group may get blocked: zombies above its CP, or never scouted — each
    with the extra AP to go around it or the zombies to kill), and the key steps (where to
    eat/drink, thirst changes, risky zones, arrival); step_table=True for every move.
    Report the risks as given: do not invent a different route.

    Defaults: 6 AP, no scout, no shoes, no bike, no Scout's Lair, nothing drunk or eaten
    yet, carrying water and one 7 AP food. Every extra must be declared by the player.
    When the player didn't say, state these assumptions in your answer (one line) so they
    can correct them. If the plan needs drugs or alcohol it reports them as "extra needed"
    (one 6 AP extra = steroids or alcohol, either; two extras or a Twinoid are named).

    Args:
        waypoints: Zones to visit in order, town-relative, e.g. "-7,5" or "-7,5; -3,8".
        round_trip: Come back to `start` (default True).
        start: Starting zone, default "0,0" (town).
        start_ap: AP at departure (default 6; 7 after a lucky dice/cards roll, 5 if wounded).
        start_ep: EP at departure. -1 = full: scout 2 + shoes 1 + bike 2. With the Scout's
                  Lair bonus pass the real EP (e.g. scout 6).
        scout / shoes / bike: Scout job, Worn-out Sports Shoes, Mountain Bike equipped.
        thirst_counter: Zones already walked since the last drink (0-10).
        thirst: Current status: "none", "thirsty" or "dehydrated".
        already_drank / already_ate: Water / food already used today (no more AP from them).
        drug_taken_today: A drug was already taken today (no drug in the plan).
        drunk_or_hungover: No alcohol in the plan.
        wounded: Max AP 5 instead of 6.
        available: What the player has or can take, e.g. "water=2, food7=1, twinoid=1"
                   (names: water, food6, food7, alcohol, steroid, twinoid, coffee). Empty =
                   up to 3 water and one 7 AP food, plus extras (one drug, one alcohol)
                   only when needed; it reports the minimum to carry.
        free_slots: Free rucksack slots for consumables; 0 = no limit (the plan reports how
                    many it needs).
        step_table: Add the full move-by-move table (long: only when asked for it).
        group_cp / party: For route safety, as in find_expedition_path.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    points = []
    for raw in [start] + waypoints.replace("|", ",").split(";"):
        nums = raw.replace("|", ",").replace("[", "").replace("]", "").replace("/", ",").split(",")
        try:
            x, y = (int(n) for n in nums)
        except ValueError:
            return f"Error: can't read the zone '{raw.strip()}' (use 'x,y', e.g. '-7,5')."
        points.append((x, y))
    if len(points) < 2:
        return "Error: give at least one waypoint."
    if round_trip:
        points.append(points[0])
    level = {"none": 0, "ok": 0, "thirsty": 1, "dehydrated": 2}.get(thirst.strip().lower())
    if level is None:
        return "Error: thirst must be 'none', 'thirsty' or 'dehydrated'."
    items = supplies.parse_available(available)
    if isinstance(items, str):
        return f"Error: {items}"

    data = await fata.fetch_town_data(tid)
    if data.get("error"):
        return f"Error: {data['error']}"
    breakdown = None
    if not group_cp:
        group_cp = 2
        if party:
            group_cp, breakdown = fata.party_cp(fata.load_cp_log(tid), data["citizens"], party.split(","))
    route = safest_route(data, points, group_cp)
    if route is None:
        return "Error: no route found between the given zones (40 AP cap per leg)."
    route, end_ap, note = supplies.end_requirements(data, route, points[-1])
    risks = route_risks(data, route, points, group_cp)
    st = supplies.Start(
        ap=start_ap, ep=None if start_ep < 0 else start_ep, counter=thirst_counter, thirst=level,
        drank=already_drank, ate=already_ate, drugged=drug_taken_today,
        no_alcohol=drunk_or_hungover, wounded=wounded, scout=scout, shoes=shoes, bike=bike,
    )
    result = supplies.plan(route, st, items, end_ap=end_ap, slots=free_slots)
    path = " → ".join(f"[{x}|{y}]" for x, y in points)
    notes = [data_updated(data["meta"]), note, f"Route safety computed for {group_cp} CP." + (" " + "; ".join(breakdown) if breakdown else "")]
    if not available.strip():
        notes.append("Assumed: water and one 7 AP food; drugs/alcohol only as extras if needed.")
    if result["cost"][0] or result["cost"][1]:
        # Not feasible: what would make it work (default items, no slot limit)?
        more = {k: max(items.get(k, 0), n) for k, n in supplies.DEFAULT_AVAILABLE.items()}
        alt = supplies.plan(route, st, more, end_ap=end_ap)
        if not (alt["cost"][0] or alt["cost"][1]):
            need = ", ".join(f"{n} × {supplies.ITEMS[k].label}" for k, n in alt["used"].items())
            notes.append(f"Feasible with: {need} ({sum(alt['used'].values())} slots).")
        else:
            notes.append("Not feasible even with the default set of items: shorten the route.")
    return supplies.format_plan(route, st, result, title=f"Supplies plan {path}", notes=notes,
                                slots=free_slots, end_ap=end_ap, step_table=step_table,
                                teleport="teleport" in note, generic_extras=not available.strip(),
                                risks=risks, cp=group_cp)


@mcp.tool()
async def get_zone_details(
    day: int = 0,
    town_id: int = 0,
    x1: int | None = None,
    y1: int | None = None,
    x2: int | None = None,
    y2: int | None = None,
    max_ap: int | None = None,
) -> str:
    """
    Fetches detailed map zone data from Fata Morgana — ruins (with names, dig
    counts, blueprint status), ground items per zone, and zombie counts.
    Use this when the user asks about ruins, what items are on the ground outside,
    or what's available at specific map coordinates.

    Without coordinates: returns only zones that have a ruin or ground items
    (empty zones are omitted, count noted).
    When x1/y1/x2/y2 are provided, restricts output to the bounding box between
    those two coordinates, sorted by AP cost (Manhattan distance from town).
    Zones with nothing to report (no ruin, no items, no threat) are collapsed
    into one-line coordinate lists — the output stays compact for large areas,
    so prefer one call with a generous box over many small calls.
    Use this for expedition planning: "what's between [2|3] and [5|6] within 8 AP?"

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
        x1: X coordinate of the first corner of the area to inspect (town-relative).
        y1: Y coordinate of the first corner of the area to inspect (town-relative).
        x2: X coordinate of the second corner. Required if x1/y1 are set.
        y2: Y coordinate of the second corner. Required if x1/y1 are set.
        max_ap: Optional AP budget to filter results (e.g. 8). Cells beyond this cost
                are shown separately. Typical range: 4–15.
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid, day=day or None)

    coords_provided = all(v is not None for v in (x1, y1, x2, y2))
    if coords_provided:
        return fata.format_zone_path(data, x1, y1, x2, y2, max_ap=max_ap)
    return fata.format_zones(data)


# ---------------------------------------------------------------------------
# Gest'Hordes tools — public attack/defence statistics
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_attack_distribution(town_id: int = 0) -> str:
    """
    Fetches historical attack distribution statistics from Gest'Hordes — real attack
    values sampled across all towns per day, showing median, percentiles (p25/p75),
    min/max, and sample count alongside the theoretical floor and ceiling.
    Use this when the user wants to understand how bad the attack typically gets at
    a given day level, or whether tonight's estimate is unusually high or normal.

    Args:
        town_id: Gest'Hordes map ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await gesthordes.fetch_stats(tid)
    return gesthordes.format_attack_distribution(data)


@mcp.tool()
async def get_attack_forecast(town_id: int = 0) -> str:
    """
    Fetches the theoretical attack curve and defence history from Gest'Hordes.
    Shows the theoretical min/max zombie attack range for each day of the game,
    actual attack counts from previous nights, Gest'Hordes community estimates,
    and defence totals with per-source breakdown (buildings, items, homes, guardians).
    Use this when the user asks about tonight's expected attack, how the attack
    scales over the game, or wants to compare defence vs. projected zombie counts.

    Args:
        town_id: Gest'Hordes map ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await gesthordes.fetch_stats(tid)
    return gesthordes.format_attack_forecast(data)


# Official MyHordes API tools are disabled — see src/myhordes_mcp/myhordes/official_api.py.


# ---------------------------------------------------------------------------
# Wiki tools (scraped from en.mhwiki.org)
# ---------------------------------------------------------------------------

@mcp.tool()
def search_wiki(query: str, category: str = "", limit: int = 5) -> str:
    """
    Search the MyHordes wiki for game information.
    Use for items, buildings, ruins, skills, statuses, distinctions, jobs, deaths,
    mechanics, and strategy guides sourced from en.mhwiki.org.

    Args:
        query: Search terms (e.g. "Twisted Plank", "camping", "water ration poisoned")
        category: Optional filter — one of: items, buildings, ruins, skills, status,
                  distinctions, deaths, homes, jobs, guide, general, town, events, tutorials.
                  Leave empty to search all categories.
        limit: Max results to return (1-10, default 5). Use 1-2 for specific lookups,
               higher for broad searches.
    """
    return wiki.format_search(query, category=category, limit=limit)


@mcp.tool()
def list_wiki_categories() -> str:
    """
    List all categories in the MyHordes wiki with page counts.
    Use this to discover what wiki information is available before searching.
    """
    return wiki.format_categories()


# ---------------------------------------------------------------------------
# Knowledge tools (curated advisor knowledge base)
# ---------------------------------------------------------------------------

@mcp.tool()
def search_knowledge(query: str, section: str = "") -> str:
    """
    Search the advisor's curated knowledge base for strategy, mechanics, building
    guides and tactical notes not found in the wiki. Content lives in knowledge/.

    Use for: expedition planning (AP/EP, thirst step counter, consumable order),
    building priority by game phase, opti-town tactics, wonders, player meta.

    Args:
        query: Search terms (e.g. "thirst step counter", "day 5 buildings",
            "restore to max", "exploration points").
        section: Optional subfolder filter. Valid sections:
            "buildings" — AP costs, defense values, build priority by phase, wonders.
            "tactics"   — expedition planning, game mechanics, strategy, meta.
            Leave empty to search all sections.
    """
    return curated.search(query, section=section)


if __name__ == "__main__":
    # Run the MCP server using standard input/output
    mcp.run()
