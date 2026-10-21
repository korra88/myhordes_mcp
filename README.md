# MyHordes MCP Server — AI Town Advisor

A **read-only** Model Context Protocol (MCP) server that exposes MyHordes game data to AI assistants, helping players optimize their town strategy. Unofficial fan project, not affiliated with MyHordes or Eternaltwin.

> **Anti-botting policy:** This server implements **read-only operations only**. No write/action endpoints (moving, taking items, spending AP) will ever be added. No automated/scheduled API polling — all requests are triggered by user queries only. See [game rules](docs/game-rules-for-external-apps.md).

Live town data comes from [Fata Morgana](https://fatamorgana.md26.eu) (no account or API key needed, just your town ID), attack statistics from [Gest'Hordes](https://gesthordes.fr). The advisor runs in [Claude Code](https://claude.com/claude-code).

## Quick start

You need Python 3.10+, [Claude Code](https://claude.com/claude-code) and your town's Fata Morgana ID
(the number in your town's Fata link, e.g. `https://beta.fatamorgana.md26.eu/map/12345`).

```bash
# 1. Install
git clone https://github.com/korra88/myhordes_mcp.git && cd myhordes_mcp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 2. Pick your town (writes towns/_current_town; switch any time, no restart needed)
cp .env.example .env
make town TOWN=12345

# 3. Give the advisor a voice (yours to edit)
cp persona.example.md persona.md
```

4. Register the server with Claude Code: create `.mcp.json` in the repo root, with your absolute path.

```json
{
  "mcpServers": {
    "myhordes": {
      "type": "stdio",
      "command": "/absolute/path/to/myhordes_mcp/.venv/bin/python",
      "args": ["main.py"],
      "cwd": "/absolute/path/to/myhordes_mcp"
    }
  }
}
```

5. Start the advisor and ask something:

```bash
make advisor     # Claude Code with persona.md + knowledge/tactics/*.md + personal/*.md as system prompt
```

- *"What's the town status?"* → `get_town_overview`
- *"Will we survive tonight's attack?"* → `get_defense_status`
- *"Safest path to [-7|5] for Alice and Bob?"* → `find_expedition_path`
- *"What do I need to bring to reach [-1|15] and back?"* → `plan_expedition_supplies`
- *"What should we build today?"* → `/build-plan`

`claude mcp list` should show `myhordes` as connected. Settings are in `.env` (see
[.env.example](.env.example)): all optional once the town is set.

## Tools

| Tool | Source | Description |
|------|--------|-------------|
| `get_town_overview` | Fata Morgana | Town snapshot: gate, defense, water, citizens, attack estimate, trapped warnings. Optional `day`. |
| `get_citizen_positions` | Fata Morgana | Who's inside/outside, where, last known CP, plus death log. Optional `day`. |
| `get_citizen_cp` | Fata Morgana (CP log) | Every citizen's Control Points: last and best value seen, with day and zone. |
| `get_defense_status` | Fata Morgana + Gest'Hordes | Defense breakdown, attack estimates and actual attacks, survival assessment. Optional `day`. |
| `get_bank_inventory` | Fata Morgana | Bank summary by strategic group (`detail='full'` for every item). Optional `day`. |
| `get_buildings` | Fata Morgana | Built today / history / available buildings. |
| `get_build_options` | Fata Morgana | Buildable buildings ranked with def/AP, def/water, def/nuts-and-bolts, bank availability, and the situation (buffer, water ratio, AP budget, multiplier gap). |
| `get_blueprint_order` | Fata Morgana | Which blueprints in the bank to read first, which to hold (parent missing) and which would be wasted, with the odds of a normal blueprint taking a ruin building. |
| `get_construction_history` | Fata Morgana + Gest'Hordes | Day-by-day paid AP vs budget, alive, attack, deaths, free vote upgrades. |
| `get_town_changes` | Fata Morgana (snapshots) | Movements with AP, bank deposits/withdrawals, constructions, AP spent moving today, warnings — since the previous check, the day start or a time. |
| `get_night_report` | Fata Morgana + Gest'Hordes | One night: survived/failed, defense vs attack, alive before/after, deaths with cause and position. |
| `get_expedition_roster` | Fata Morgana | Outside citizens by tile with ruin names and class icons, scrappers, reconciliation with an expedition list. |
| `map_bank_to_dump_sheet` | Fata Morgana | Bank mapped onto Garbage Dump sheet rows (aliases, broken, emptied weapons). |
| `get_scout_map` | Fata Morgana | Zombies seen today (danger) and older counts by day, plus tonight's global respawn check. |
| `get_zone_details` | Fata Morgana | Desert overview (ground items grouped like the bank, ruins, who is outside); `item=` to locate an item; a box for zone detail; one zone for its reach from town. |
| `plan_expedition_supplies` | Fata Morgana + game rules | What to carry and where to drink, eat or take a drug along a route: fewest slots, no wasted AP, home not thirsty; platform teleport and Labyrinth included. |
| `find_expedition_path` | Fata Morgana | CP-aware safest/shortest path (`party="A, B"` takes the party's CP from the CP log); `step_table=True` adds AP/EP and thirst counter per move. |
| `get_attack_forecast` | Gest'Hordes | Theoretical attack curve, actual and estimated attacks, defence per day. |
| `get_attack_distribution` | Gest'Hordes | Historical attack statistics across towns per day. |
| `search_wiki` | Wiki | Search items, buildings, ruins, skills, statuses, and strategy guides from en.mhwiki.org (needs the [offline wiki](docs/wiki.md)). |
| `list_wiki_categories` | Wiki | List available wiki categories. |
| `search_knowledge` | Knowledge | Search curated advisor KB — building phase guides, strategy, mechanics. |

Every tool takes an optional `town_id`; without it, the default town is used
(`towns/_current_town`, else `FATAMORGANA_TOWN_ID` in `.env`; the Discord bot first looks for the asking person's own `towns/_user_towns/<discord id>`).

## Skills

Slash commands for Claude Code (`.claude/commands/`). The advisor also starts them from plain requests.

| Command | What it does | Say e.g. |
|---|---|---|
| `/build-plan` | Today's construction queue from live state and bank | "what should we build today?" |
| `/inspect-town` | Snapshot of movements, AP spent, bank changes and warnings, written to the day log | "take a town snapshot" |
| `/close-day` | Finalizes yesterday's log with the night's outcome (`backfill` closes every missing day) | "close the day" |
| `/building-report` | Day-by-day construction throughput report | "how much AP did we spend building?" |
| `/expedition-report` | Audits an expedition list (BBCode) or builds one: who is outside, unlisted, scrapping | "check the expedition list" |
| `/update-garbage-dump-list` | Writes the bank into a coalition Garbage Dump Google Sheet (needs a Google Sheets connection) | "update the dump list" |

The skills keep their logs in `towns/` (gitignored): one folder per town with a daily
log, a report per day and the server's data archive. See [docs/town-logs.md](docs/town-logs.md),
including how to keep them in a private git repo.

## Optional

- **Offline wiki** for `search_wiki`: [docs/wiki.md](docs/wiki.md).
- **Discord bot** answering in a channel: the listener used here is private, but any MCP-capable bot can serve the same tools — [docs/discord.md](docs/discord.md).
- **Developing** the server (layout, key files, game source): [docs/development.md](docs/development.md).

## Credits

This project only reads data that players already share on these sites. Thanks to:

- [MyHordes](https://myhordes.eu) and the [Eternaltwin](https://eternaltwin.org) team, for keeping the game alive
- [Fata Morgana](https://fatamorgana.md26.eu), the town spy and map tool that provides most of the live data
- [Gest'Hordes](https://gesthordes.fr), for attack and defence statistics
- [MHWiki](https://en.mhwiki.org), source of the offline wiki search

Requests to Fata Morgana and Gest'Hordes carry the User-Agent
`myhordes-mcp/1.0 (+https://github.com/korra88/myhordes_mcp; install=<random id>)`, so their
admins can see where the traffic comes from. Set `MCP_CONTACT` in `.env` to add a way to reach you.

## License

[MIT](LICENSE)
