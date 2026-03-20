# CLAUDE.md — Project Context for Claude Code

## What this project is

A read-only MCP (Model Context Protocol) server in Python for **MyHordes**, a browser survival game (Eternaltwin project, recreation of Motion Twin's Die2Nite). The MCP lets an AI agent fetch live game data (bank inventory, defense, attack estimations) to advise players on town strategy.

## Hard constraints — never violate these

- **Read-only only.** Never implement write/action endpoints (no moving, no taking items, no spending AP). The game has strict anti-botting policies.
- **No automated API polling.** No cron jobs, no background refresh, no periodic fetching. Every API call must result from a user query. This is an official game rule — see `docs/game-rules-for-external-apps.md`.
- **No secrets in code.** API keys (`MYHORDES_USER_KEY`, `MYHORDES_APP_KEY`) come from `.env` only. Never hardcode, log, or include them in tool responses.

## Architecture

- **Entry point:** `main.py` — `FastMCP` server with tool definitions, runs over stdio.
- **Data sources are modular** under `sources/`:
  - `sources/fatamorgana.py` — Scrapes Fata Morgana spy pages (community-maintained). No auth needed, just a town ID. Provides defense, citizens, gate, map/scout, attack estimations, ruins, buildings, water, consumables.
  - `sources/official_api.py` — *(planned)* Official JSON v1 API client. Needs `userkey` + `appkey`.
- **Auth (official API):** Two keys required — `userkey` (player External ID) + `appkey` (registered app secret). Both passed as query params.
- **Auth (Fata Morgana):** Just `FATAMORGANA_TOWN_ID` in `.env`. No API key needed.
- **Game API:** JSON v1 at `https://myhordes.eu/api/x/json/{type}`. The `map` endpoint with SURLL field selection is the workhorse. Full reference in `docs/external-api-reference.md`.
- **API blocked during attacks:** ~23:59 CET nightly. Tools must handle `nightly_attack` errors gracefully.
- **Fata Morgana approach:** The spy page embeds a `var data = {...}` JS object with structured data (defense, water, buildings, scout zones) plus server-rendered HTML for citizens, gate, ruins, attack estimations. We fetch with httpx and parse with regex — no Selenium/browser needed.

## Key files

| File | Purpose |
|---|---|
| `main.py` | MCP server, tool definitions |
| `sources/fatamorgana.py` | Fata Morgana httpx scraper + formatters |
| `sources/official_api.py` | *(planned)* Official API client |
| `knowledge.py` | Wiki knowledge base search engine |
| `AGENT-PERSONALITY.md` | System prompt for the end-user AI agent (game advisor persona + mechanics + MCP guidelines) |
| `docs/source-map.md` | Navigation guide for the game PHP source (`myhordes-docker/myhordes/`) |
| `docs/external-api-reference.md` | Every JSON v1 endpoint, field, and SURLL syntax |
| `docs/auth-and-rate-limits.md` | Two-key auth model, rate limit buckets, attack lockout |
| `docs/game-rules-for-external-apps.md` | Official rules translated from German — the authoritative compliance reference |

## Game source location

The game source (PHP/Symfony) is at `myhordes-docker/myhordes/`. Key paths:
- API controllers: `src/Controller/API/JSONv1Controller.php` (primary), `XMLv2Controller.php`
- Entities: `src/Entity/` — `Town.php`, `Citizen.php`, `Inventory.php`, `Item.php`, `Building.php`, `Zone.php`
- Services: `src/Service/` — `TownHandler.php`, `CitizenHandler.php`, `InventoryHandler.php`
- Auth listener: `src/EventSubscriber/APIRequestListener.php`

## Tech stack

- Python 3.10+, `mcp` (FastMCP), `httpx`, `python-dotenv`
- System has `python3` (3.12.3) but `python3-venv` is not installed — use `pip3 install --user` as fallback

## Current state

- Fata Morgana tools are live: `get_town_overview`, `get_citizen_positions`, `get_defense_status`
- `get_bank_inventory` still returns mocked data (waiting for official API app key)
- Knowledge base tools are live: `search_knowledge_base`, `list_knowledge_categories`
- Next: official API client (`sources/official_api.py`) once app key is obtained
- Future: when both sources work, let the agent choose the right tool based on the question

## Style notes

- Keep tools focused — each tool should map to a clear player question
- Format tool output as human-readable text for the LLM, not raw JSON
- Batch API field requests via SURLL to minimize calls (rate limits apply)
