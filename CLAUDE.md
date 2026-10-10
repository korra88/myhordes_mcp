# CLAUDE.md — Project Context for Claude Code

## What this project is

Read-only MCP server in Python for **MyHordes** (browser survival game, Eternaltwin/Die2Nite). Exposes live game data (bank, defense, citizens, map) to AI assistants via Model Context Protocol.

## Hard constraints — never violate

- **Read-only only.** Never implement write/action endpoints (no moving, no taking items, no spending AP). Game has strict anti-botting policies.
- **No automated API polling.** Every API call must result from a user query. No cron, no background refresh. Official game rule — see `docs/game-rules-for-external-apps.md`.
- **No secrets in code.** API keys (`MYHORDES_USER_KEY`, `MYHORDES_APP_KEY`) come from `.env` only. Never hardcode, log, or include in tool responses.

## Architecture

- **Entry point:** `main.py` — FastMCP server, runs over stdio. Tool declarations only; logic lives in `src/myhordes_mcp/`.
- **Data source:** `src/myhordes_mcp/fata/` — scrapes Fata Morgana spy pages. No auth needed, just `FATAMORGANA_TOWN_ID`.
  Every Fata request goes through `fata/client.py:fetch_town_data()` (single-flight + TTL cache, `FATA_CACHE_TTL` default 180 s). Never add another HTTP path to Fata.
- **Secondary:** `src/myhordes_mcp/gesthordes/` — Gest'Hordes attack stats (same cache pattern).
- **Disabled:** `src/myhordes_mcp/myhordes/official_api.py` — official JSON v1 API (needs `userkey` + `appkey`), not wired as tools.
- **Game API:** `https://myhordes.eu/api/x/json/{type}`. Full reference: `docs/external-api-reference.md`.
- **API blocked ~23:59 CET** during nightly attack. Handle `nightly_attack` errors gracefully.

## Current state

- Live (Fata): `get_town_overview`, `get_citizen_positions`, `get_defense_status`, `get_bank_inventory`, `get_buildings`, `get_scout_map`, `get_zone_details`, `find_expedition_path`, `get_build_options`, `get_construction_history`, `get_town_changes`, `get_night_report`, `get_expedition_roster`, `map_bank_to_dump_sheet`
- Live (Gest'Hordes): `get_attack_distribution`, `get_attack_forecast`
- Live (offline knowledge): `search_wiki`, `list_wiki_categories`, `search_knowledge`
- Removed: `refresh_fata_data` (wrote to Fata, little value)
- Official API disabled; planned tools described in `myhordes/official_api.py`

## Design decisions

Documented in `docs/implementation-notes.md`. Consult before changing data source strategy, MCP write permissions, or agent memory approach.

## Style notes

- Each tool maps to one clear player question.
- Format tool output as human-readable text for LLM, not raw JSON.
- Batch API fields via SURLL to minimize calls (rate limits apply).
- **Condensed by default.** Tool defaults return condensed views (overview→compact,
  bank→summary, buildings→summary); full detail is opt-in via explicit args, and
  docstrings must tell the model when NOT to fetch more. Server is also used by
  small models (Sonnet, local gemma) — keep defaults small and steering explicit.

## Skill triggers — natural language

When user says any of these, invoke the matching skill:

| Skill | Trigger phrases |
|---|---|
| `/build-plan` | "build plan", "what to build today", "construction queue", "what should we build", "building recommendations" |
| `/close-day` | "close the day", "finalize day", "close day logs", "wrap up yesterday", "night outcome" |
| `/close-day backfill` | "backfill days", "close all days", "close missing logs" |
| `/inspect-town` | "track town", "snapshot town", "take a town snapshot", "seed baseline", "update town state" |
| `/building-report` | "building report", "construction report", "throughput report", "how much AP we spent", "build history" |
| `/expedition-report` | "expedition list", "check the expedition list", "who is outside", "who is not on the list", "expedition roster", "count the scrappers" |
| `/update-garbage-dump-list` | "update the dump list", "update garbage dump", "refresh the dump sheet", "update the bank items in the spreadsheet", "sync bank to the dump calculator" |

## Developer reference

Full key files table, tech stack, game source paths: see **README.md** and `docs/`.
