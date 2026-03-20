import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
import knowledge
from sources import fatamorgana

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
    print("Warning: MYHORDES_USER_KEY not found in environment variables.", flush=True)
if not MYHORDES_APP_KEY:
    print("Warning: MYHORDES_APP_KEY not found in environment variables.", flush=True)
if not FATAMORGANA_TOWN_ID:
    print("Warning: FATAMORGANA_TOWN_ID not found in environment variables.", flush=True)


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


def _check_fata() -> str | None:
    """Return an error message if Fata Morgana town ID is missing, None if OK."""
    if not FATAMORGANA_TOWN_ID:
        return "Error: FATAMORGANA_TOWN_ID not configured. Set it in .env to your town's Fata Morgana spy ID."
    return None


@mcp.tool()
async def get_bank_inventory(day: int = 0) -> str:
    """
    Fetches the current bank inventory of the MyHordes town, grouped by category.
    Use this tool when the user asks about available resources, materials for
    construction sites, or general inventory status.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
    """
    if err := _check_fata():
        return err
    data = await fatamorgana.fetch_town_data(int(FATAMORGANA_TOWN_ID), day=day or None)
    return fatamorgana.format_bank(data)


# ---------------------------------------------------------------------------
# Fata Morgana tools — live town data from community-maintained spy service
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_town_overview(day: int = 0) -> str:
    """
    Fetches a complete overview of the town from Fata Morgana (community spy service).
    Returns: town name/day, gate status, defense breakdown, attack estimation,
    water supply, consumables, and citizen positions.
    Use this as the first tool when the user asks about general town status.
    Data is crowd-sourced by players and may lag behind real-time game state.

    Args:
        day: Specific day number to inspect (e.g. 5 for day 5). Use 0 or omit for
             the current/latest day. Useful for comparing town progress over time.
    """
    if err := _check_fata():
        return err
    data = await fatamorgana.fetch_town_data(int(FATAMORGANA_TOWN_ID), day=day or None)
    return fatamorgana.format_town_overview(data)


@mcp.tool()
async def get_citizen_positions(day: int = 0) -> str:
    """
    Fetches citizen positions from Fata Morgana — who is inside the town,
    who is outside (and where), and the list of dead citizens with cause of death.
    Use this when the user asks who is outside, who is camping, or about deaths.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
    """
    if err := _check_fata():
        return err
    data = await fatamorgana.fetch_town_data(int(FATAMORGANA_TOWN_ID), day=day or None)
    return fatamorgana.format_citizens(data)


@mcp.tool()
async def get_defense_status(day: int = 0) -> str:
    """
    Fetches the town defense breakdown and attack estimations from Fata Morgana.
    Includes: total defense, per-source breakdown (wall, buildings, items, guardians,
    homes, other), item multiplier, tonight's and tomorrow's zombie estimates,
    and a survival assessment (safe / at risk / danger).
    Use this when the user asks about defense, attack survival, or zombie estimates.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
    """
    if err := _check_fata():
        return err
    data = await fatamorgana.fetch_town_data(int(FATAMORGANA_TOWN_ID), day=day or None)
    return fatamorgana.format_defense(data)


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
