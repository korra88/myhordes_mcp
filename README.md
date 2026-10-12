# MyHordes MCP Server — AI Town Advisor

A **read-only** Model Context Protocol (MCP) server that exposes MyHordes game data to AI assistants, helping players optimize their town strategy.

> **Anti-botting policy:** This server implements **read-only operations only**. No write/action endpoints (moving, taking items, spending AP) will ever be added. No automated/scheduled API polling — all requests are triggered by user queries only. See [game rules](docs/game-rules-for-external-apps.md).

## Repository Structure

```
myhordes_mcp/
├── main.py                  # MCP server entry point (FastMCP) — tool declarations only
├── src/myhordes_mcp/
│   ├── utils/               # .env config, single-flight TTL cache
│   ├── fata/                # Fata Morgana: client (only HTTP entry), parse, formatters, pathfinding
│   ├── gesthordes/          # Gest'Hordes attack/defence statistics
│   ├── myhordes/            # Official MyHordes API (disabled)
│   └── knowledgebase/       # Wiki search (wiki/processed/) + curated knowledge/ search
├── persona.example.md       # Example persona — copy to persona.md (gitignored)
├── prompts/discord.md       # Discord channel context for the listener
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

Discord is not served by this MCP any more. Mentions in #myhordes-ai are answered by the
listener in [`../discord_mcp`](https://github.com/korra88/discord_mcp), configured by
`discord-listener.toml` and `discord-listener.mcp.json`. Start it with `make discord-listen`
(`make discord-listen-once` for one poll cycle). The bot token lives in `../discord_mcp/.env`.

> **Note:** The `.env` file is loaded by `python-dotenv` inside `main.py`, so you can either put values in `.env` or in the `"env"` block above. The `"env"` block in `.mcp.json` takes precedence.

### 2. Set up the persona and start the advisor

The advisor's voice comes from `persona.md` (gitignored, yours to edit). Start from the example:

```bash
cp persona.example.md persona.md

# Start the advisor — loads persona.md + knowledge/tactics/*.md + personal/*.md as system prompts
make advisor
```

This keeps all advisory content out of the conversation context window, leaving more room for actual game data. The Discord listener loads the same `persona.md`.

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
| `get_town_overview` | Fata Morgana | Town snapshot: gate, defense, water, citizens, attack estimate, possibly-trapped warning. Optional `day`. |
| `get_citizen_positions` | Fata Morgana | Who's inside/outside, where, plus death log. Optional `day`. |
| `get_defense_status` | Fata Morgana + Gest'Hordes | Defense breakdown, attack estimates, survival assessment. Optional `day`. |
| `get_bank_inventory` | Fata Morgana | Bank summary by strategic group (`detail='full'` for every item). Optional `day`. |
| `get_buildings` | Fata Morgana | Built today / history / available buildings. |
| `get_build_options` | Fata Morgana | Buildable buildings ranked with def/AP, def/water, def/nuts-and-bolts, bank availability, and the situation (buffer, water ratio, AP budget, multiplier gap). |
| `get_construction_history` | Fata Morgana + Gest'Hordes | Day-by-day paid AP vs budget, alive, attack, deaths, free vote upgrades. |
| `get_town_changes` | Fata Morgana (snapshots) | Movements with AP, bank deposits/withdrawals, constructions, AP spent moving today, warnings — since the previous check, the day start or a time. |
| `get_night_report` | Fata Morgana + Gest'Hordes | One night: survived/failed, defense vs attack, alive before/after, deaths with cause and position. |
| `get_expedition_roster` | Fata Morgana | Outside citizens by tile with ruin names and class icons, scrappers, reconciliation with an expedition list. |
| `map_bank_to_dump_sheet` | Fata Morgana | Bank mapped onto Garbage Dump sheet rows (aliases, broken, emptied weapons). |
| `get_scout_map` | Fata Morgana | Zombie counts per scouted zone, grouped by threat level. |
| `get_zone_details` | Fata Morgana | Ruins, ground items, and zombie counts per map zone, optionally in a box. |
| `find_expedition_path` | Fata Morgana | CP-aware safest/shortest path; `step_table=True` adds AP/EP and thirst counter per move. |
| `get_attack_forecast` | Gest'Hordes | Theoretical attack curve, actual and estimated attacks, defence per day. |
| `get_attack_distribution` | Gest'Hordes | Historical attack statistics across towns per day. |
| `search_wiki` | Wiki | Search items, buildings, ruins, skills, statuses, and strategy guides from en.mhwiki.org. |
| `list_wiki_categories` | Wiki | List available wiki categories. |
| `search_knowledge` | Knowledge | Search curated advisor KB — building phase guides, strategy, mechanics. |

Fata data is cached in memory for `FATA_CACHE_TTL` seconds (default 180); concurrent calls share one request. Every live fetch of the current day also stores a small snapshot under `towns/<town>/cache/snapshots/`, which `get_town_changes` compares.

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
| `main.py` | MCP server, tool definitions (thin wrappers) |
| `src/myhordes_mcp/fata/client.py` | Single entry point for Fata Morgana requests: coalesced + cached (`FATA_CACHE_TTL`, default 180 s), disk archive for past days. Documents the `getdata` JSON endpoint. |
| `src/myhordes_mcp/fata/` | `parse.py` (spy page → dict), `town.py` / `bank.py` / `buildings.py` / `zones.py` (formatters), `pathing.py` (expedition Dijkstra), `risk.py` (shared zone helpers), `archive.py` (disk archive) |
| `src/myhordes_mcp/gesthordes/` | Gest'Hordes stats client + formatters |
| `src/myhordes_mcp/myhordes/official_api.py` | *(disabled)* Official API client placeholder |
| `src/myhordes_mcp/knowledgebase/` | `wiki.py` (indexes `wiki/processed/`), `curated.py` (searches `knowledge/`) |
| `src/myhordes_mcp/utils/` | `config.py` (.env, town ID, paths), `cache.py` (single-flight TTL cache) |
| `persona.md` | Active persona (gitignored). Copy from `persona.example.md`. Loaded by `make advisor` and the Discord listener. |
| `prompts/discord.md` | Discord channel context appended by the listener. |
| `docs/source-map.md` | Navigation guide for game PHP source (`myhordes-docker/myhordes/`) |
| `docs/external-api-reference.md` | Every JSON v1 endpoint, field, and SURLL syntax |
| `docs/auth-and-rate-limits.md` | Two-key auth model, rate limit buckets, attack lockout |
| `docs/game-rules-for-external-apps.md` | Official rules translated from German — authoritative compliance reference |
| `docs/implementation-notes.md` | Design decisions with rationale — read before changing architecture |
| `templates/town/` | Templates for new town folders |
| `towns/` | Town logs (gitignored). Keep your own private data repo here, e.g. `git clone <your-town-data-repo> towns`, or point `MYHORDES_TOWNS_DIR` elsewhere. Skills write `towns/s{season}-{slug}/`. |
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
