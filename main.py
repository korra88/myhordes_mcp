import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from myhordes_mcp import fata, gesthordes  # noqa: E402
from myhordes_mcp.knowledgebase import curated, wiki  # noqa: E402
from myhordes_mcp.utils.config import FATAMORGANA_TOWN_ID, resolve_town_id  # noqa: E402

# IMPORTANT: MyHordes rules prohibit automated/scheduled API polling.
# All API calls must be triggered by explicit user queries via MCP tools.
# Never add cron jobs, background refresh, or periodic data fetching.
# See: docs/game-rules-for-external-apps.md

mcp = FastMCP("MyHordes Advisor")

if not FATAMORGANA_TOWN_ID:
    print("Warning: FATAMORGANA_TOWN_ID not found in environment variables.", file=sys.stderr, flush=True)


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
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
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
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
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
    Use this when the user asks who is outside, who is camping, or about deaths.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid, day=day or None)
    return fata.format_citizens(data)


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
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
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
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
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
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
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
    group_cp: int = 2,
    escape_items: int = 0,
    scout_mode: bool = False,
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
        group_cp: Total Control Points of the expedition party. Default 2
                  (solo citizen, no bonuses). Each citizen = 2 CP base; add
                  bonuses for Prepared skill, Car Door, Riot Shield, etc.
                  Zones with zombies >= group_cp are flagged as trap risk.
        escape_items: Number of flash-grenade-equivalent escape items carried.
                      Default 0. Each can neutralize one trapped zone on the
                      shortest path.
        scout_mode: Set True when a Scout with Camouflage Vest is leading.
                    Trapped zones become passable at a detection risk cost
                    instead of being impassable.
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
    """
    tid = resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fata.fetch_town_data(tid, day=day or None)
    return fata.find_safe_path(
        data, x1, y1, x2, y2,
        group_cp=group_cp,
        escape_items=escape_items,
        scout_mode=scout_mode,
    )


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
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
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
        town_id: Gest'Hordes map ID. Omit to use the default from .env.
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
        town_id: Gest'Hordes map ID. Omit to use the default from .env.
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
