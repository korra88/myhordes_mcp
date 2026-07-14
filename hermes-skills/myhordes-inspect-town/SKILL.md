---
name: myhordes-inspect-town
description: Seed baseline if needed and run a MyHordes town snapshot — movements, AP spend, bank changes — writing to the daily log. Trigger on "track town", "snapshot town", "take a town snapshot", "update town state".
platforms: [linux]
---

# MyHordes — Inspect Town

The full, authoritative workflow lives in the project source of truth:
**`.claude/commands/inspect-town.md`** (relative to the gateway's working directory,
the `myhordes_mcp` repo).

Do this now:

1. `read_file` `.claude/commands/inspect-town.md`.
2. Follow every step exactly. MCP tool names are called directly; file reads/writes
   use `read_file` / `write_file`.
3. **Memory discipline:** when writing any log/memory markdown, NEVER patch — rewrite
   the ENTIRE file with `write_file`, preserving every existing line, and read it back
   to confirm nothing was lost.

Re-read the command file each invocation so you follow the current version.
