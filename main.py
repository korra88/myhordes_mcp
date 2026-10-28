import asyncio
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from myhordes_mcp import fata, gesthordes  # noqa: E402
from myhordes_mcp.fata import pickups as pick_mod, supplies  # noqa: E402
from myhordes_mcp.fata.pathing import loop_return, route_risks, safest_route  # noqa: E402
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
             "Last = most recent reading, Max = best ever seen.", ""]
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
    return fata.format_defense(data)


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
async def get_build_options(town_id: int = 0, include_resources: bool = False, include_all: bool = False) -> str:
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
        include_all: Show every option of each group. Default False — the best 8
            per group are shown and the rest named on one line; enable only when
            the user asks about one of those.
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid)
    return fata.format_build_options(data, include_resources=include_resources, include_all=include_all)


@mcp.tool()
async def get_blueprint_order(town_id: int = 0) -> str:
    """
    In which order to read the construction blueprints in the bank, and which
    not to read yet. Use when the user asks about blueprints: what to read,
    whether a ruin (Bunker/Hotel/Hospital) blueprint is worth reading, or why
    reading one unlocked nothing.

    Applies the game's rule: a blueprint unlocks a random locked building whose
    parent is unlocked; ruin blueprints draw from a small list per ruin and tier,
    normal ones from every building of their rarity, so a normal one can take a
    ruin building, and a ruin blueprint with nothing reachable is consumed for
    nothing. Returns the reading order with the odds, the blueprints to hold
    (with the parent they wait for), those that would be wasted, and what each
    explorable ruin on the map can still unlock. Report it; do not redo the odds.

    Args:
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    return fata.format_blueprint_order(await fata.fetch_town_data(tid))


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
    On the current day it also checks tonight's global respawn threshold
    (25 × the new day zombies on the whole map) against what Fata counts —
    use it for zombie-zoo questions; Fata never sees the whole map, and the
    output says what is not counted.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid, day=day or None)
    return fata.format_scout(data)


def _parse_zones(raws: list[str]) -> list[tuple[int, int]] | str:
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


@mcp.tool()
async def find_expedition_path(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    group_cp: int = -1,
    party: str = "",
    escape_items: int = 0,
    scout_mode: bool = False,
    step_table: bool = False,
    round_trip: bool = False,
    start_ap: int = 6,
    start_ep: int = 0,
    thirst_counter: int = 0,
    show_items: bool = False,
    waypoints: str = "",
    day: int = 0,
    town_id: int = 0,
) -> str:
    """
    Runs CP-aware Dijkstra pathfinding between two map coordinates, through waypoints if given.
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
        group_cp: Total Control Points of the expedition party. Omit (-1) to
                  compute it from `party` (or 2 = solo citizen without party).
                  Set it only when the user states the party's CP. 0 is valid:
                  a Terrorised citizen alone has 0 CP (any zombie traps them).
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
        show_items: Set True to list the ground items on each step (only when
                    the user wants to pick things up on the way).
        waypoints: Zones the route must pass through, in order, town-relative, e.g.
                   "-7,5" or "-7,5; -3,8". Legs after the first avoid zones already
                   walked (a zone can be dug once a day). Flash items are shared by
                   all legs. Omit for a direct route.
        step_table: Set True when planning an actual trip. Adds a step-by-step
                    table for the first path: AP or EP paid per move (EP is used
                    first when leaving a zone 3+ km from town), AP/EP left, thirst
                    counter and status (Thirsty at 11, Dehydrated at 22, death at
                    33). No consumables are applied: for where to drink, eat
                    and take drugs, and what to carry, use plan_expedition_supplies.
        round_trip: Also plan the way back, as a loop: over zones the way out
                    does not use (a zone can be dug once a day), and, when the
                    trip starts in town and the Observation Platform is level
                    3+, ending on the teleport zone cheapest to reach (off row 0 /
                    column 0, e.g. [2|1] at level 4). Gives the round-trip AP and
                    the AP saved. With step_table, the table covers both ways.
        start_ap: AP at departure (default 6).
        start_ep: EP at departure (Scout 2, shoes +1, bike +2; default 0).
        thirst_counter: Zones already walked since the last water ration.
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    wps = []
    if waypoints.strip():
        wps = _parse_zones(waypoints.split(";"))
        if isinstance(wps, str):
            return wps
    data = await fata.fetch_town_data(tid, day=day or None)
    breakdown = None
    if group_cp < 0:
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
        show_items=show_items,
        round_trip=round_trip,
        start_ap=start_ap,
        start_ep=start_ep,
        thirst_counter=thirst_counter,
        waypoints=wps,
    )


def _walked_again(route: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Zones a route enters more than once (town aside), in order."""
    seen, again = set(), []
    for c in route:
        if c in seen and c != (0, 0) and c not in again:
            again.append(c)
        seen.add(c)
    return again


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
    slots: int = 5,
    pickups: str = "",
    trolley: bool = False,
    guardian: bool = False,
    step_table: bool = False,
    group_cp: int = -1,
    party: str = "",
    second_wind: int = 0,
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
    waypoints, back to `start` if round_trip. Legs after the first avoid zones already
    walked (a zone can be dug once a day) unless that needs more supplies; a round trip
    from town with the Observation Platform level 3+ ends on the best teleport zone. The
    output names the zones walked again. Accounts for the Labyrinth's 1 AP.
    The plan minimises, in order: death, running out of AP, ending Dehydrated, ending
    Thirsty, items carried (slots), alcohol, drugs, premium items (Twinoid, 7 AP food),
    AP wasted. At most one drug and one alcohol (warned about). Output: items to bring
    with slot count, the other ways to cover drugs/alcohol with the bank stock, warnings,
    route risks (zones where the group may get blocked: zombies above its CP, or never
    scouted — each with the extra AP to go around it or the zombies to kill), and a
    numbered Itinerary in walking order (walks with turning points, what to use where,
    thirst changes, waypoints, risky zones, arrival); step_table=True for every move.
    Give the Itinerary as it is, and report the risks as given: do not invent a different
    route.

    Defaults: 6 AP, no scout, no shoes, no bike, no Scout's Lair, nothing drunk or eaten
    yet, carrying water and one 7 AP food, 5 free rucksack slots. Every extra must be
    declared by the player. When the player didn't say, state these assumptions in your
    answer (one line) so they can correct them.

    Goals on the way (a blueprint, defensive objects, any item): put the zone in BOTH
    `waypoints` and `pickups` — the route only goes where waypoints say, and the pickups
    are what makes the plan check the rucksack (supplies still to use + items picked up
    must fit the slots; supplies are never dropped to make room) and heavy items.
    Find the zones first (get_zone_details); do not guess slots or heavy items yourself.
    If the plan needs drugs or alcohol it reports them as "extra needed"
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
        slots: Free rucksack slots at departure (default 5 = base 4 + Enduring level 1,
               which heroes have). The player says their own ("I have 7 slots"): bags,
               trolley and Utility Belt are theirs to add up. Must be at least 1.
        pickups: Items to bring back, each at one of the waypoints: "14,2: blueprint;
                 -3,8: 2 defense". After the colon: an item name (part of it), `defense`
                 (defensive object or part) or `heavy`, with an optional count. Matched
                 against the zone's ground items (heavy / defense as Fata tags them); an
                 item Fata did not see there is kept as light, with a warning.
        trolley: A Shopping Trolley is carried (it is the one heavy item, like the bike).
        guardian: A Guardian may carry a 2nd heavy item with the shield lowered: the plan
                  warns, and the group CP is 2 lower on every leg after that pickup.
                  Without it, 2 heavy items (bike, trolley, heavy pickups) are refused.
        step_table: Add the full move-by-move table (long: only when asked for it).
        group_cp / party: For route safety, as in find_expedition_path.
        second_wind: The player's Enduring level as they say it, 1-4 (4 = Master); 0 = none
                     or keep the heroic action for something else (default). Level
                     1/2/3/4 = +3/+3/+4/+4 AP (up to max) and +1/+3/+4/+6 EP. The plan uses
                     it only when it helps, and warns that it is the day's one heroic
                     action (no Heroic Return that day). Pass it when the player said or
                     the bot memory holds their level.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    points = _parse_zones([start] + waypoints.split(";"))
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
    items = supplies.parse_available(available)
    if isinstance(items, str):
        return f"Error: {items}"
    sw_ap = sw_ep = 0
    if second_wind:
        if second_wind - 1 not in supplies.SECOND_WIND:
            return "Error: second_wind is the Enduring level, 1 to 4 (0 = none)."
        sw_ap, sw_ep = supplies.SECOND_WIND[second_wind - 1]
        items["secondwind"] = 1
    if slots < 1:
        return "Error: slots is the number of free rucksack slots at departure, at least 1."
    entries = pick_mod.parse(pickups)
    if isinstance(entries, str):
        return entries
    zones = _parse_zones([e[0] for e in entries])
    if isinstance(zones, str):
        return zones
    for (x, y), (_, what, _) in zip(zones, entries):
        if (x, y) not in wanted:
            return (f"Error: pickup '{what}' at [{x}|{y}]: that zone is not one of the waypoints. "
                    "Add it to waypoints too (the route only goes where the waypoints say).")

    data = await fata.fetch_town_data(tid)
    if data.get("error"):
        return f"Error: {data['error']}"
    breakdown = None
    if group_cp < 0:
        group_cp = 2
        if party:
            group_cp, breakdown = fata.party_cp(fata.load_cp_log(tid), data["citizens"], party.split(","))
    picks = pick_mod.resolve(data, [(z, w, n) for z, (_, w, n) in zip(zones, entries)])
    for p in picks:
        p.wp = points.index(p.zone, 1)
    heavy = pick_mod.heavy_check(picks, bike=bike, trolley=trolley, guardian=guardian)
    if isinstance(heavy, str):
        return heavy
    # Per-leg CP: a Guardian carrying a 2nd heavy item has the shield lowered (-2 CP).
    cps = pick_mod.leg_cps(group_cp, len(points) - 1, heavy["drop_from"])
    # Legs after the first avoid zones already walked: their one dig of the day is used.
    avoid = len(points) >= 3
    back = None
    if avoid and points[-1] == points[0]:
        # Round trip: the way back is a loop ending on the best Observation Platform
        # teleport zone, as find_expedition_path.
        out = safest_route(data, points[:-1], cps[:-1], avoid_revisits=True)
        back = loop_return(data, out, cps[-1]) if out else None
    if back is not None:
        route = out + back["route"][1:]
        note = ""
        if back["teleport_from"]:
            tx, ty = back["teleport_from"]
            end_ap = 0
            note = (f"Observation Platform level {back['level']}: teleport home from [{tx}|{ty}] "
                    f"({back['saved_ap']} AP saved; needs the gate open).")
        else:
            route, end_ap, note = supplies.end_requirements(data, route, points[-1])
    else:
        route = safest_route(data, points, cps, avoid_revisits=avoid)
        if route is None:
            return "Error: no route found between the given zones (40 AP cap per leg)."
        route, end_ap, note = supplies.end_requirements(data, route, points[-1])
    risks = route_risks(data, route, points, cps, avoid_revisits=avoid)
    st = supplies.Start(
        ap=start_ap, ep=None if start_ep < 0 else start_ep, counter=thirst_counter, thirst=level,
        drank=already_drank, ate=already_ate, drugged=drug_taken_today,
        no_alcohol=drunk_or_hungover, wounded=wounded, scout=scout, shoes=shoes, bike=bike,
        sw_ap=sw_ap, sw_ep=sw_ep,
    )
    fitted = pick_mod.fit(route, points, picks, slots,
                          lambda n: supplies.plan(route, st, items, end_ap=end_ap, slots=n))
    result = fitted["result"]
    if avoid:
        # Avoiding zones already walked is worth it only when it costs no more supplies
        # (compare death, AP short, thirst and items carried) than the shortest routes;
        # among those, the one walking the fewest zones again.
        alt_route = safest_route(data, points, cps, avoid_revisits=True, revisit_weight=0.01)
        if alt_route is not None:
            alt_route, alt_end, alt_note = supplies.end_requirements(data, alt_route, points[-1])
            alt_fit = pick_mod.fit(alt_route, points, picks, slots,
                                   lambda n: supplies.plan(alt_route, st, items, end_ap=alt_end, slots=n))
            alt = alt_fit["result"]
            if alt["cost"][:6] < result["cost"][:6]:
                extra = (len(route) - 1) - (len(alt_route) - 1)
                why = ("not feasible with these supplies" if result["cost"][0] or result["cost"][1]
                       else "needs more supplies")
                route, end_ap, result, note, fitted = alt_route, alt_end, alt, alt_note, alt_fit
                risks = route_risks(data, route, points, cps, avoid_revisits=True)
                note = (f"Avoiding zones already walked would be {extra} AP longer and {why}. "
                        f"{note}").strip()
        again = _walked_again(route)
        if again:
            note = (f"Walks again (already dug today): {', '.join(f'[{x}|{y}]' for x, y in again)}. "
                    f"{note}").strip()
    path = " → ".join(f"[{x}|{y}]" for x, y in points)
    cp_label = None
    if heavy["drop_from"] is None:
        cp_text = f"Route safety computed for {group_cp} CP."
    else:
        low = max(0, group_cp - pick_mod.GUARDIAN_CP_LOSS)
        cause = heavy["at_pickup"]
        where = (f"from the start ([{points[0][0]}|{points[0][1]}])" if cause is None
                 else f"after the pickup at [{cause.zone[0]}|{cause.zone[1]}]")
        cp_text = (f"Route safety computed for {group_cp} CP, then {low} CP {where} "
                   f"(2nd heavy item: the Guardian lowers the shield).")
        cp_label = f"{group_cp} CP, {low} CP {where}"
    notes = [data_updated(data["meta"]), note, cp_text + (" " + "; ".join(breakdown) if breakdown else "")]
    if not available.strip():
        notes.append("Assumed: water and one 7 AP food; drugs/alcohol only as extras if needed.")
    if slots == 5:
        notes.append("Assumed: 5 free slots.")
    if result["cost"][0] or result["cost"][1]:
        # Not feasible: what would make it work (default items, no slot limit)?
        more = {**items, **{k: max(items.get(k, 0), n) for k, n in supplies.DEFAULT_AVAILABLE.items()}}
        alt = supplies.plan(route, st, more, end_ap=end_ap)
        if not (alt["cost"][0] or alt["cost"][1]):
            need = ", ".join(f"{n} × {supplies.ITEMS[k].label}" for k, n in alt["used"].items())
            notes.append(f"Feasible with: {need} ({sum(alt['used'].values())} slots)"
                         + (f", you have {slots}." if sum(alt['used'].values()) > slots else "."))
        else:
            notes.append("Not feasible even with the default set of items: shorten the route.")
    options = None
    if not available.strip() and any(k in supplies.EXTRAS for k in result["used"]) \
            and not (result["cost"][0] or result["cost"][1]):
        options = supplies.extra_options(route, st, items, end_ap=end_ap, slots=fitted["departure_slots"],
                                         stock=fata.expedition_extras(data["bank"]))
    pick_verdict, pick_notes, extra_warn = "", None, [p.warning for p in picks if p.warning]
    if picks:
        if fitted["rows"]:
            pick_verdict = pick_mod.verdict(fitted, slots, heavy)
            pick_notes = pick_mod.pickup_lines(fitted, slots)
        else:
            pick_verdict = "Pickups not checked: the supplies plan is not feasible."
        if heavy["drop_from"] is not None:
            extra_warn.append("2 heavy items: the Guardian must lower the shield (-2 CP for the group "
                              "until the night raises it).")
    return supplies.format_plan(route, st, result, title=f"Supplies plan {path}", notes=notes,
                                slots=slots, end_ap=end_ap, step_table=step_table,
                                teleport="teleport" in note, generic_extras=not available.strip(),
                                risks=risks, cp=group_cp, waypoints=points[1:-1], options=options,
                                pick_verdict=pick_verdict, pick_notes=pick_notes,
                                extra_warn=extra_warn, cp_label=cp_label)


@mcp.tool()
async def get_zone_details(
    day: int = 0,
    town_id: int = 0,
    x1: int | None = None,
    y1: int | None = None,
    x2: int | None = None,
    y2: int | None = None,
    max_ap: int | None = None,
    item: str = "",
) -> str:
    """
    The desert from Fata Morgana: ground items, ruins, zones.

    Three modes:
    - No arguments: desert overview — every item lying on the ground summed and
      grouped like the bank (water, food, drugs, defense items, metal, wood,
      weapons...), the ruins nearest first (blueprint, digs left, depletion), and
      who is outside where. Use for "what is out there", "where are the ruins".
    - item="<name>": the zones where items matching that name lie, nearest first
      (e.g. "wrought iron", "battery"). Use for "where can I find X".
    - x1/y1/x2/y2: every zone of that box, sorted by AP cost, with ruin, items,
      zombies and freshness; empty zones collapsed into one-line lists. One zone
      (x1=x2, y1=y2) also gets a "From town" block: moves, km, whether it is
      an EP zone, and whether the Observation Platform teleport, Heroic Return
      (Reclusive level) and Rescue (University level) reach it. Use that for
      "can I teleport / Heroic Return from [x|y]?" instead of computing km
      yourself. Prefer one call with a generous box over many small ones.
    Items are as last seen in each zone; the zone's day says how old.
    Item tags: (heavy) = one per citizen, two for a Guardian with the shield lowered;
    (defense) = adds defense in the bank; (defense part) = assembles into one.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit for the default town (towns/_current_town, else .env).
        x1: X coordinate of the first corner of the area to inspect (town-relative).
        y1: Y coordinate of the first corner of the area to inspect (town-relative).
        x2: X coordinate of the second corner. Required if x1/y1 are set.
        y2: Y coordinate of the second corner. Required if x1/y1 are set.
        max_ap: Optional AP budget for the box (e.g. 8). Cells beyond this cost
                are shown separately. Typical range: 4–15.
        item: Part of an item name to locate on the map (case-insensitive).
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid, day=day or None)

    coords_provided = all(v is not None for v in (x1, y1, x2, y2))
    if coords_provided:
        return fata.format_zone_path(data, x1, y1, x2, y2, max_ap=max_ap)
    return fata.format_zones(data, item=item)


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
        limit: Pages to consider (1-10, default 5). The best match comes in full,
               the others as one line each (name + first sentence): ask for one of
               them by name if it looks useful.
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
    digging and dried zones, rucksack slots and heavy items, weapons and kill runs
    (zoo trimming), building priority by game phase, opti-town tactics, wonders,
    player meta. Search before planning a trip that digs, carries items home or
    kills zombies.

    Args:
        query: Search terms (e.g. "thirst step counter", "digging dried",
            "rucksack", "heavy defensive relay", "weapons" (whole table),
            "day 5 buildings", "exploration points").
        section: Optional subfolder filter. Valid sections:
            "buildings" — AP costs, defense values, build priority by phase, wonders.
            "tactics"   — expedition planning, game mechanics, strategy, meta.
            Leave empty to search all sections.
    """
    return curated.search(query, section=section)


if __name__ == "__main__":
    # Run the MCP server using standard input/output
    mcp.run()
