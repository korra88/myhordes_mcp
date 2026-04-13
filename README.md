# MyHordes MCP Server — AI Town Advisor

A **read-only** Model Context Protocol (MCP) server that exposes MyHordes game data to AI assistants, helping players optimize their town strategy.

> **Anti-botting policy:** This server implements **read-only operations only**. No write/action endpoints (moving, taking items, spending AP) will ever be added. No automated/scheduled API polling — all requests are triggered by user queries only. See [game rules](docs/game-rules-for-external-apps.md).

## Repository Structure

```
myhordes_mcp/
├── main.py                  # MCP server entry point (FastMCP)
├── knowledge.py             # Wiki knowledge base search engine
├── sources/
│   └── fatamorgana.py       # Fata Morgana spy page scraper
├── tips/                    # All shared meta-knowledge (loaded as system prompts)
├── towns/                   # Per-town daily logs and notes
├── personal/                # Player-specific private data (gitignored contents)
├── kb_build/                # Knowledge base build pipeline
│   ├── fetch_wiki.py        # MediaWiki scraper
│   └── process_wiki.py      # Wiki → JSON + Markdown processor
├── knowledge_base/          # Generated wiki content (gitignored)
├── requirements.txt         # Python dependencies
├── .env.example             # Template for environment variables
├── docs/                    # Source analysis & API reference
│   ├── source-map.md
│   ├── external-api-reference.md
│   ├── auth-and-rate-limits.md
│   └── game-rules-for-external-apps.md
└── myhordes-docker/         # Game source (git submodule, ignored)
```

## Setup

```bash
# 1. Create a virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure your credentials
cp .env.example .env
# Edit .env and set at minimum:
#   FATAMORGANA_TOWN_ID = your town's Fata Morgana spy ID (e.g. YOUR_TOWN_ID)
#
# Optional (for future official API support):
#   MYHORDES_USER_KEY = your External ID (found in account settings)
#   MYHORDES_APP_KEY  = your registered app secret

# 3. Build the knowledge base (optional, for wiki search tools)
make kb

# 4. Test the server starts
.venv/bin/python main.py
# It will start in stdio mode — press Ctrl+C to stop
```

## Using with Claude Code (CLI)

To connect this MCP server to Claude Code so you can use the tools in conversation:

### 1. Create `.mcp.json` in the project root

```json
{
  "mcpServers": {
    "myhordes": {
      "type": "stdio",
      "command": "/absolute/path/to/myhordes_mcp/.venv/bin/python",
      "args": ["main.py"],
      "cwd": "/absolute/path/to/myhordes_mcp",
      "env": {
        "FATAMORGANA_TOWN_ID": "YOUR_TOWN_ID"
      }
    }
  }
}
```

Replace `/absolute/path/to/myhordes_mcp` with the actual path to this repo, and `YOUR_TOWN_ID` with your town ID.

> **Note:** The `.env` file is loaded by `python-dotenv` inside `main.py`, so you can either put values in `.env` or in the `"env"` block above. The `"env"` block in `.mcp.json` takes precedence.

### 2. Load the agent personality (recommended)

To use the advisor persona and community tips as system prompts (more token-efficient than loading them as context):

```bash
claude --append-system-prompt-file ./AGENT-PERSONALITY.md \
       --append-system-prompt-file ./tips/game-mechanics.md \
       --append-system-prompt-file ./tips/mcp-guidelines.md \
       --append-system-prompt-file ./tips/player-behavior.md \
       --append-system-prompt-file ./tips/strategy-quirks.md \
       --append-system-prompt-file ./tips/buildings-cheatsheet.md \
       --append-system-prompt-file ./tips/opti-town-meta.md \
       --append-system-prompt-file ./tips/expedition-planning.md \
       --append-system-prompt-file ./tips/s19-meta.md \
       --append-system-prompt-file ./tips/session-protocols.md
```

This keeps all advisory content out of the conversation context window, leaving more room for actual game data. Add new `tips/*.md` files and include them here as the knowledge grows.

### 3. Restart Claude Code

```bash
# If running in CLI:
claude

# Verify the server is registered:
claude mcp list
```

### 3. Test the tools

In a Claude Code conversation, ask something like:

- *"What's the town status?"* → calls `get_town_overview`
- *"Who's outside the town?"* → calls `get_citizen_positions`
- *"Will we survive tonight's attack?"* → calls `get_defense_status`
- *"How bad does the attack get on day 15?"* → calls `get_attack_forecast`
- *"What's a Twisted Plank?"* → calls `search_knowledge_base`

## Available Tools

| Tool | Source | Description |
|------|--------|-------------|
| `get_town_overview` | Fata Morgana | Complete town snapshot: gate, defense, water, citizens, bank, attack estimates. Accepts optional `day` param for historical data. |
| `get_citizen_positions` | Fata Morgana | Who's inside/outside, where, plus death log. Accepts optional `day`. |
| `get_defense_status` | Fata Morgana | Defense breakdown, attack estimates, survival assessment, attack history. Accepts optional `day`. |
| `get_bank_inventory` | Fata Morgana | Town bank inventory grouped by category. Accepts optional `day`. |
| `get_buildings` | Fata Morgana | Built and available construction projects with AP costs and defense values. |
| `get_scout_map` | Fata Morgana | Zombie counts per scouted zone, grouped by threat level. |
| `get_zone_details` | Fata Morgana | Ruins, ground items, and zombie counts per map zone. |
| `get_attack_forecast` | Gest'Hordes | Theoretical min/max attack curve for the full game, with actual and estimated attack history and defence breakdown per day. |
| `search_knowledge_base` | Wiki KB | Search items, buildings, ruins, skills, statuses, and strategy guides. |
| `list_knowledge_categories` | Wiki KB | List available knowledge base categories. |

## Tech Stack

- Python 3.10+
- `mcp` (Anthropic MCP SDK / FastMCP)
- `httpx` (async HTTP client)
- `python-dotenv` (environment management)
