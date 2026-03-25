import os
import sys
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
import knowledge
from sources import fatamorgana, gesthordes

# IMPORTANT: MyHordes rules prohibit automated/scheduled API polling.
# All API calls must be triggered by explicit user queries via MCP tools.
# Never add cron jobs, background refresh, or periodic data fetching.
# See: docs/game-rules-for-external-apps.md

# Load environment variables from .env file
load_dotenv()

# Initialize the MCP Server
mcp = FastMCP("MyHordes Advisor")

# Fetch API credentials from the environment
# userkey: the player's External ID (identifies whose data to fetch)
# appkey: the registered app secret (identifies this application)
MYHORDES_USER_KEY = os.getenv("MYHORDES_USER_KEY")
MYHORDES_APP_KEY = os.getenv("MYHORDES_APP_KEY")

FATAMORGANA_TOWN_ID = os.getenv("FATAMORGANA_TOWN_ID")

if not MYHORDES_USER_KEY:
    print("Warning: MYHORDES_USER_KEY not found in environment variables.", file=sys.stderr, flush=True)
if not MYHORDES_APP_KEY:
    print("Warning: MYHORDES_APP_KEY not found in environment variables.", file=sys.stderr, flush=True)
if not FATAMORGANA_TOWN_ID:
    print("Warning: FATAMORGANA_TOWN_ID not found in environment variables.", file=sys.stderr, flush=True)


def _check_auth() -> str | None:
    """Return an error message if official API credentials are missing, None if OK."""
    missing = []
    if not MYHORDES_USER_KEY:
        missing.append("MYHORDES_USER_KEY")
    if not MYHORDES_APP_KEY:
        missing.append("MYHORDES_APP_KEY")
    if missing:
        return f"Authentication Error: {', '.join(missing)} not configured. See .env.example."
    return None


def _resolve_town_id(town_id: int = 0) -> int | str:
    """Return a valid town ID (int) or an error message (str).

    If town_id is provided and non-zero, use it directly.
    Otherwise fall back to the FATAMORGANA_TOWN_ID env var.
    """
    if town_id:
        return int(town_id)
    if FATAMORGANA_TOWN_ID:
        return int(FATAMORGANA_TOWN_ID)
    return "Error: No town ID provided and FATAMORGANA_TOWN_ID not configured in .env."


@mcp.tool()
async def get_bank_inventory(day: int = 0, town_id: int = 0, detail: str = "summary") -> str:
    """
    Fetches the current bank inventory of the MyHordes town.
    Default view is a strategic summary grouped by priority (water, food by AP,
    drugs, defense items, key resources, weapons). Use detail='full' for the
    complete item list grouped by raw category.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
        detail: 'summary' (default) for strategic overview, 'full' for every item.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)
    if detail == "full":
        return fatamorgana.format_bank(data)
    return fatamorgana.format_bank_summary(data)


# ---------------------------------------------------------------------------
# Fata Morgana tools — live town data from community-maintained spy service
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_town_overview(day: int = 0, town_id: int = 0, detail: str = "full") -> str:
    """
    Fetches a complete overview of the town from Fata Morgana (community spy service).
    Returns: town name/day, gate status, defense breakdown, attack estimation,
    water supply, consumables, and citizen positions.
    Use this as the first tool when the user asks about general town status.
    Data is crowd-sourced by players and may lag behind real-time game state.

    Args:
        day: Specific day number to inspect (e.g. 5 for day 5). Use 0 or omit for
             the current/latest day. Useful for comparing town progress over time.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
        detail: 'full' (default) includes bank inventory and deaths. 'compact' omits
                both — use for cron/delta checks where bank is fetched separately via
                get_bank_inventory.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)
    # Enrich with season points from Gest'Hordes (current day only)
    season_points = None
    if not (day and day != data.get("meta", {}).get("day")):
        gh_data = await gesthordes.fetch_stats(tid)
        season_points = gesthordes.extract_season_points(gh_data)
    return fatamorgana.format_town_overview(data, season_points=season_points, detail=detail)


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
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)
    return fatamorgana.format_citizens(data)


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
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)
    # Enrich current-day defense with Gest'Hordes breakdown (watchmen, temps, dead bonus)
    gh_defense = None
    if not (day and day != data.get("meta", {}).get("day")):
        gh_data = await gesthordes.fetch_stats(tid)
        gh_defense = gesthordes.extract_current_defense(gh_data)
    return fatamorgana.format_defense(data, gh_defense=gh_defense)


@mcp.tool()
async def get_buildings(day: int = 0, town_id: int = 0) -> str:
    """
    Fetches the town's building list from Fata Morgana — what's been built
    and what's still available to construct, with defense values and AP costs.
    Use this when the user asks what to build next, what buildings exist,
    or how much AP a construction needs.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)
    return fatamorgana.format_buildings(data)


@mcp.tool()
async def get_scout_map(
    day: int = 0,
    town_id: int = 0,
    x1: int | None = None,
    y1: int | None = None,
    x2: int | None = None,
    y2: int | None = None,
) -> str:
    """
    Fetches zombie counts per zone from scout data (Fata Morgana).
    Shows which zones have been scouted, how many zombies were spotted,
    and who scouted them. Zones are grouped by threat level.
    Use this when the user asks about zombie positions, safe scavenging routes,
    or where the horde is concentrated.

    When x1/y1/x2/y2 are provided, runs Dijkstra pathfinding to find the safest
    route between those two coordinates, minimising total zombie exposure.
    Hard cap: 40 AP. Use this when the user asks for the safest path to a location.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
        x1: X coordinate of the starting point (town-relative). Omit for full map.
        y1: Y coordinate of the starting point.
        x2: X coordinate of the destination. Required if x1/y1 are set.
        y2: Y coordinate of the destination. Required if x1/y1 are set.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)

    coords_provided = all(v is not None for v in (x1, y1, x2, y2))
    if coords_provided:
        return fatamorgana.find_safe_path(data, x1, y1, x2, y2)
    return fatamorgana.format_scout(data)


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

    When x1/y1/x2/y2 are provided, restricts output to the bounding box between
    those two coordinates, sorted by AP cost (Manhattan distance from town).
    Use this for expedition planning: "what's between [2|3] and [5|6] within 8 AP?"

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
        x1: X coordinate of the first corner of the area to inspect (town-relative).
        y1: Y coordinate of the first corner of the area to inspect (town-relative).
        x2: X coordinate of the second corner. Required if x1/y1 are set.
        y2: Y coordinate of the second corner. Required if x1/y1 are set.
        max_ap: Optional AP budget. Cells beyond this cost are shown separately.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)

    coords_provided = all(v is not None for v in (x1, y1, x2, y2))
    if coords_provided:
        return fatamorgana.format_zone_path(data, x1, y1, x2, y2, max_ap=max_ap)
    return fatamorgana.format_zones(data)


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
    tid = _resolve_town_id(town_id)
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
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await gesthordes.fetch_stats(tid)
    return gesthordes.format_attack_forecast(data)


# ---------------------------------------------------------------------------
# Official API tools — requires MYHORDES_APP_KEY (not yet available)
# ---------------------------------------------------------------------------

# TODO: Uncomment once official API app key is obtained and sources/official_api.py
# is implemented. These tools need the official API because Fata Morgana doesn't
# provide construction progress details or last night's attack report.

# @mcp.tool()
# async def get_construction_progress() -> str:
#     """
#     Fetches construction site progress from the official API.
#     Shows buildings currently under construction: AP invested vs. AP needed,
#     resources deposited vs. required, and estimated completion.
#     Use this when the user asks what's closest to being finished,
#     where to spend AP, or what resources are still needed for a build.
#     """
#     if err := _check_auth():
#         return err
#     # return await official_api.get_construction_progress(MYHORDES_USER_KEY, MYHORDES_APP_KEY)

# @mcp.tool()
# async def get_last_night_report() -> str:
#     """
#     Fetches last night's attack gazette from the official API.
#     Includes: zombies killed, defense used, water lost overnight,
#     wind direction (if Search Tower built), and citizen casualties.
#     Use this for post-attack analysis — was defense tight or comfortable,
#     and how should the town adjust today?
#     """
#     if err := _check_auth():
#         return err
#     # return await official_api.get_last_night_report(MYHORDES_USER_KEY, MYHORDES_APP_KEY)


# ---------------------------------------------------------------------------
# Knowledge base tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_knowledge_base(query: str, category: str = "", limit: int = 5) -> str:
    """
    Search the MyHordes wiki knowledge base for game information.
    Use this tool to look up items, buildings, ruins, skills, statuses, distinctions,
    jobs, deaths, mechanics, and strategy guides.

    Args:
        query: Search terms (e.g. "Twisted Plank", "camping", "water ration poisoned")
        category: Optional filter — one of: items, buildings, ruins, skills, status,
                  distinctions, deaths, homes, jobs, guide, general, town, events, tutorials.
                  Leave empty to search all categories.
        limit: Max results to return (1-10, default 5). Use 1-2 for specific lookups,
               higher for broad searches.
    """
    if not knowledge.is_loaded():
        return "Error: Knowledge base not loaded. Run 'make process' to build it."

    limit = max(1, min(10, limit))
    cat = category.strip().lower() or None
    results = knowledge.search(query, category=cat, limit=limit)

    if not results:
        return f"No results found for '{query}'" + (f" in category '{category}'" if category else "") + "."

    parts = [f"Found {len(results)} result(s) for '{query}':\n"]
    for r in results:
        parts.append(f"## {r['name']} [{r['category']}]\n")
        parts.append(r["content"])
        parts.append("\n---\n")

    return "\n".join(parts)


@mcp.tool()
def list_knowledge_categories() -> str:
    """
    List all categories in the MyHordes knowledge base with page counts.
    Use this to discover what information is available before searching.
    """
    if not knowledge.is_loaded():
        return "Error: Knowledge base not loaded. Run 'make process' to build it."

    cats = knowledge.get_categories()
    lines = ["MyHordes Knowledge Base Categories:\n"]
    total = 0
    for cat, count in cats.items():
        lines.append(f"- {cat}: {count} pages")
        total += count
    lines.append(f"\nTotal: {total} pages")
    lines.append("\nUse search_knowledge_base(query, category='...') to search within a category.")
    return "\n".join(lines)


if __name__ == "__main__":
    # Run the MCP server using standard input/output
    mcp.run()
