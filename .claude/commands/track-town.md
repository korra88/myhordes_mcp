Set up a recurring cron job to monitor citizen positions and town status for the current town.

## Log file structure

Each town folder uses a per-day structure:
- `towns/{folder}/daily-log.md` — index only (one summary row per day, links to day files)
- `towns/{folder}/day-01.md`, `day-02.md`, … — one file per game day (active file grows during play)

## Step 1 — Resolve the town folder and active day log

- Read `.env` in the project root and note the `FATAMORGANA_TOWN_ID` value.
- Call `get_town_overview` to fetch the current town's name and **current game day number**.
- List subdirectories under `towns/` (excluding `_template`).
- Match the town name to the correct folder. The folder naming convention is `s{season}-{slugified-town-name}` (e.g. "Tortuous Valleys" → `s19-tortuous-valleys`). Do a case-insensitive match on the slug portion.
- If no match is found, tell the user and stop — do not create the cron.
- Determine the active day log: `towns/{matched-folder}/day-{NN}.md` where NN is the current game day zero-padded to 2 digits (e.g. Day 3 → `day-03.md`).
- If `day-{NN}.md` does not exist yet, create it with a `# Day N — {dates}` header and add a row for it in `daily-log.md`.
- Confirm `towns/{matched-folder}/daily-log.md` exists.

## Step 2 — Determine the interval

- If `$ARGUMENTS` is provided, treat it as the interval (e.g. `30m`, `1h`, `2h`). Supported suffixes: `m` (minutes), `h` (hours).
- If no argument is provided, default to `1h`.
- Convert to a cron expression:
  - `Nm` where N ≤ 59 → `*/N * * * *`
  - `Nh` where N ≤ 23 → `7 */N * * *` (use minute :07 to avoid thundering-herd at :00)

## Step 3 — Create the cron job

Use CronCreate with:
- `recurring: true`
- `cron`: the expression from Step 2
- `prompt` (substitute the resolved folder from Step 1):

```
Call get_town_overview to get the current town name and game day number. Call get_citizen_positions and get_defense_status. Also call get_bank_inventory.

Determine the active day log:
- Active file = `towns/{resolved-folder}/day-{NN}.md` where NN is the current game day zero-padded to 2 digits.
- If this file does not exist (a new day started since the cron was created): create it with a `# Day N — {dates}` header, then add a new row to `towns/{resolved-folder}/daily-log.md` marking this day as active (outcome TBD).

Read the last recorded state from the active day file.

Append a brief timestamped update to that file noting:

MOVEMENTS: Who moved (from/to), who came home, who went out. Note any deaths.

GATE & DEFENSE: Flag if gate is open within 2 hours of midnight. Note any significant defense drops.

BANK CHANGES: Compare current bank to the last logged "critical items baseline" table. Flag any count decrease as "PULLED" (old count → new count) for these building-critical items:
- Handful of nuts and bolts (HNB)
- Wire Reel
- Electronic component
- Laser Diode
- Compact detonator
- Copper Pipe
- Semtex
- Anabolic Steroids (note: only needed until Fertilizer, Ravaged Pumpkins, and Tamer's Trap System are built)
- Vodka Marinostov (note: only needed until Architect's Study and Builder's Merchant are built)

Also flag if Construction Blueprint (rare or uncommon) count drops.

Update the baseline table in the active day file to reflect the current counts after each check.

Only append if there are actual changes. If nothing changed, note "no changes" with the current time.
```

## Step 4 — Execute once immediately

After creating the cron, run the prompt once immediately so the first check happens now rather than waiting for the first scheduled fire.

## Step 5 — Confirm to the user

Report:
- The active day log path (e.g. `towns/s19-tortuous-valleys/day-03.md`)
- The index path (`towns/{folder}/daily-log.md`)
- The cron job ID
- The interval and cron expression
- That it will auto-expire after 7 days, and can be cancelled with `CronDelete {job-id}`
