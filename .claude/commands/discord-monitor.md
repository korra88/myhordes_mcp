Monitor Discord `#generale` for unanswered mentions of the Town Elder bot and reply using game knowledge.

Run once immediately. Pass `loop` to start continuous monitoring via `/loop`.

## Tools

Use the myhordes MCP tools directly:
- `get_mentions(after_id)` — returns only bot-mention messages, filtered server-side
- `send_discord_message(message)` — sends reply as Town Elder bot

## Step 1 — Load state

Read `.discord-monitor-state.json` if it exists:
```json
{"last_message_id": "SNOWFLAKE_OR_NULL"}
```
Use `last_message_id` as `after_id` for `get_mentions`. If file missing or id null: call with empty `after_id`.

## Step 2 — Fetch mentions

Call `get_mentions(after_id=LAST_ID)`. Returns only messages mentioning the bot, authored by non-bot users.

## Step 3 — Answer each mention

For each mention:

1. Extract question (strip `<@BOT_USER_ID>` tag).
2. Look up answer:
   - Game items, buildings, stats, statuses → `search_wiki(query=...)`
   - Strategy, construction phases → `search_knowledge(query=...)`
   - Live town data → appropriate `get_*` tool. Keep the condensed defaults
     (`get_town_overview` → compact, `get_bank_inventory` → summary); pass
     `detail='full'` only if the asker explicitly wants the complete item list.
     One tool call usually answers the question — don't chain overview + bank + defense.
   - "what to build today", "build plan", "construction queue" → use Skill tool with `skill='build-plan'`
   - "building report", "construction report", "AP spent", "build history" → use Skill tool with `skill='building-report'`
3. Compose reply: tag asker with `<@{author_id}>`, lead with direct answer. Stay in the defined Persona character.
4. Call `send_discord_message(message=...)`.
5. **Log any issue** encountered while answering to `.discord-monitor-issues.log` (append, one line per issue):
   ```
   [YYYY-MM-DD HH:MM] ISSUE_TYPE | message_id=ID | detail
   ```
   Issue types: `TOOL_FAILURE` (MCP tool error), `NO_KNOWLEDGE` (search_knowledge returned no results),
   `FALLBACK` (had to answer without live data), `UNKNOWN_DATA` (missing field, e.g. unknown death),
   `SKILL_ERROR` (sub-skill failed). Only log when the issue actually affects reply quality.

If no mentions: skip to Step 4.

## Step 4 — Update state

Write highest message ID seen (from `get_mentions` result or previous state if no new messages) to `.discord-monitor-state.json`. Parse IDs from lines starting with `[ID]`.

## Step 5 — Report

Tell user: mentions found, replies sent, one-line summary per reply.

## Loop mode

If `$ARGUMENTS` contains `loop`: complete task and return. `/loop` handles re-invocation.
