# CLAUDE.md — Project Context for Claude Code

## What this project is

Read-only MCP (Model Context Protocol) server in Python for **MyHordes**, browser survival game (Eternaltwin project, recreation of Motion Twin's Die2Nite). MCP lets AI agent fetch live game data (bank inventory, defense, attack estimations) to advise players on town strategy.

## Runtime mode

When running as game advisor (launched via `make desert-veteran` or similar), prioritize `AGENT-PERSONALITY.md` for tone, persona, behavior. Treat this file as background technical context and constraints only — advisor persona stay consistent throughout long conversations.

## Hard constraints — never violate these

- **Read-only only.** Never implement write/action endpoints (no moving, no taking items, no spending AP). Game has strict anti-botting policies.
- **No automated API polling.** No cron jobs, no background refresh, no periodic fetching. Every API call must result from user query. Official game rule — see `docs/game-rules-for-external-apps.md`.
- **No secrets in code.** API keys (`MYHORDES_USER_KEY`, `MYHORDES_APP_KEY`) come from `.env` only. Never hardcode, log, or include in tool responses.

## Architecture

- **Entry point:** `main.py` — `FastMCP` server with tool definitions, runs over stdio.
- **Data sources modular** under `sources/`:
  - `sources/fatamorgana.py` — Scrapes Fata Morgana spy pages (community-maintained). No auth needed, just town ID. Provides defense, citizens, gate, map/scout, attack estimations, ruins, buildings, water, consumables.
  - `sources/official_api.py` — *(planned)* Official JSON v1 API client. Needs `userkey` + `appkey`.
- **Auth (official API):** Two keys required — `userkey` (player External ID) + `appkey` (registered app secret). Both passed as query params.
- **Auth (Fata Morgana):** Just `FATAMORGANA_TOWN_ID` in `.env`. No API key needed.
- **Game API:** JSON v1 at `https://myhordes.eu/api/x/json/{type}`. `map` endpoint with SURLL field selection is workhorse. Full reference in `docs/external-api-reference.md`.
- **API blocked during attacks:** ~23:59 CET nightly. Tools must handle `nightly_attack` errors gracefully.
- **Fata Morgana approach:** Spy page embeds `var data = {...}` JS object with structured data (defense, water, buildings, scout zones) plus server-rendered HTML for citizens, gate, ruins, attack estimations. Fetch with httpx, parse with regex — no Selenium/browser needed.

## Key files

| File | Purpose |
|---|---|
| `main.py` | MCP server, tool definitions |
| `sources/fatamorgana.py` | Fata Morgana httpx scraper + formatters |
| `sources/official_api.py` | *(planned)* Official API client |
| `knowledge.py` | Wiki knowledge base search engine |
| `AGENT-PERSONALITY.md` | Symlink → active persona in `personas/`. Set via `make use-persona p=<name>`. Gitignored (local state). |
| `personas/` | All persona files. `town-elder.md` = current default. Add new personas here. |
| `docs/source-map.md` | Navigation guide for game PHP source (`myhordes-docker/myhordes/`) |
| `docs/external-api-reference.md` | Every JSON v1 endpoint, field, and SURLL syntax |
| `docs/auth-and-rate-limits.md` | Two-key auth model, rate limit buckets, attack lockout |
| `docs/game-rules-for-external-apps.md` | Official rules translated from German — authoritative compliance reference |
| `docs/implementation-notes.md` | Design decisions with rationale — read before changing architecture |
| `towns/` | Per-town memory logs written by agent (`s{season}-{town-slug}/daily-log.md` + `notes.md`) |
| `towns/_template/` | Templates for new town folders |

## Game source location

Game source (PHP/Symfony) at `myhordes-docker/myhordes/`. Key paths:
- API controllers: `src/Controller/API/JSONv1Controller.php` (primary), `XMLv2Controller.php`
- Entities: `src/Entity/` — `Town.php`, `Citizen.php`, `Inventory.php`, `Item.php`, `Building.php`, `Zone.php`
- Services: `src/Service/` — `TownHandler.php`, `CitizenHandler.php`, `InventoryHandler.php`
- Auth listener: `src/EventSubscriber/APIRequestListener.php`

## Tech stack

- Python 3.10+, `mcp` (FastMCP), `httpx`, `python-dotenv`
- System has `python3` (3.12.3) but `python3-venv` not installed — use `pip3 install --user` as fallback

## Current state

- Fata Morgana tools live: `get_town_overview`, `get_citizen_positions`, `get_defense_status`, `get_bank_inventory`, `get_buildings`, `get_scout_map`
- Knowledge base tools live: `search_knowledge_base`, `list_knowledge_categories`
- Planned (blocked on official API app key): `get_construction_progress`, `get_last_night_report` — stubs commented out in `main.py`
- Next: official API client (`sources/official_api.py`) once app key obtained
- Future: when both sources work, let agent choose right tool based on question

## Design decisions

Key architectural choices documented in `docs/implementation-notes.md`. Consult before changing data source strategy, MCP write permissions, or agent memory approach.

## Agent context files

Agent loaded with two types of system prompt files:

| File | Purpose |
|---|---|
| `personas/<name>.md` | Persona files. Each defines tone, behavior, character. Switch via `make use-persona p=<name>`. |
| `AGENT-PERSONALITY.md` | Symlink → active persona. Set locally, gitignored. |
| `tips/*.md` | All shared meta-knowledge: game mechanics, strategy, expedition math, opti-town tactics, session protocols. Add new tips here, **not** in persona files. |
| `personal/*.md` | Player-specific private data (friends, loadout). Local only, gitignored. |

**Where to put new content:**
- Persona or character enforcement → `AGENT-PERSONALITY.md` (keep slim — persona only)
- Game mechanics or rules → `tips/game-mechanics.md`
- MCP tool usage, constraints, town memory → `tips/mcp-guidelines.md`
- Observed player behavior (e.g. timezone patterns) → `tips/player-behavior.md`
- Non-obvious strategy or game quirk → `tips/strategy-quirks.md`
- Opti-town coordination tactics → `tips/opti-town-meta.md`
- Expedition planning & movement math → `tips/expedition-planning.md`
- Season-specific meta & nerfs → `tips/s19-meta.md`
- Session standing orders → `tips/session-protocols.md`
- New category → create new `tips/<topic>.md` and add to Makefile + README

## Style notes

- Keep tools focused — each tool map to clear player question
- Format tool output as human-readable text for LLM, not raw JSON
- Batch API field requests via SURLL to minimize calls (rate limits apply)