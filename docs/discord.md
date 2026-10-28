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
  `discord-listener.example.toml`); never a wildcard, so a new tool is opt-in.
- **Town per conversation:** pass `town_id` to every tool when the conversation is
  about a given town; without it the tools use the default town. A bot that sets
  `LISTENER_USER_ID=<discord id>` in the server's environment gets per-person
  defaults (see "Default town per person").
- **Answer only on demand** (a mention or a message to the bot), never on a timer:
  the game forbids scheduled polling, and Fata agreed to on-demand use only.
- **Limit who can use it** and how often, since every turn costs model usage.

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

Answers are visible only to the person who ran the command (except `/new`). Only `allow_users` may use
them; anyone else is told "You are not on this bot's list; ask @<maintainer> to be added."
(`[dm] maintainer`), so `/help` doubles as "am I allowed?". To change the help, edit `prompts/discord-help.md` and restart the listener (the
file is read once at start); the text is not read by the model, so keep it in step with
what the bot can do. The server needs the `applications.commands` scope, and the
Developer Portal must have no Interactions Endpoint URL.

## Direct messages and long sessions

Both are configured in `discord-listener.toml` (`[dm]`, `[sessions]`) and explained
in `../discord_mcp/README.md` ("Sessions that fit the cache", "Direct messages").

- **DMs** are off by default. When on, each person in `allow_users` sees the text of
  `prompts/discord-dm-disclaimer.md` on their first DM (`{maintainer}` becomes a
  mention of the `maintainer` id) and the bot answers only after they add the check
  mark. What they wrote while waiting is answered as one turn, as in a thread.
  Removing the check mark silences
  the bot. In a DM the bot can write `towns/_bot/` (memory, feedback) like in a thread.
  The check mark is a conscious step, so the bot never adds it.
- **Sessions**: a thread or DM idle for 55+ minutes whose context reached 128000
  tokens is not resumed. A thread gets a fixed English notice asking for a new thread;
  a DM starts a fresh session by itself, carrying the latest ~4000 tokens of talk
  (`carry_tokens`). Counters are kept in a state file
  outside the repo.
- Add `[sessions]` and `[dm]` by hand to the local `discord-listener.toml` on the Pi
  (it is gitignored), and restart the listener: prompts and toml changed.

## Memory and feedback log

Both live in `towns/_bot/`, inside the listener's write permission (`towns/**`), so
they need no extra permission and, if `towns/` is a git repo, get history and backup
with the town logs.

- **Memory** (`memory.md`, always on). Facts readers ask the bot to keep across
  threads, e.g. which in-game player a Discord user is. The listener pastes it into
  the first prompt of each thread (`first_turn_files` in the toml), so it costs no
  tool call and does not touch the cached system prompt. The bot writes it only on
  an explicit "remember"/"forget". Rules and line format: `prompts/discord.md`,
  "Memory".
- **Feedback log** (`feedback/`, opt-in). Add `prompts/discord-feedback.md` to
  `append_system_prompt_files` and restart the listener. The bot then writes one file
  per complaint, correction, missing tool or tool problem; it never reads them back,
  so an entry cannot steer it. Review them in the terminal with `/review-bot-feedback`,
  which proposes prompt and tool changes and moves processed entries to
  `feedback/reviewed/`.

Memory is the one place where text from a thread comes back in later threads: keep
`allow_users` to people you trust, and check it now and then (`/review-bot-feedback`
does). The bot edits `memory.md` itself: if you edit it by hand on another machine,
commit and push right away so the two copies do not diverge.
