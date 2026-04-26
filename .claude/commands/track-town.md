Schedule a recurring cron job that runs the inspect-town-cron skill. For a one-time snapshot, use `inspect-town` instead.

## Step 1 — Resolve town folder

- Read `.env`, note `FATAMORGANA_TOWN_ID`.
- Call `get_town_overview` → town name + current game day N.
- List `towns/` subdirs (exclude `_template`). Case-insensitive slug match on `s{season}-{slug}`.
- No match → tell user, stop.
- Confirm `towns/{folder}/_baseline.md` exists (run `inspect-town` first if not).

## Step 2 — Parse interval

Parse interval from `$ARGUMENTS` (e.g. `set-cron 30m`, `set-cron 1h`). Default if omitted: `1h`. Convert:
- `Nm` (N ≤ 59) → `*/N * * * *`
- `Nh` (N ≤ 23) → `7 */N * * *`

## Step 3 — Create cron job

Use CronCreate with:
- `recurring: true`
- `cron`: expression from Step 2
- `prompt`: `Run skill inspect-town-cron for town {resolved-folder}`

## Step 4 — Confirm to user

Report:
- Job ID
- Interval + cron expression
- Note: auto-expires after 7 days, cancel with `CronDelete {job-id}`
- Reminder: edit `inspect-town-cron.md` to change snapshot behaviour — no cron recreation needed
