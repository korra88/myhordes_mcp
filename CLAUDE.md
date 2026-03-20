# CLAUDE.md — Project Context for Claude Code

## What this project is

A read-only MCP (Model Context Protocol) server in Python for **MyHordes**, a browser survival game (Eternaltwin project, recreation of Motion Twin's Die2Nite). The MCP lets an AI agent fetch live game data (bank inventory, defense, attack estimations) to advise players on town strategy.

## Hard constraints — never violate these

- **Read-only only.** Never implement write/action endpoints (no moving, no taking items, no spending AP). The game has strict anti-botting policies.
- **No automated API polling.** No cron jobs, no background refresh, no periodic fetching. Every API call must result from a user query. This is an official game rule — see `docs/game-rules-for-external-apps.md`.
- **No secrets in code.** API keys (`MYHORDES_USER_KEY`, `MYHORDES_APP_KEY`) come from `.env` only. Never hardcode, log, or include them in tool responses.

## Architecture

- **Entry point:** `main.py` — `FastMCP` server with tool definitions, runs over stdio.
- **Auth:** Two keys required — `userkey` (player External ID) + `appkey` (registered app secret). Both passed as query params to the game API.
- **Game API:** JSON v1 at `https://myhordes.eu/api/x/json/{type}`. The `map` endpoint with SURLL field selection is the workhorse — one call can fetch bank, defense, estimations, citizens, zones, buildings. Full reference in `docs/external-api-reference.md`.
- **API blocked during attacks:** ~23:59 CET nightly. Tools must handle `nightly_attack` errors gracefully.

## Key files

| File | Purpose |
|---|---|
| `main.py` | MCP server, tool definitions |
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

- MVP phase: `get_bank_inventory` tool returns mocked data
- Next: replace mocks with real `httpx` calls to the JSON v1 API
- Future tools planned: town status, defense breakdown, attack estimations, citizen list, map/zones, buildings, gazette

## Style notes

- Keep tools focused — each tool should map to a clear player question
- Format tool output as human-readable text for the LLM, not raw JSON
- Batch API field requests via SURLL to minimize calls (rate limits apply)
