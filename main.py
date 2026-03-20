import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables from .env file
load_dotenv()

# Initialize the MCP Server
mcp = FastMCP("MyHordes Advisor")

# Fetch the API key (External ID) from the environment
MYHORDES_API_KEY = os.getenv("MYHORDES_API_KEY")

if not MYHORDES_API_KEY:
    print("Warning: MYHORDES_API_KEY not found in environment variables.", flush=True)

@mcp.tool()
def get_bank_inventory() -> str:
    """
    Fetches the current bank inventory of the MyHordes town.
    Use this tool when the user asks about available resources, materials for construction sites,
    or general inventory status.
    """
    if not MYHORDES_API_KEY:
        return "Authentication Error: MyHordes API Key is not configured in the MCP server."

    # TODO: Implement actual HTTP request to MyHordes API
    # Example:
    # url = f"https://myhordes.eu/api/v1/town/bank?external_id={MYHORDES_API_KEY}"
    # response = httpx.get(url)
    # data = response.json()

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
