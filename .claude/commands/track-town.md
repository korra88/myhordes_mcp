Set up a recurring cron job to monitor citizen positions and town status for the current town.

## Log file structure

Each town folder uses a per-day structure:
- `towns/{folder}/daily-log.md` — index only (one summary row per day, links to day files)
- `towns/{folder}/day-01.md`, `day-02.md`, … — one file per game day (active file grows during play)
- `towns/{folder}/_baseline.md` — small sidecar holding last-known state for cron delta checks

## Step 1 — Resolve the town folder and active day log

- Read `.env` in the project root and note the `FATAMORGANA_TOWN_ID` value.
- Call `get_town_overview` to fetch the current town's name and **current game day number**.
- List subdirectories under `towns/` (excluding `_template`).
- Match the town name to the correct folder. The folder naming convention is `s{season}-{slugified-town-name}` (e.g. "Tortuous Valleys" → `s19-tortuous-valleys`). Do a case-insensitive match on the slug portion.
- If no match is found, tell the user and stop — do not create the cron.
- Determine the active day log: `towns/{matched-folder}/day-{NN}.md` where NN is the current game day zero-padded to 2 digits (e.g. Day 3 → `day-03.md`).
- If `day-{NN}.md` does not exist yet, create it with a `# Day N — {dates}` header and add a row for it in `daily-log.md`.
- Confirm `towns/{matched-folder}/daily-log.md` exists.

## Step 2 — Seed the baseline sidecar

Check if `towns/{matched-folder}/_baseline.md` exists.
- If it does not exist, call `get_town_overview` and `get_buildings` (to check Observation Platform level) and create `_baseline.md` with the following structure:

```markdown
# Cron baseline — {folder}
_Last updated: {datetime} (Day N)_

## Platform
Observation Platform: Level N (N AP return discount)
```
*(Level 3 → 2 AP discount; Level 4 → 3 AP discount. If the building does not exist yet, omit the discount line and note "not built".)*

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

All citizens start with `~0` AP spent. Citizens already in town at seeding time are not listed in the Outside table.

## Step 3 — Determine the interval

- If `$ARGUMENTS` is provided, treat it as the interval (e.g. `30m`, `1h`, `2h`). Supported suffixes: `m` (minutes), `h` (hours).
- If no argument is provided, default to `1h`.
- Convert to a cron expression:
  - `Nm` where N ≤ 59 → `*/N * * * *`
  - `Nh` where N ≤ 23 → `7 */N * * *` (use minute :07 to avoid thundering-herd at :00)

## Step 4 — Create the cron job

Use CronCreate with:
- `recurring: true`
- `cron`: the expression from Step 3
- `prompt` (substitute the resolved folder from Step 1):

```
Call get_town_overview(detail='compact') and get_bank_inventory(detail='summary') in parallel. Read `towns/{resolved-folder}/_baseline.md` for last known state.

---

## STEP 1 — DAY TRANSITION CHECK

Compare baseline day number to current game day.

**If baseline day < current game day (new day detected):**
- Check if `towns/{resolved-folder}/day-{NN-1}.md` (previous day file) contains a `### Night outcome` section.
  - If NOT found: prepend `⚠ Day N-1 not yet closed — run /close-day when ready.` as the first line of today's log entry.
- Reset ALL ap_spent to 0 for every citizen (outside and returned).
- Use current positions as the new Day N baseline reference. Do NOT compute movement deltas from previous day positions.
- Update baseline day to current day N.

---

## STEP 2 — ACTIVE DAY LOG

Determine active day log: `towns/{resolved-folder}/day-{NN}.md` (NN = current game day, zero-padded to 2 digits). If it does not exist, create it with a `# Day N — {date}` header and add a row to `towns/{resolved-folder}/daily-log.md` (outcome TBD).

---

## STEP 3 — MOVEMENTS

Compare current citizen list to baseline. Identify:
- Returned to town: citizen was in "Outside citizens" table, now IN TOWN.
- Went outside: citizen was IN TOWN (not in any baseline table), now has coordinates.
- Position changes: citizen was outside, still outside, but at different coordinates.

---

## STEP 4 — AP SPENT TRACKING

Read platform level from baseline `## Platform` section (default Level 3 = 2 AP return discount; Level 4 = 3 AP return discount).

For each citizen who changed position:

**Outside → new outside position:**
  - delta = Manhattan(old_position, new_position)
  - ap_spent += delta

**Outside → IN TOWN (returned):**
  - raw_leg = Manhattan(last_known_position, [0|0])
  - ap_spent += max(0, raw_leg − platform_discount)
  - Move citizen from "Outside citizens" to "Returned today" table in baseline.

**IN TOWN → outside (freshly departed):**
  - If citizen already appears in "Returned today" (went out and back earlier today): carry their existing ap_spent.
  - Otherwise: ap_spent starts at 0.
  - Add citizen to "Outside citizens" table.

Citizens with no position change: ap_spent unchanged (carry forward as-is).

Note ap_spent in the log entry for every citizen who moved, e.g.:
  `PlayerD [-6|-2]→[-6|-4] (+2 AP, ~15 AP total)`
  `PlayerC returned from [-2|-4] (4 AP net, ~4 AP total)`

---

## STEP 5 — PLAYER DEPLETED ZONE CHECK

Read PLAYER_NAME from `.env`. If that citizen is outside town, call get_zone_details(x1=X, y1=Y, x2=X, y2=Y) for their current coordinates. If the zone is marked "depleted", flag: `⚠ {PLAYER_NAME} in depleted zone [X|Y] — consider moving`.

---

## STEP 6 — GATE

Flag as urgent if gate is OPEN at 23:30 CET or later.

---

## STEP 7 — BANK

Flag any decrease as PULLED (old→new) for these tracked items:
HNB · Wire Reel · Electronic component · Laser Diode · Compact detonator · Copper Pipe · Semtex · Anabolic Steroids · Vodka Marinostov · Blueprint (rare) · Blueprint (very rare)
Also flag increases (deposits) for the same items.

---

## STEP 8 — WRITE LOG ENTRY

If nothing changed at all, write a single line: `no changes — {time}`.
Otherwise append a full timestamped entry to the active day log, including the State line (alive/inside/outside/defense/tonight).

---

## STEP 9 — OVERWRITE BASELINE

Overwrite `towns/{resolved-folder}/_baseline.md` with updated state:
- Timestamp and day number
- Platform section (preserve level — do not overwrite unless get_buildings confirms a change)
- State (alive/inside/outside counts, defense, gate)
- Outside citizens table: Citizen | Position | AP spent (updated)
- Returned today table: Citizen | AP spent (updated, cumulative for the day)
- Critical items table (updated counts)
```

## Step 5 — Execute once immediately

After creating the cron, run the prompt once immediately so the first check happens now rather than waiting for the first scheduled fire.

## Step 6 — Confirm to the user

Report:
- The active day log path (e.g. `towns/s19-tortuous-valleys/day-03.md`)
- The baseline sidecar path (`towns/{folder}/_baseline.md`)
- The index path (`towns/{folder}/daily-log.md`)
- The cron job ID
- The interval and cron expression
- That it will auto-expire after 7 days, and can be cancelled with `CronDelete {job-id}`
