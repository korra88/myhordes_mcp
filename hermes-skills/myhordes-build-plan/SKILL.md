---
name: myhordes-build-plan
description: Recommend today's MyHordes construction queue from live town state, bank inventory, and phase-appropriate building priorities. Trigger on "build plan", "what to build today", "construction queue", "building recommendations".
platforms: [linux]
---

# MyHordes — Build Plan

The full, authoritative workflow lives in the project source of truth:
**`.claude/commands/build-plan.md`** (relative to the gateway's working directory,
the `myhordes_mcp` repo).

Do this now:

1. `read_file` `.claude/commands/build-plan.md`.
2. Follow every step in it exactly. Tool names in that file are MyHordes MCP tools
   (`get_defense_status`, `get_bank_inventory`, `get_buildings`, `search_knowledge`)
   and are called directly. File reads it mentions (e.g. `tips/…`, `towns/…`) use
   `read_file`.
3. Produce the Build Plan output block defined at the end of that file.

Do not improvise the priority logic — it is precise and lives in that file. Re-read it
each invocation so you always follow the current version.
