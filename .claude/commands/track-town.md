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
- If it does not exist, call `get_town_overview` (if not already fresh) and create `_baseline.md` with the following structure:

```markdown
# Cron baseline — {folder}
_Last updated: {datetime} (Day N)_

## State
- **Alive:** N — X inside, Y outside
- **Defense:** N
- **Gate:** OPEN/CLOSED

## Outside citizens
{name} [{x}|{y}] · …

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
| Blueprint (uncommon) | N |
| Sealed Architect's Chest | N |
```

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

Determine the active day log: `towns/{resolved-folder}/day-{NN}.md` where NN is the current game day zero-padded to 2 digits. If it doesn't exist, create it with a `# Day N — {date}` header and add a row to `towns/{resolved-folder}/daily-log.md` (outcome TBD).

Compare current state to baseline. Build a brief timestamped entry:

**MOVEMENTS:** Who went out / came home / died. Note position changes for citizens already outside.

**GATE:** Flag as urgent if gate is OPEN at 23:30 CET or later.

**BANK — flag any decrease as PULLED (old→new) for these items:**
HNB · Wire Reel · Electronic component · Laser Diode · Compact detonator · Copper Pipe · Semtex · Anabolic Steroids · Vodka Marinostov · Blueprint (rare) · Blueprint (uncommon)
Also flag increases (deposits) for these same items.

If nothing changed at all, write a single line: `no changes — {time}`.
Otherwise append the full entry to the active day log.

Finally, overwrite `towns/{resolved-folder}/_baseline.md` with updated state (timestamp, alive/inside/outside counts, defense, gate, outside citizen list, critical item counts).
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