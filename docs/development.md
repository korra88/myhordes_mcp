# Development

Read [implementation-notes.md](implementation-notes.md) before changing the data
source, the read-only model or how town memory works.

## Repository layout

```
myhordes_mcp/
├── main.py                  # MCP server entry point (FastMCP) — tool declarations only
├── src/myhordes_mcp/
│   ├── utils/               # .env config, town ID, single-flight TTL cache, game clock
│   ├── fata/                # Fata Morgana: client (only HTTP entry), parsers, formatters, pathfinding, CP log
│   ├── gesthordes/          # Gest'Hordes attack/defence statistics
│   ├── myhordes/            # Official MyHordes API (disabled)
│   └── knowledgebase/       # Wiki search (wiki/processed/) + curated knowledge/ search
├── .claude/commands/        # Skills (slash commands) for Claude Code
├── knowledge/
│   ├── buildings/           # Building guides by game phase (search_knowledge)
│   └── tactics/             # Advisor knowledge, appended to the system prompt by make advisor
├── persona.example.md       # Example persona — copy to persona.md (gitignored)
├── prompts/game-primer.md   # One-page game rules for the Discord bot (other clients too)
├── prompts/discord.md       # Discord channel context for the listener
├── personal/                # Player-specific private notes (gitignored contents)
├── towns/                   # Town logs + Fata archive (gitignored, see town-logs.md)
├── templates/town/          # Starting files for a new town's logs
├── templates/systemd/       # User units: Discord listener service, nightly towns commit
├── scripts/set_town.py      # Show/set the default town (make town)
├── kb_build/                # Wiki fetch/process/update scripts (see wiki.md)
├── wiki/                    # Generated wiki content (gitignored)
├── docs/                    # This documentation, API and source references
└── myhordes-docker/         # Optional local clone of the game source (gitignored)
```

`make help` lists every Makefile target.

## Key files

| File | Purpose |
|---|---|
| `main.py` | MCP server, tool definitions (thin wrappers) |
| `src/myhordes_mcp/fata/client.py` | Single entry point for Fata Morgana requests (`/towndata`): coalesced + cached (`FATA_CACHE_TTL`, default 180 s), disk archive for past days. |
| `src/myhordes_mcp/fata/` | `towndata.py` (`/towndata` → dict, field meanings), `parse.py` (legacy spy-page archives → dict), `cp.py` (per-citizen CP log), `townlog.py` (automatic town log files), `town.py` / `bank.py` / `buildings.py` / `zones.py` (formatters), `pathing.py` (expedition Dijkstra), `supplies.py` (consumables along a route), `planning.py` (build options, construction history), `blueprints.py` (blueprint reading order), `risk.py` (shared zone helpers: freshness, km and reach, gate/outside/defense evening alerts, respawn check), `archive.py` (disk archive). Which game rules live in code: [mechanics-in-code.md](mechanics-in-code.md) |
| `src/myhordes_mcp/gesthordes/` | Gest'Hordes stats client + formatters |
| `src/myhordes_mcp/myhordes/official_api.py` | *(disabled)* Official API client placeholder |
| `src/myhordes_mcp/knowledgebase/` | `wiki.py` (indexes `wiki/processed/`), `curated.py` (searches `knowledge/`) |
| `src/myhordes_mcp/utils/` | `config.py` (.env, town ID, paths, User-Agent), `cache.py` (single-flight TTL cache), `clock.py` (game time) |
| `persona.md` | Active persona (gitignored). Copy from `persona.example.md`. Loaded by `make advisor` and the Discord listener. |
| `prompts/game-primer.md` | Core game rules + knowledge-base index, appended by the listener. Rules the tools compute stay out of it. |
| `prompts/discord.md` | Discord channel context appended by the listener. |

## Docs

| File | Content |
|---|---|
| [implementation-notes.md](implementation-notes.md) | Design decisions with rationale |
| [game-rules-for-external-apps.md](game-rules-for-external-apps.md) | Official rules translated from German — authoritative compliance reference |
| [town-logs.md](town-logs.md) | `towns/` layout, CP log, private git repo for the logs |
| [wiki.md](wiki.md) / [discord.md](discord.md) | Offline wiki, Discord bot |
| [external-api-reference.md](external-api-reference.md) | Official JSON v1 API: every endpoint, field and SURLL syntax |
| [auth-and-rate-limits.md](auth-and-rate-limits.md) | Official API: two-key auth model, rate limit buckets, attack lockout |
| [source-map.md](source-map.md) | Navigation guide for the game's PHP source |
| [future-improvements.md](future-improvements.md) | Ideas not actionable yet |
| [mechanics-in-code.md](mechanics-in-code.md) | Which game rules the tools compute, and which to move from prose to code next |

## Game source

PHP/Symfony source, used only as a reference for the docs and parsers. Not part of this repo: clone
[myhordes-docker](https://gitlab.com/eternaltwin/myhordes/myhordes-docker) into `myhordes-docker/`
(gitignored), with the game in `myhordes-docker/myhordes/`. See [source-map.md](source-map.md). Key paths:
- API controllers: `src/Controller/API/JSONv1Controller.php` (primary), `XMLv2Controller.php`
- Entities: `src/Entity/` — `Town.php`, `Citizen.php`, `Inventory.php`, `Item.php`, `Building.php`, `Zone.php`
- Services: `src/Service/` — `TownHandler.php`, `CitizenHandler.php`, `InventoryHandler.php`
- Auth listener: `src/EventSubscriber/APIRequestListener.php`

## Tech stack

- Python 3.10+
- `mcp` (Anthropic MCP SDK / FastMCP), pinned below 2
- `httpx` (async HTTP client)
- `python-dotenv` (environment management)
