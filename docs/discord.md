# Discord bot

The MCP server does not talk to Discord itself. Mentions in a Discord channel are
answered by a separate listener (`../discord_mcp`, **private, not published**) that runs
Claude Code with this server's tools, the same `persona.md`, `prompts/game-primer.md`
and `prompts/discord.md`.
The `make discord-*` targets, `templates/systemd/discord-listener.service` and the two
`discord-listener.*.example.*` files are the glue for that listener; without it, use
another bot as below.

## Using another bot

Nothing in the server is Discord-specific: any bot or agent that can talk to an MCP
server over stdio can use it. What the listener does, and another bot should too:

- **Start the server** as in `discord-listener.mcp.example.json`: `.venv/bin/python
  main.py` with the repo as working directory (absolute paths).
- **System prompt:** `persona.md` (voice), `prompts/game-primer.md` (core game rules,
  ~2k tokens, and which `search_knowledge` query answers what), `prompts/discord.md`
  (channel etiquette: short answers, tables in code blocks, how to name the town).
  Loading all of `knowledge/tactics/*.md` instead costs ~16k tokens and carries
  terminal-only instructions (town logs, `personal/`).
- **Allow only the read-only tools.** List them by name (see `allowed_tools` in
  `discord-listener.example.toml`); never a wildcard, so a new tool is opt-in. The
  three bot tools (`log_feedback`, `remember`, `forget`) write only fixed files in
  `towns/_bot/` and need `LISTENER_USER_ID` (and `LISTENER_CONTEXT=dm` for memory).
- **Town per conversation:** pass `town_id` to every tool when the conversation is
  about a given town; without it the tools use the default town. A bot that sets
  `LISTENER_USER_ID=<discord id>` in the server's environment gets per-person
  defaults (see "Default town per person").
- **Answer only on demand** (a mention or a message to the bot), never on a timer:
  the game forbids scheduled polling, and Fata agreed to on-demand use only.
- **Limit who can use it** and how often, since every turn costs model usage.

## Two tiers: trusted and public

The bot answers everybody in its channels, at two levels (`[public]` in
`discord-listener.toml`; mechanism in `../discord_mcp/README.md`):

| | trusted (`allow_users`) | public (everybody else) |
| --- | --- | --- |
| model | `sonnet` | `claude-haiku-5-5` (full id: the CLI alias `haiku` is Haiku 4.5) |
| turns per person per hour | 60 | 10 (`[public] max_turns_per_user_per_hour`) |
| writes | town logs (`inspect-town`, `close-day`) via `Write(./towns/**)` | none: `Write`/`Edit` stay denied; only the bot tools |
| DMs | yes | yes, found by the gateway when they write (see below) |

A turn runs at the **lowest tier among its authors**: one public person in a thread
makes that turn public (same session, resumed with the public model and tools), so a
public person cannot have a trusted thread write files for them. Both tiers share the
system prompt; `prompts/discord.md` "Other players" forbids verdicts on real players
(traitor, thief, lazy), measured necessary on Haiku. Why Haiku, with the numbers: the
2026-11-10 benchmark (`../claude-ollama-protocol/experiments/hordes-advisor/RESULTS.md`).

## Configure the listener

Copy the two example files (the copies are gitignored), then set `allow_users` and the
absolute paths:

```bash
cp discord-listener.example.toml discord-listener.toml
cp discord-listener.mcp.example.json discord-listener.mcp.json
```

`allowed_tools` in `discord-listener.toml` lists the tools the bot may call: add new
read-only tools there when the server gets them. The bot token lives in
`../discord_mcp/.env`.

## Run the listener

```bash
make discord-listen        # answer mentions until stopped
make discord-listen-once   # one poll cycle, for testing
```

To keep it running on a server (e.g. a Raspberry Pi), install it as a systemd user
service (`templates/systemd/discord-listener.service`, restarts on failure):

```bash
make discord-service-install     # install and start
make discord-service-disable     # stop
make discord-service-uninstall   # remove
journalctl --user-unit discord-listener -f   # logs
```

For it to start at boot without a login, run `sudo loginctl enable-linger $USER` once.
Run one listener per bot: two would both answer.

## Default town per person

The listener runs `claude` with `LISTENER_USER_ID` set to the Discord id of whoever
opened the conversation (the author of the message that opened the thread, or the
person in the DM), and the MCP server inherits it (no `env` block in the MCP JSON).
`resolve_town_id` then looks, in order, at: an explicit `town_id`,
`towns/_user_towns/<id>`, `towns/_current_town`, `FATAMORGANA_TOWN_ID`. The id must be
all digits, so it cannot name another path.

- **`/set-my-town 8212`**: the slash command (see [Slash commands](#slash-commands)); the
  listener runs `scripts/set_town.py --user <id> 8212` itself, no model involved. The town
  is required; to check it, ask the bot "which town am I on?".
- **Asking the bot** ("change my default town to 8212"): it writes only the
  requester's own file. It no longer writes `towns/_current_town`; the shared default
  changes only from the terminal (`make town TOWN=...`).
- **From the terminal**: `make town TOWN=8212 FOR=<discord id>` (or
  `python3 scripts/set_town.py --user <discord id> [<town id>]`); with no `TOWN` it
  shows that person's default.
- `towns/_user_towns/` lives in the private `towns/` repo and is committed with it.

## Slash commands

Declared in `discord-listener.toml` as `[[commands]]` (example in
`discord-listener.example.toml`); the listener registers them at start and answers them
itself, without Claude (mechanism: `../discord_mcp/README.md`, "Slash commands").

| Command | What it does |
| --- | --- |
| `/help` | Fixed English text from `prompts/discord-help.md`: what to ask, with examples. At most 2000 characters. |
| `/set-my-town <town>` | Sets the caller's default town (`towns/_user_towns/<id>`) through `scripts/set_town.py --user`. Answers with the town name, season and day when `towns/` holds that town, and the previous ID when it changed. |
| `/new` | DMs only, built into the listener (not in the toml; there whenever `[dm]` is on): starts a fresh DM conversation. Its answer stays visible in the DM, as the start of the new session. |

Answers are visible only to the person who ran the command (except `/new`). With `[public]`
on, everybody may use every declared command: declare nothing a stranger must not run.
Without it only `allow_users` may use them; anyone else is told "You are not on this bot's list; ask @<maintainer> to be added."
(`[dm] maintainer`), so `/help` doubles as "am I allowed?". To change the help, edit `prompts/discord-help.md` and restart the listener (the
file is read once at start); the text is not read by the model, so keep it in step with
what the bot can do. The server needs the `applications.commands` scope, and the
Developer Portal must have no Interactions Endpoint URL.

## Direct messages and long sessions

Both are configured in `discord-listener.toml` (`[dm]`, `[sessions]`) and explained
in `../discord_mcp/README.md` ("Sessions that fit the cache", "Direct messages").

- **DMs** are off by default. When on, each person in `allow_users` (and, with
  `[public]` on, anybody who writes to the bot: the gateway rings, the listener then
  reads that DM for `public_window_minutes`, at most `max_public_open` at once) sees the text of
  `prompts/discord-dm-disclaimer.md` on their first DM (`{maintainer}` becomes a
  mention of the `maintainer` id) and the bot answers only after they add the check
  mark. What they wrote while waiting is answered as one turn, as in a thread.
  Removing the check mark silences
  the bot. Memory exists only in DMs (see below).
  The check mark is a conscious step, so the bot never adds it.
- **Sessions**: a thread or DM idle for 55+ minutes whose context reached 128000
  tokens is not resumed. A thread gets a fixed English notice asking for a new thread;
  a DM starts a fresh session by itself, carrying the latest ~4000 tokens of talk
  (`carry_tokens`). Counters are kept in a state file
  outside the repo.
- Add `[sessions]` and `[dm]` by hand to the local `discord-listener.toml` on the Pi
  (it is gitignored), and restart the listener: prompts and toml changed.

## Old threads

Discord does not apply `auto_archive_duration` (measured: threads still active after
14 and 24 idle days), so the listener archives **its own** threads idle for
`[threads] archive_after_days` (default 7, `0` = off), once an hour. Archived, not
locked: writing in one reopens it and the bot answers as usual. Threads opened by
people are left alone. Log lines: `thread.archived`, `thread.archive_failed`.

## Memory and feedback log

Both live in `towns/_bot/` and are written only through MCP tools of this server
(`src/myhordes_mcp/bot/store.py`), never by the bot's own `Write`: the path, the format
and the author id (from `LISTENER_USER_ID`, set by the listener) are fixed in the
server. That is what lets the public tier run without `Write`/`Edit`.

- **Memory** (`memory/<discord id>.md`, one file per person, **DMs only**). Facts a
  reader asks the bot to keep, e.g. which in-game player they are. Tools `remember` /
  `forget`, refused by the server unless `LISTENER_CONTEXT=dm`. The listener pastes the
  reader's file into the first prompt of a DM session (`[dm] memory_file`), so it costs
  no tool call; threads get no memory. Cap 40 lines, one line per fact. Rules:
  `prompts/discord.md`, "Memory". The old shared `memory.md` is moved once with
  `make bot-memory-migrate` (idempotent; leaves `memory.md.migrated`).
- **Feedback log** (`feedback/`, opt-in). Add `prompts/discord-feedback.md` to
  `append_system_prompt_files` and `mcp__myhordes__log_feedback` to `allowed_tools`, then
  restart the listener. The bot logs one entry per complaint, correction, missing tool
  or tool problem with `log_feedback`; it never reads them back, so an entry cannot
  steer it. Review them in the terminal with `/review-bot-feedback`, which proposes
  prompt and tool changes and moves processed entries to `feedback/reviewed/`.

A memory file is the one place where text from a conversation comes back later, and
only in that person's own DMs. Check the files now and then (`/review-bot-feedback`
does). The bot edits them itself: if you edit one by hand on another machine, commit
and push right away so the two copies do not diverge.
