# Handoff — Open Discord-Monitor Issues

Three issues surfaced during the first live discord-monitor session. Issues 1/2/6 (knowledge base
queries, resource requirements, issue log) were already fixed. These three remain.

---

## ~~Issue 3 — Unknown second death in close-day output~~ ✅ FIXED

### What was done
Night 5→6 had 2 deaths. `close-day` identified PlayerB (camping outside [0|-2]) but wrote
"Unknown" for the second because day-05.md had no full citizen roster — only a movement log.

Ground truth supplied by user: second death was **PlayerA**, cause **Dehydration** (inside town).

**Data fixes applied:**
- `towns/s19-multicoloured-theatre/day-05.md` — replaced "Unknown" row with PlayerA / Dehydration
- `towns/s19-multicoloured-theatre/daily-log.md` — Day 5 outcome updated to `PlayerB †, PlayerA †`

**Root cause fix:**
`close-day.md` Step 3 now calls `get_citizen_positions(day=N-1)` as the **primary** death source.
Fata Morgana returns a `### Dead citizens` section grouped by day with name + cause + coords —
authoritative, no citizen-list diff needed. Cause string used verbatim (no mapping). Citizen-list
diff demoted to fallback. If fallback still leaves gaps, close-day now asks the user rather than
writing "Unknown".

### Key insight
`sources/fatamorgana.py` `_parse_deaths()` already parses the full cadaver list with `dtype` →
human-readable cause (Dehydrated, Eaten by zombies, Infection, etc.) per day. `format_citizens()`
renders it in `### Dead citizens (N):` / `  Day X:` / `    Name — Cause (last at [x|y])` format.
`get_citizen_positions(day=N)` accepts historical day param — this is the right tool for close-day.

---

## Issue 4 — Cron prompt is 280+ lines embedded in CronCreate call

### Problem
`track-town` skill ([.claude/commands/track-town.md](.claude/commands/track-town.md)) embeds the
full cron prompt inline in the `CronCreate` call (lines 78–196, ~120 lines of instructions).
This is hard to read, impossible to edit without re-running `/track-town set-cron`, and any
prompt change requires recreating the cron job.

### Fix approach
Two options:

**Option A — External skill file (recommended)**
Extract the cron body into `.claude/commands/track-town-cron.md`. In the CronCreate `prompt`
field, write a short dispatch: `"Run skill track-town-cron for town {resolved-folder}"`. The
cron agent loads the skill file fresh each run — edits take effect immediately without
recreating the job.

**Option B — Inline but trimmed**
Compress the embedded prompt using `/caveman:compress`. Reduces token cost per cron tick but
doesn't solve the maintainability problem.

Option A is cleaner. The CronCreate prompt then becomes ~3 lines. Skill resolution works the
same way as `/build-plan` or `/close-day` — the cron agent has skill access.

### Files to touch
- `.claude/commands/track-town.md` — replace embedded prompt block with skill dispatch
- `.claude/commands/track-town-cron.md` — new file, extracted cron body

**Warning:** After changing track-town.md, the live cron job (if any) still has the old embedded
prompt. It must be recreated: `CronDelete {job-id}` then `/track-town set-cron`. Check
`.discord-monitor-state.json` or ask user for the current job ID.

---

## Issue 5 — Day-transition logic in cron untested

### Problem
The cron prompt in `track-town.md` has a `STEP 1 — DAY TRANSITION CHECK` block (line 85–94)
that detects when `baseline day < current game day`. This has never fired — the town has been on
Day 6 since the cron was set up.

### What to verify when Day 7 arrives
1. Cron runs and detects the day change (baseline day=6, game day=7).
2. AP counters reset to 0 for all citizens.
3. Day-7 log file is created with `# Day 7 — {date}` header.
4. `daily-log.md` gets a new row for Day 7.
5. If `day-06.md` has no `### Night outcome`, the warning line is prepended.
6. `_baseline.md` updates to Day 7 with fresh positions.

### How to test without waiting
Manually edit `_baseline.md` to set day=5 (or any past day), then trigger the cron prompt
manually (run `/track-town` without `set-cron`). It should fire the transition branch.
Restore baseline after.

### Files to watch
- `towns/s19-multicoloured-theatre/_baseline.md` — day field drives the transition check
- `towns/s19-multicoloured-theatre/day-07.md` — should be created on first Day 7 cron run
- `.claude/commands/track-town.md` lines 85–94 — the transition logic itself

---

## Context: what was fixed this session

| Issue | Fix |
|---|---|
| KB queries returned nothing | Query strings now match actual file headings (`"Day 1–5"` etc.) |
| `get_buildings` missing resource requirements | Added `include_resources=True` param; build-plan uses it |
| Build-plan recommended locked/unbuilt buildings | MCP now splits Unlocked vs Locked; skill rules updated |
| Water urgency threshold too low | Changed `< 1.0` → `< 2.0` WR/citizen |
| Discord-monitor had no issue logging | Added `.discord-monitor-issues.log` append in Step 3 |
