# MyHordes MCP Server — AI Town Advisor

A **read-only** Model Context Protocol (MCP) server that exposes MyHordes game data to AI assistants, helping players optimize their town strategy.

> **Anti-botting policy:** This server implements **read-only operations only**. No write/action endpoints (moving, taking items, spending AP) will ever be added.

## Repository Structure

```
myhordes_mcp/
├── main.py              # MCP server entry point (FastMCP)
├── requirements.txt     # Python dependencies
├── .env.example         # Template for environment variables
├── .gitignore
├── README.md
└── myhordes-docker/     # Game source (git submodule, ignored)
```

## Setup

```bash
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your API key
cp .env.example .env
# Edit .env and set MYHORDES_API_KEY to your External ID

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
