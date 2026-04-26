# CLAUDE.md — Project Context for Claude Code

## What this project is

Read-only MCP server in Python for **MyHordes** (browser survival game, Eternaltwin/Die2Nite). Exposes live game data (bank, defense, citizens, map) to AI assistants via Model Context Protocol.

## Hard constraints — never violate

- **Read-only only.** Never implement write/action endpoints (no moving, no taking items, no spending AP). Game has strict anti-botting policies.
- **No automated API polling.** Every API call must result from a user query. No cron, no background refresh. Official game rule — see `docs/game-rules-for-external-apps.md`.
- **No secrets in code.** API keys (`MYHORDES_USER_KEY`, `MYHORDES_APP_KEY`) come from `.env` only. Never hardcode, log, or include in tool responses.

## Architecture

- **Entry point:** `main.py` — FastMCP server, runs over stdio.
- **Data source:** `sources/fatamorgana.py` — scrapes Fata Morgana spy pages via httpx + regex. No auth needed, just `FATAMORGANA_TOWN_ID`.
- **Planned:** `sources/official_api.py` — official JSON v1 API (needs `userkey` + `appkey`).
- **Game API:** `https://myhordes.eu/api/x/json/{type}`. Full reference: `docs/external-api-reference.md`.
- **API blocked ~23:59 CET** during nightly attack. Handle `nightly_attack` errors gracefully.

## Current state

- Live: `get_town_overview`, `get_citizen_positions`, `get_defense_status`, `get_bank_inventory`, `get_buildings`, `get_scout_map`, `search_wiki`, `list_wiki_categories`, `search_knowledge`
- Planned (blocked on app key): `get_construction_progress`, `get_last_night_report` — stubs commented out in `main.py`
- Next: `sources/official_api.py` once app key obtained

## Design decisions

Documented in `docs/implementation-notes.md`. Consult before changing data source strategy, MCP write permissions, or agent memory approach.

## Style notes

- Each tool maps to one clear player question.
- Format tool output as human-readable text for LLM, not raw JSON.
- Batch API fields via SURLL to minimize calls (rate limits apply).

## Skill triggers — natural language

When user says any of these, invoke the matching skill:

| Skill | Trigger phrases |
|---|---|
| `/build-plan` | "build plan", "what to build today", "construction queue", "what should we build", "building recommendations" |
| `/close-day` | "close the day", "finalize day", "close day logs", "wrap up yesterday", "night outcome" |
| `/close-day backfill` | "backfill days", "close all days", "close missing logs" |
| `/inspect-town` | "track town", "snapshot town", "take a town snapshot", "seed baseline", "update town state" |
| `/track-town` | "set up town cron", "schedule town tracking", "auto track town" |
| `/building-report` | "building report", "construction report", "throughput report", "how much AP we spent", "build history" |

## Developer reference

Full key files table, tech stack, game source paths: see **README.md** and `docs/`.
