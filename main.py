import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
import knowledge

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

if not MYHORDES_USER_KEY:
    print("Warning: MYHORDES_USER_KEY not found in environment variables.", flush=True)
if not MYHORDES_APP_KEY:
    print("Warning: MYHORDES_APP_KEY not found in environment variables.", flush=True)


def _check_auth() -> str | None:
    """Return an error message if credentials are missing, None if OK."""
    missing = []
    if not MYHORDES_USER_KEY:
        missing.append("MYHORDES_USER_KEY")
    if not MYHORDES_APP_KEY:
        missing.append("MYHORDES_APP_KEY")
    if missing:
        return f"Authentication Error: {', '.join(missing)} not configured. See .env.example."
    return None


@mcp.tool()
def get_bank_inventory() -> str:
    """
    Fetches the current bank inventory of the MyHordes town.
    Use this tool when the user asks about available resources, materials for construction sites,
    or general inventory status.
    """
    if err := _check_auth():
        return err

    # TODO: Replace mock with real API call:
    # GET https://myhordes.eu/api/x/json/map
    #   ?userkey={MYHORDES_USER_KEY}&appkey={MYHORDES_APP_KEY}
    #   &fields=city(.bank(.id|.count|.broken))
    #   &lang=en

    # MOCK RESPONSE FOR MVP
    mock_data = {
        "status": "success",
        "items": [
            {"name": "Wooden plank", "quantity": 12},
            {"name": "Twisted plank", "quantity": 5},
            {"name": "Wrought iron", "quantity": 8},
            {"name": "Water ration", "quantity": 24},
            {"name": "Bandage", "quantity": 2},
            {"name": "Flesh-eating virus", "quantity": 1},
        ],
    }

    # Format data for the LLM
    result = "Current Town Bank Inventory:\n"
    for item in mock_data["items"]:
        result += f"- {item['name']}: {item['quantity']} units\n"

    return result


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
