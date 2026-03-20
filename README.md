# MyHordes MCP Server — AI Town Advisor

A **read-only** Model Context Protocol (MCP) server that exposes MyHordes game data to AI assistants, helping players optimize their town strategy.

> **Anti-botting policy:** This server implements **read-only operations only**. No write/action endpoints (moving, taking items, spending AP) will ever be added. No automated/scheduled API polling — all requests are triggered by user queries only. See [game rules](docs/game-rules-for-external-apps.md).

## Repository Structure

```
myhordes_mcp/
├── main.py              # MCP server entry point (FastMCP)
├── requirements.txt     # Python dependencies
├── .env.example         # Template for environment variables
├── .gitignore
├── README.md
├── docs/                # Source analysis & API reference
│   ├── source-map.md                  # Game source navigation guide
│   ├── external-api-reference.md      # JSON v1 API endpoints & fields
│   ├── auth-and-rate-limits.md        # Auth model & rate limiting
│   └── game-rules-for-external-apps.md # Official rules (translated)
└── myhordes-docker/     # Game source (git submodule, ignored)
```

## Setup

```bash
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your API credentials
cp .env.example .env
# Edit .env and set:
#   MYHORDES_USER_KEY = your External ID (found in account settings)
#   MYHORDES_APP_KEY  = your registered app secret

# 4. Run the server
python main.py
```

## Available Tools

| Tool                 | Description                                      |
|----------------------|--------------------------------------------------|
| `get_bank_inventory` | Returns the current town bank inventory (mocked) |

## Goals

1. **MVP (current):** Mocked bank inventory tool over stdio transport.
2. **Next:** Real API integration via `httpx` against the MyHordes API.
3. **Future:** Additional read-only tools — town status, attack estimations, citizen list, construction site progress.

## Tech Stack

- Python 3.10+
- `mcp` (Anthropic MCP SDK / FastMCP)
- `httpx` (async HTTP client)
- `python-dotenv` (environment management)
