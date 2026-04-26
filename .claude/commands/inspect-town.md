Seed baseline and run a one-time snapshot of citizen positions and town status. For cron setup, use `track-town`.

## Log structure

- `towns/{folder}/daily-log.md` — index, one summary row per day
- `towns/{folder}/day-{NN}.md` — one file per game day
- `towns/{folder}/_baseline.md` — last-known state for delta checks

## Step 1 — Resolve town folder and active day log

- Read `.env`, note `FATAMORGANA_TOWN_ID`.
- Call `get_town_overview` → town name + current game day N.
- List `towns/` subdirs (exclude `_template`). Case-insensitive slug match on `s{season}-{slug}`.
- No match → tell user, stop.
- Active day log: `towns/{folder}/day-{NN}.md` (NN zero-padded). If missing, create with `# Day N — {date}` header and add row to `daily-log.md`.
- Confirm `towns/{folder}/daily-log.md` exists.

## Step 2 — Seed baseline sidecar

If `_baseline.md` missing: call `get_town_overview` + `get_buildings` (Observation Platform level). Create:

```markdown
# Cron baseline — {folder}
_Last updated: {datetime} (Day N)_

## Platform
Observation Platform: Level N (N AP return discount)
```
*(Level 3 → 2 AP discount; Level 4 → 3 AP discount. Not built → omit discount line, note "not built".)*

```markdown
## State
- **Alive:** N — X inside, Y outside
- **Defense:** N
- **Gate:** OPEN/CLOSED

## Outside citizens
| Citizen | Position | AP spent |
|---|---|---|
| Name | [x\|y] | ~0 |

## Returned today
| Citizen | AP spent |
|---|---|

## Critical items
| Item | Count |
|---|---|
| Handful of nuts and bolts | N |
| Wire Reel | N |
| Electronic component | N |
| Laser Diode | N |
| Compact detonator | N |
| Copper Pipe | N |
| Semtex | N |
| Anabolic Steroids | N |
| Vodka Marinostov | N |
| Blueprint (rare) | N |
| Blueprint (very rare) | N |
| Iron Chest | N |
```

Citizens in town at seed time: not listed in Outside table. All start at `~0` AP spent.

## Step 3 — Run snapshot

Run the `inspect-town-cron` skill once now.

For the **initial seed** (no prior baseline existed), write this entry to the active day log instead of the standard cron format:
```
### {HH:MM} CET — baseline seeded
State: {N} alive — {inside} inside, {outside} outside · Defense {D} · Gate {OPEN/CLOSED} · Tonight: {estimate}
Baseline established. {N} citizens outside logged. No prior state to compare.
```

## Step 4 — Confirm to user

Report:
- Active day log path
- Baseline sidecar path
- Index path
- Note "one-time run only — use /track-town to schedule recurring cron"
