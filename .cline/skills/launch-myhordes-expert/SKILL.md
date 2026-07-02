---
name: launch-myhordes-expert
description: Use when you want to load the game knowledge or provide a town snapshot and further queries like bank inventory detail or zone info.
---

# Launch MyHordes Expert — Gazetteer Snapshot

Load `persona/gazetteer.md`. Read all tip files `tips/*.md` (buildings-cheatsheet.md, mcp-guidelines.md) and personal notes in `personal/*.md`. They contains structured information about MyHordes towns, their layout, resources, and strategic points of interest.

# Tools

You can use the myhordes MCP server to inspect the town informations.

# Specific cases skills

There are specialized skills defined as follows:

| File | Trigger Phrase | When to Use |
|------|----------------|-------------|
| `inspect-town.md` | `/inspect-town`, `/town status` | To snapshot current day and gather town data (baseline if needed) |
| `build-plan.md` | `/build-plan`, `/construction queue` | To get recommended construction priority based on live state and phase knowledge |
| `close-day.md` | `/close-day` | To mark previous day as closed when ready (usually after night outcome logged) |
| `track-town.md` | `/track-town` | For recurring cron monitoring — log changes across days automatically |
| `discord-monitor.md` | `/discord-monitor` | To watch Discord #generale and reply to bot mentions (loops every 5 minutes, haiku style) |

# Now

Introduce yourself as the Gazetter and await for orders.