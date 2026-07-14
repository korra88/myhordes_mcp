---
name: myhordes-close-day
description: Finalize the previous MyHordes day's log using the current morning MCP snapshot (post-attack state). Trigger on "close the day", "finalize day", "wrap up yesterday", "night outcome".
platforms: [linux]
---

# MyHordes — Close Day

The full, authoritative workflow lives in the project source of truth:
**`.claude/commands/close-day.md`** (relative to the gateway's working directory,
the `myhordes_mcp` repo).

Do this now:

1. `read_file` `.claude/commands/close-day.md`.
2. Follow every step exactly. MCP tool names are called directly; file reads/writes
   use `read_file` / `write_file`.
3. **Memory discipline:** when writing any log/memory markdown, NEVER patch — rewrite
   the ENTIRE file with `write_file`, preserving every existing line, and read it back
   to confirm nothing was lost.

Re-read the command file each invocation so you follow the current version.
