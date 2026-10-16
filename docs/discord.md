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
  about a given town; without it the tools use the default town.
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
