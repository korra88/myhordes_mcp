---
name: myhordes-building-report
description: Produce the MyHordes town's day-by-day construction throughput report (AP spent, buildings raised over time). Trigger on "building report", "construction report", "how much AP we spent", "build history".
platforms: [linux]
---

# MyHordes — Building Report

The full, authoritative workflow lives in the project source of truth:
**`.claude/commands/building-report.md`** (relative to the gateway's working directory,
the `myhordes_mcp` repo).

Do this now:

1. `read_file` `.claude/commands/building-report.md`.
2. Follow every step exactly. MCP tool names are called directly; file reads use
   `read_file`.
3. Produce the report output block defined in that file.

Re-read the command file each invocation so you follow the current version.
