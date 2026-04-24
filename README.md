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
├── personas/                # Persona files (town-elder.md = default)
├── towns/                   # Per-town daily logs and notes
├── personal/                # Player-specific private data (gitignored contents)
├── kb_build/                # Knowledge base build pipeline
│   ├── fetch_wiki.py        # MediaWiki scraper (full re-crawl)
│   ├── process_wiki.py      # Wiki → JSON + Markdown processor
│   └── update_pages.py      # Targeted update from Special:Export XML
├── wiki/                    # Generated wiki content (gitignored)
├── knowledge/               # Curated advisor knowledge base (on-demand via search_knowledge)
│   └── buildings/           #   Building guides by game phase
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
# Full crawl — takes ~5-10 min, requires browser cookies in .env (see fetch_wiki.py)
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

Set `DISCORD_TOKEN` (or `DISCORD_BOT_TOKEN`) in `.env` to enable Discord tools (`get_mentions`, `get_discord_messages`, `send_discord_message`). Bot requires **Message Content**, **Server Members**, and **Presence** privileged intents enabled in the [Discord Developer Portal](https://discord.com/developers/applications).

Optionally set `DISCORD_CHANNEL_ID` to override the default monitored channel.

For full Discord channel/role management via MCP (optional), install the Node package and configure `.mcp.json`:
```bash
make install-discord-mcp
```

> **Note:** The `.env` file is loaded by `python-dotenv` inside `main.py`, so you can either put values in `.env` or in the `"env"` block above. The `"env"` block in `.mcp.json` takes precedence.

### 2. Select and load the agent persona

Personas live in `personas/`. The active persona is a symlink at `AGENT-PERSONALITY.md` (gitignored — local state).

```bash
# Select a persona (default: town-elder)
make use-persona p=town-elder

# Start the advisor — loads active persona + all tips/ files as system prompts
make desert-veteran
```

This keeps all advisory content out of the conversation context window, leaving more room for actual game data. Add new personas to `personas/` and switch between them with `make use-persona`.

### 3. Restart Claude Code

```bash
# If running in CLI:
claude

# Verify the server is registered:
claude mcp list
```

### 4. Test the tools

In a Claude Code conversation, ask something like:

- *"What's the town status?"* → calls `get_town_overview`
- *"Who's outside the town?"* → calls `get_citizen_positions`
- *"Will we survive tonight's attack?"* → calls `get_defense_status`
- *"How bad does the attack get on day 15?"* → calls `get_attack_forecast`
- *"What's a Twisted Plank?"* → calls `search_wiki`
- *"What should we build on day 8?"* → calls `search_knowledge`

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
| `search_wiki` | Wiki | Search items, buildings, ruins, skills, statuses, and strategy guides from en.mhwiki.org. |
| `list_wiki_categories` | Wiki | List available wiki categories. |
| `search_knowledge` | Knowledge | Search curated advisor KB — building phase guides, strategy, post-mortems. |
| `get_mentions` | Discord | Fetch unread messages mentioning the bot. Filtered server-side — no noise. Accepts optional `after_id` snowflake. |
| `get_discord_messages` | Discord | Browse channel messages with optional regex filter. Accepts `after_id`, `limit`, `regex_filter`. |
| `send_discord_message` | Discord | Send a message to the monitored channel as the bot. |

## Updating the Wiki

The wiki cache lives in `wiki/` (gitignored). Two update paths:

### Targeted update (recommended for a few changed pages)

No auth or cookies needed — uses a browser export.

1. Go to `https://en.mhwiki.org/wiki/Special:Export`
2. Paste the page titles (one per line), check **"Include only the current revision"**, click **Export**
3. Save the XML, then run:

```bash
.venv/bin/python kb_build/update_pages.py path/to/MHWiki-export.xml
```

Running without arguments prints the full instructions.

### Full re-crawl

Refetches all ~3000 pages. Requires Cloudflare cookies in `.env` (`MHWIKI_CF_CLEARANCE`, `MHWIKI_SESSION`, `MHWIKI_TOKEN`) copied from browser DevTools. Must be run from the same machine as the browser (cookies are IP-bound).

```bash
make kb
# or manually:
.venv/bin/python kb_build/fetch_wiki.py
.venv/bin/python kb_build/process_wiki.py
```

## Developer Reference

### Key files

| File | Purpose |
|---|---|
| `main.py` | MCP server, tool definitions |
| `sources/fatamorgana.py` | Fata Morgana httpx scraper + formatters |
| `sources/official_api.py` | *(planned)* Official API client |
| `knowledge.py` | Wiki search engine (indexes `wiki/processed/`) |
| `AGENT-PERSONALITY.md` | Symlink → active persona in `personas/`. Set via `make use-persona p=<name>`. Gitignored. |
| `personas/` | All persona files. `town-elder.md` = current default. Add new personas here. |
| `docs/source-map.md` | Navigation guide for game PHP source (`myhordes-docker/myhordes/`) |
| `docs/external-api-reference.md` | Every JSON v1 endpoint, field, and SURLL syntax |
| `docs/auth-and-rate-limits.md` | Two-key auth model, rate limit buckets, attack lockout |
| `docs/game-rules-for-external-apps.md` | Official rules translated from German — authoritative compliance reference |
| `docs/implementation-notes.md` | Design decisions with rationale — read before changing architecture |
| `towns/_template/` | Templates for new town folders |
| `knowledge/buildings/` | Building guides by game phase: `basic.md`, `intermediate.md`, `defense-focus.md`, `advanced.md`, `wonders.md` |

### Game source

PHP/Symfony source at `myhordes-docker/myhordes/` (git submodule). See `docs/source-map.md` for full navigation. Key paths:
- API controllers: `src/Controller/API/JSONv1Controller.php` (primary), `XMLv2Controller.php`
- Entities: `src/Entity/` — `Town.php`, `Citizen.php`, `Inventory.php`, `Item.php`, `Building.php`, `Zone.php`
- Services: `src/Service/` — `TownHandler.php`, `CitizenHandler.php`, `InventoryHandler.php`
- Auth listener: `src/EventSubscriber/APIRequestListener.php`

## Tech Stack

- Python 3.10+
- `mcp` (Anthropic MCP SDK / FastMCP)
- `httpx` (async HTTP client)
- `python-dotenv` (environment management)
