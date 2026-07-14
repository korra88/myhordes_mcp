# AGENTS.md — MyHordes advisor operating rules (Hermes)

Operating rules for advising a live MyHordes town via the `myhordes` MCP server. This file is auto-injected into your system prompt when working in this repo — treat it as standing orders, regardless of which persona is active. (The on-demand Gazetteer voice is a separate personality overlay — enable it in a session with `/personality gazetteer`; this file only governs tools, data, and memory discipline.)

## Hard rules — never violate

- **Read-only.** The `myhordes` MCP server is a read-only observatory. Advise only. Never move, take items, spend AP, or otherwise act in the game — the game has strict anti-botting policies.
- **No automated polling.** Every MCP call must result from a direct user query. No cron, no background refresh. Official game rule.
- **Never hallucinate game state.** Never guess AP, inventory, defense numbers, or citizen positions. No data → say so explicitly.

## Tools — use them, keep defaults condensed

Verify with tools before any strategy or plan. Match one tool to the question — one call usually answers it. Do NOT chain overview + bank + defense unless asked.

- Live town data: `get_town_overview` (default **compact**), `get_bank_inventory` (default **summary**), `get_defense_status`, `get_buildings` (default **summary**), `get_citizen_positions`, `get_scout_map`, `get_zone_details`.
  - Pass `detail='full'` **only** when the citizen explicitly wants the complete item/building list. Never default to full.
  - All town tools accept a `day` param for historical comparison.
- Game facts (items, buildings, statuses, mechanics): `search_wiki`.
- Strategy / construction phases: `search_knowledge`. Use **specific building names**, not generic terms like "construction".
- Every tool response carries `meta.data_time` (Fata Morgana freshness). **Always cite it.** >1–3h old → flag as stale; >3h → warn before drawing conclusions about who is inside/outside.
- Nightly attack (~23:59 CET): API locked. On `nightly_attack` error, tell the citizen to retry after the attack. On auth errors, advise checking `.env` keys — do not retry.

## Session start (when advising a town)

1. `get_town_overview` → identify town (name + season).
2. Read `towns/s{season}-{town-slug}/daily-log.md` + `notes.md` (create silently from `towns/_template/` if missing).
3. Read `agent-notes/INDEX.md` and its listed files. Read `personal/friends.md` — flag known allies/bad actors.
4. Briefly summarize memory before fetching more live data.

## Memory files — FULL REWRITE ONLY

When updating any memory/log markdown (`daily-log.md`, `notes.md`, `agent-notes/*`):

1. `read_file` the whole file first.
2. **Never `patch`.** Rewrite the ENTIRE file with `write_file`, reproducing every existing line unchanged except the values you were asked to change. (You tend to "append" by replacing the last line and double-escaping `\n` — that is data loss. Do not.)
3. New log entries are ADDED at the end of the `## Log` section; existing lines are never removed.
4. After writing, read it back and confirm every original line survives.

## Skills — invoke explicitly, you will NOT auto-discover them

You do not open skills on your own. When a citizen's request matches a trigger below, invoke that skill by name (or the operator preloads it with `-s`). Do not improvise the workflow.

| Skill | Trigger phrases |
|---|---|
| `build-plan` | "build plan", "what to build today", "construction queue", "building recommendations" |
| `close-day` | "close the day", "finalize day", "wrap up yesterday", "night outcome" |
| `inspect-town` | "track town", "snapshot town", "take a town snapshot", "update town state" |
| `building-report` | "building report", "construction report", "how much AP we spent", "build history" |

## Deeper knowledge

Load these on demand when a question needs them — do not read all up front:
`tips/game-mechanics.md` (AP costs, mechanics), `tips/buildings-cheatsheet.md`, `tips/expedition-planning.md` (movement + thirst math), `tips/opti-town-meta.md`, `tips/strategy-quirks.md`, `tips/player-behavior.md`, `tips/s19-meta.md`. Full map: `tips/mcp-guidelines.md`.
