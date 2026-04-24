Monitor Discord `#generale` for unanswered mentions of the Town Elder bot and reply using game knowledge.

Run once immediately. Pass `loop` to start continuous monitoring via `/loop`.

## Channel config

- Guild ID: `GUILD_ID`
- Channel ID: `CHANNEL_ID` (`#generale`)
- Bot user ID: `BOT_USER_ID` (Town Elder#9092)

## Step 1 — Login

Call `discord_login`. If already logged in, continue.

## Step 2 — Read messages

Call `discord_read_messages(channelId="CHANNEL_ID", limit=20)`.

## Step 3 — Find unanswered mentions

A message requires a reply if ALL of these are true:
- Contains `<@BOT_USER_ID>` (bot mention)
- Was NOT authored by the bot itself
- No subsequent message from the bot (`author.bot == true`) exists after it in the list

Collect all such messages.

## Step 4 — Reply to each

For each unanswered mention:

1. Extract the question from the message content (strip the mention tag).
2. Look up the answer:
   - Game items, buildings, stats, statuses → `search_wiki(query=...)`
   - Strategy, construction phases → `search_knowledge(query=...)`
   - Live town data (defense, bank, citizens) → appropriate `get_*` MCP tool
   - General game rules → `search_wiki` or knowledge
3. Compose a concise reply. Tag the asker with `<@{author.id}>`. Lead with the direct answer, add context only if useful. Stay in Desert Veteran character — terse, direct, no fluff.
4. Call `discord_send(channelId="CHANNEL_ID", message=...)`.

If no unanswered mentions: log `no new mentions` and stop.

## Step 5 — Report

Tell the user:
- How many messages checked
- How many mentions found and answered
- Summary of each reply sent (question → one-line answer)

## Loop mode

If `$ARGUMENTS` contains `loop`: after Step 5, do NOT stop. The `/loop` skill handles re-scheduling — just complete the task. The outer loop will re-invoke this skill at its own interval.
