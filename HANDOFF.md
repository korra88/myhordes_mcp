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
`src/myhordes_mcp/fata/parse.py` `_parse_deaths()` already parses the full cadaver list with `dtype` →
human-readable cause (Dehydrated, Eaten by zombies, Infection, etc.) per day. `format_citizens()`
renders it in `### Dead citizens (N):` / `  Day X:` / `    Name — Cause (last at [x|y])` format.
`get_citizen_positions(day=N)` accepts historical day param — this is the right tool for close-day.

---

## Issue 5 — Day-transition logic in inspect-town untested

### Problem
`inspect-town.md` Step 3 detects when `baseline day < current game day` and resets AP counters,
creates new day file, etc. This has never fired — town has been Day 6 since cron was set up.

### How to test
Manually edit `towns/s19-multicoloured-theatre/_baseline.md` to set day to a past day (e.g. 5),
then run `/inspect-town`. It should fire the transition branch. Restore baseline after.

### What to verify
1. Detects day change (baseline day=6, game day=7).
2. AP counters reset to 0 for all citizens.
3. Day-7 log file created with `# Day 7 — {date}` header.
4. `daily-log.md` gets new row for Day 7.
5. If `day-06.md` has no `### Night outcome`, warning line prepended.
6. `_baseline.md` updates to Day 7 with fresh positions.

### Files
- `towns/s19-multicoloured-theatre/_baseline.md` — day field drives the check
- `.claude/commands/inspect-town.md` Step 3 — transition logic

---

## Context: what was fixed this session

| Issue | Fix |
|---|---|
| KB queries returned nothing | Query strings now match actual file headings (`"Day 1–5"` etc.) |
| `get_buildings` missing resource requirements | Added `include_resources=True` param; build-plan uses it |
| Build-plan recommended locked/unbuilt buildings | MCP now splits Unlocked vs Locked; skill rules updated |
| Water urgency threshold too low | Changed `< 1.0` → `< 2.0` WR/citizen |
| Discord-monitor had no issue logging | Added `.discord-monitor-issues.log` append in Step 3 |
| close-day wrote "Unknown" for second death | Now calls `get_citizen_positions(day=N-1)` as primary source; Fata cadaver list is authoritative |
| track-town had 120+ lines inline in CronCreate | Split into `inspect-town` (snapshot) + `track-town` (cron setup); cron dispatches `"Run skill inspect-town"` |
