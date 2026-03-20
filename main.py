import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

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


if __name__ == "__main__":
    # Run the MCP server using standard input/output
    mcp.run()
