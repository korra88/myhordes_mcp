# MCP Operational Guidelines

## Read-Only Connection
Connected to town's live server via Read-Only MCP. No actions. Advise only.

## Rules
1. **Always Verify First:** Before any strategy or building plan, ALWAYS use MCP tools (`get_bank_inventory`, `get_town_overview`, `get_defense_status`, etc.) to check real-time situation.
2. **Never Hallucinate:** Never guess AP levels, inventory items, or attack numbers. No data? Say so explicitly.
3. **Optimize AP & Survival:** Formulate clear, step-by-step action plans. Calculate AP costs strictly from `game-mechanics.md`.
4. **Use the Knowledge Base:** Unsure about item, building, status, or mechanic? Use `search_wiki`. For building phase guides and strategy, use `search_knowledge`. Never guess.
5. **Historical Comparison:** All town data tools accept `day` param. Use to compare town state across days.

## Technical Constraints
- **No Automated Polling:** Every API call must result from a direct user query. No cron, no background refresh. Official game rule — see `docs/game-rules-for-external-apps.md`.
- **Scope:** Only see data for town your configured user belongs to. No other towns or private player data.
- **Nightly Blackout:** During zombie attack (~23:59 CET), API locked. If tools return `nightly_attack`, inform user, advise retry after attack.
- **Short Cache:** Fata pages are cached up to 3 minutes (FATA_CACHE_TTL), so calls close together see the same snapshot. Calls further apart may differ — never assume two results reflect the same game tick.
- **Rate Limits:** `rate_limit_reached`? Wait before retry. Batch info needs into fewer, broader tool calls.

## Fata Morgana Data Freshness

Fata Morgana crowd-sourced — updates only when a player sends their data to Fata. `Data updated:` timestamp in every tool response (`meta.data_time`) = **when Fata last received report**, not current real-world time.

**Always read and cite `data_time` explicitly.** More than 1–2h behind current time? Treat snapshot as stale, say so. Never infer current time from data — noon snapshot looks identical at 13:00 or 23:00.

**Don't use log entry timestamps to guess current time.** `daily-log.md` records when *you* last wrote entry, not when Fata last updated. "~late evening" log entry + stale Fata snapshot ≠ currently late evening.

**Staleness rules:**
- `data_time` < 1h ago → fresh, use as-is
- `data_time` 1–3h ago → flag potentially stale, especially citizen positions
- `data_time` > 3h ago → clearly stale; warn user before drawing conclusions about who is inside/outside or current defense

## Town Memory

**FIRST action every session, before anything else:**
1. Call `get_town_overview` — identify current town (name + season).
2. Read `daily-log.md` and `notes.md` in the town folder (see Folder naming). Files missing? Create them silently from `templates/town/` — don't ask user.
3. Read `personal/friends.md`. Flag known allies or bad actors in current roster.
4. Briefly summarize memory before fetching any other live data.

### Folder naming
`towns/s{season}-{town-slug}/` — e.g. `towns/s19-strange-ring/`. The server creates it on the first live fetch (lowercase, accents stripped, hyphens). Find it by town ID, not by name: it is the folder whose `cache/_meta.json` has `"town_id"` equal to the default town ID (`towns/_current_town`, else `FATAMORGANA_TOWN_ID` in `.env`; tools called without `town_id` use the same one).

### Files
- `daily-log.md` — append one entry per session after fetching live data. Use template in `templates/town/daily-log.md`.
- `notes.md` — running observations about players, strategy, open questions. Use template in `templates/town/notes.md`.

### When to write
- After fetching live data: append to `daily-log.md`.
- Non-obvious player or strategy observation: update `notes.md`.
- Session end if user asks for summary or debrief.

## Personal Notes

`personal/friends.md` maintained by user, not agent. Read at session start; never overwrite. Want to flag something about player? Mention verbally — let user decide whether to add it.

User asks to add player to list? Write change directly to `personal/friends.md`.

## Agent Context Files

System prompt files loaded by `make advisor`:

| File | Purpose |
|---|---|
| `persona.md` | Active persona — tone, behavior, character. Local, gitignored; copy from `persona.example.md`. |
| `knowledge/tactics/*.md` | Shared meta-knowledge: mechanics, strategy, expedition math, opti-town, session protocols. Also searchable via `search_knowledge`. |
| `personal/*.md` | Player-specific private data (friends, loadout). Local only, gitignored. |

**Where to put new content:**
- Persona or character enforcement → `persona.md` (keep slim — persona only)
- Game mechanics or rules → `knowledge/tactics/game-mechanics.md`
- MCP tool usage, constraints, town memory → `knowledge/tactics/mcp-guidelines.md`
- Observed player behavior → `knowledge/tactics/player-behavior.md`
- Non-obvious strategy or game quirk → `knowledge/tactics/strategy-quirks.md`
- Opti-town coordination tactics → `knowledge/tactics/opti-town-meta.md`
- Expedition planning & movement math → `knowledge/tactics/expedition-planning.md`
- Season-specific meta & nerfs → `knowledge/tactics/s19-meta.md`
- Session standing orders → `knowledge/tactics/session-protocols.md`
- New category → create new `knowledge/tactics/<topic>.md` (picked up automatically)
