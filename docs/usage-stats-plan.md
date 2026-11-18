# Usage stats of the Discord bot: plan

Status: **approved 2026-11-18, implemented (not committed, not deployed).** Two repos: `discord_mcp` (the generic
Discord listener, `../discord_mcp`) and `myhordes_mcp` (this repo).

## Goal

The maintainer reads, from Discord, how the bot is used over the last **24 h, 48 h and 7 days**:

- Claude turns (answered / failed), sessions (distinct threads and DMs, new vs resumed),
  distinct users per tier (trusted / public);
- tokens: input (fresh), cache read, cache written, output; Claude's cost estimate
  (`total_cost_usd`, notional on a subscription);
- tool calls, by category (expeditions, camping, construction, knowledge, town, other) and the
  top tools;
- Fata Morgana requests: real HTTP requests only (not cache/archive hits), by origin (bot turn,
  refresh timer, local) and outcome (ok, 429, other error).

## Decisions (user, 2026-11-18)

- One SQLite file **outside every repo**: `~/.myhordes_mcp/usage_stats.sqlite` on the Pi.
  Path overridable by env `USAGE_STATS_DB` (tests, PC). The directory is created on first write.
- `/stats` is registered **globally** like the other commands (so it also works in DMs) and
  **answers only the maintainer**: everyone else gets a short refusal. The user id lives in the
  Pi's `discord-listener.toml` (gitignored), never in a repo.
- Reading the stats on Discord doubles as a backup of the numbers; no other export.
- Keep it simple: no new Discord endpoints, no per-guild registration.

## Facts measured (2026-11-18)

- The listener already logs one `turn.<kind>` line per Claude run (`listen.py` ~799:
  `usage_numbers` + `context_tokens_of`), only to journald. journald on the Pi holds 5.7 MB,
  oldest `turn.*` line 2026-11-13 12:01, 24 lines: no history worth importing. Stats start at
  deploy.
- `claude -p --output-format stream-json`: the final `result` event has `usage`
  (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`),
  `total_cost_usd`, `num_turns`, `modelUsage`. Tool calls are `assistant` events whose
  `message.content[]` has blocks `{"type": "tool_use", "name": "mcp__myhordes__…", "id": …}`.
  One `assistant` event per content block; ids repeat (see `context_tokens_of`): count each
  `tool_use` block id once. Sub-agent calls have `parent_tool_use_id`: count them too (they are
  tool calls the bot made) but they are rare.
- Slash commands: `[[commands]]` tables in the toml (`listener.py` `_load_command`,
  `CommandConfig`), `argv` programs run by `listen.py` `run_command` with cwd = the claude cwd
  (`myhordes_mcp`), env = `child_env(os.environ, user_id)` (sets `LISTENER_USER_ID`). Output =
  stdout, cut to Discord's limit by `_fit`. Any allowed user can run any command today.
- Every Fata HTTP request goes through `src/myhordes_mcp/fata/client.py` `_load` (the
  `httpx` GET). The MCP server is started by `claude` for each bot turn (its env has
  `LISTENER_USER_ID`); the refresh timer runs `fata/refresh.py`; on the PC it runs from
  Claude Code / scripts.

## Design

### Shared rules for the SQLite file

- `sqlite3` stdlib only. Open per write, `PRAGMA journal_mode=WAL`, `busy_timeout=5000`,
  `CREATE TABLE IF NOT EXISTS` by whoever writes the table. Several processes write at once
  (listener, MCP servers of concurrent turns, the timer): WAL + busy timeout handle it.
- **A stats failure never breaks anything**: every write is wrapped, logs one warning line,
  and returns. Never store message text, prompts, answers or tool arguments. Ids only
  (Discord user/thread/DM ids, town ids): the file stays private on the Pi.
- Timestamps: `ts` INTEGER unix seconds UTC.

### discord_mcp (generic, knows nothing of MyHordes)

1. `[stats]` table in the toml: `db = "~/.myhordes_mcp/usage_stats.sqlite"` (path, `~`
   expanded; absent = no stats written). Add to `Config`, loader, example toml, README.
2. `usage_numbers` also returns `input_tokens` and `output_tokens` (from `result.usage`), so the
   journald line has them too.
3. New module `stats.py` (listener side): `record_turn(db, ts, kind, thread, user, tier, model,
   resume, wall_s, input_tokens, output_tokens, cache_read, cache_created, cost_usd, num_turns,
   context, tools: list[str])`. Tables:
   - `turns(id INTEGER PRIMARY KEY, ts, kind, place, user, tier, model, resumed INTEGER,
     wall_s REAL, input_tokens, output_tokens, cache_read, cache_created, cost_usd REAL,
     num_turns, context)` — `place` = thread id or DM channel id (= the session's place);
     `resumed` 1 when the run resumed a session.
   - `tool_calls(turn_id, ts, tool)` — one row per `tool_use` block id.
   A function `tool_names(events)` in `listener.py` next to `context_tokens_of` extracts the
   names; `ClaudeResult` (or the parse) carries them.
   Call it right after the existing `log("turn." ...)` in `listen.py`.
4. Per-command allow list: optional `users = ["id", …]` in a `[[commands]]` table
   (`CommandConfig.users: tuple[str, ...] | None`). When set, any other user gets an ephemeral
   "This command is for the bot's maintainer." and the program is not run (log
   `command.refused`). Unset = today's behaviour. The command stays registered globally.
5. Tests (pytest, `tests/`): tool-name extraction on a recorded stream (ids repeated across
   events), `record_turn` writes and reads back (temp db), concurrent writers (two processes or
   threads) do not raise, a stats failure (unwritable path) does not raise, `users` refusal
   path in `test_commands.py`, config errors for bad `users` / `[stats]`.

### myhordes_mcp

1. `src/myhordes_mcp/utils/usage_stats.py`: `db_path()` (env `USAGE_STATS_DB`, default
   `~/.myhordes_mcp/usage_stats.sqlite`; `USAGE_STATS_DB=off` disables), `record_fata_call(town,
   day, outcome, status, ms, origin)`. Table `fata_calls(ts, town, day, origin, outcome,
   status, ms)`: `outcome` ok | rate_limited | http_error | network_error | bad_data; `origin`
   = `bot` when `LISTENER_USER_ID` is set, `timer` when `fata/refresh.py` set env
   `USAGE_STATS_ORIGIN=timer` (or a module flag it sets before fetching), else `local`.
2. `fata/client.py` `_load`: record once per real HTTP attempt (after the response or the
   exception), never for archive/cache hits. No other change to the request path (CLAUDE.md:
   never add another HTTP path to Fata).
3. `scripts/usage_stats.py` (stdlib only: run by the listener with system `python3`, like
   `scripts/set_town.py`): reads the db and prints the report. Missing db or table = "no data
   yet" for that part. Optional `--db PATH`.
4. Report (plain Discord markdown, **≤ 1900 chars**, three columns 24h | 48h | 7d), e.g.:
   ```
   **Bot usage** (since <first ts>, now <Paris time>)
   ```text
                   24h    48h     7d
   turns ok         12     30     95
   turns failed      0      1      3
   sessions          5     11     40   (new 3 · resumed 2 in 24h)
   users             4      7     15   (trusted 2 · public 2 in 24h)
   tokens in       1.2M   2.9M    11M   (fresh+cache read+cache written)
     cache read    1.1M ...
   tokens out       45k   110k   400k
   cost est.      $4.10  $9.80   $33
   tools            80    190    700
     expeditions    20 ...
     camping         5 ...
     construction   10 ...
     knowledge      15 ...
     town           25 ...
     other           5 ...
   fata HTTP        14     30    100   (bot 10 · timer 2 · local 2 in 24h)
     errors          0      0      1   (429: 0)
   ```
   top tools 7d: get_town_overview 120, find_expedition_path 60, …
   ```
   Categories by tool name (strip `mcp__<server>__`): expeditions = find_expedition_path,
   plan_expedition_supplies, plan_kill_route, get_expedition_roster; camping =
   get_camping_odds; construction = get_build_options, get_blueprint_order, get_buildings,
   get_construction_history; knowledge = search_wiki, list_wiki_categories, search_knowledge;
   town = get_town_overview, get_citizen_positions, get_citizen_cp, get_defense_status,
   get_bank_inventory, get_scout_map, get_zone_details, get_town_changes, get_night_report,
   get_attack_distribution, get_attack_forecast, map_bank_to_dump_sheet; other = everything
   else (built-in tools like Read/Grep, memory tools). Keep the mapping in one dict.
5. Tests: `tests/usage_stats_checks.py` (no pytest in this venv; plain asserts like
   `tests/camping_checks.py`): build a temp db with rows at known ages, check the windows,
   categories, the length cap, empty db. Goldens must stay `208 same`: the golden harness must
   not write the real db — set `USAGE_STATS_DB=off` inside `tests/offline.py` (or point it at
   the temp dir) and check `_files` is unchanged.
6. Docs: README/development.md one line each; CLAUDE.md "Current state" one line (`/stats`
   maintainer command, db path).

### Pi config (by the maintainer session, not the agent)

```toml
[stats]
db = "~/.myhordes_mcp/usage_stats.sqlite"

[[commands]]
name = "stats"
description = "Bot usage: turns, tokens, tools, Fata requests (maintainer only)"
argv = ["python3", "scripts/usage_stats.py"]
users = ["<maintainer id>"]
ephemeral = true
timeout_seconds = 20
```
Plus `discord-listener.example.toml` in this repo with the same block and a placeholder id.
Deploy: commit both repos, push, `~/bin/pi-myhordes-update`, edit the Pi toml, restart the
listener (the update script restarts it), run `/stats` from Discord.

## Out of scope

Per-guild command registration, Discord permissions, importing journald history, charts,
attributing Fata requests to the tool that caused them.
