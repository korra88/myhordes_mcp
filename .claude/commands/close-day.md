Finalize previous day's log using current morning MCP snapshot (post-attack state). Run at start of new game day. Pass `backfill` to close all unclosed days from day-01 up to N-1.

## Step 1 — Resolve town, current day, target days

- Read `.env`, note `FATAMORGANA_TOWN_ID`.
- Call `get_town_overview` → town name + current game day N.
- List `towns/` subdirs (exclude `_template`). Case-insensitive slug match on `s{season}-{slug}`.
- No match → stop, tell user.

**Normal mode** (no `backfill`):
- Target: day N-1 only.
- Previous day file: `towns/{folder}/day-{NN-1}.md`. Missing → stop, tell user.

**Backfill mode** (`$ARGUMENTS` contains `backfill`):
- Scan all `towns/{folder}/day-{NN}.md` files from day-01 up to day-(N-1).
- Collect those missing `### Night outcome` section.
- Process each in order (oldest first). Continue to next even if one is sparse.

## Step 2 — Fetch current morning state

Call in parallel (once — reuse across all backfill days):
- `get_citizen_positions` — alive count, inside/outside, any dead citizens.
- `get_defense_status` — current defense + tonight's estimate (Day N's).
- `get_bank_inventory(detail='summary')` — current bank state. Never `detail='full'`.

Note: for backfill, today's snapshot is authoritative only for the most recent night. Earlier nights use the data available in the day files themselves (last citizen list logged, last defense snapshot).

## Step 3 — Reconstruct night outcome (per target day)

For each target day file:

- Read fully. Extract:
  - Last alive count + citizen list (final cron check or manual section).
  - Last known defense + attack estimate.
  - Last critical items baseline.
  - Who was outside at end of day (last position snapshot).

- **Deaths — primary source (Fata Morgana death log):**
  Call `get_citizen_positions(day=N-1)` for the target day. Fata returns a `### Dead citizens` section grouped by day, with name + cause of death + last coords for every recorded death. Use this as the authoritative source — it covers dehydration, infection, zombie kills, etc. without requiring a citizen-list diff.
  - Use Fata's cause string directly in the log (no mapping).
  - Cross-check last coords: if `last_coords` is outside town, note "camping outside".

- **Deaths — fallback (citizen-list diff):**
  Only use if Fata returns no deaths for that day (data gap or very old day). Compare previous day's last citizen list to next day's first citizen list.
  - Outside at end of day → "Zombie attack while camping".
  - Inside → "Unknown / likely infection or wound".
  - If expected death count > identified deaths, explicitly ask the user to confirm remaining names/causes rather than writing "Unknown".

- **Survival:** Citizens alive next day → survived. Note defense vs. attack estimate.
- **Net alive change:** yesterday's count → next day's count.

**Backfill sparse days:** If day file has no citizen snapshots, note "insufficient data — partial close" and record what is derivable from Fata. Do not skip.

## Step 4 — Append night outcome to day file

Append to `towns/{folder}/day-{NN}.md`:

```
---

### Night outcome — {date, e.g. "Mar 24 → 25"}
**Result: SURVIVED** (or FAILED)
**Defense:** {final defense} vs **{attack estimate}** zombies
**Alive after:** {next day count} ({prev count − deaths} — {N deaths} overnight)

#### Deaths
| Citizen | Last position | Cause |
|---|---|---|
| **Name** | [x\|y] or IN TOWN | Zombie attack / Infection / Unknown |

*(No deaths — all survived the night.)*
```

If bank changed significantly overnight (builds/deposits after last baseline), note briefly.

## Step 5 — Update daily-log.md

Find row for each closed day. Replace **TBD** outcome cell:
- `Survived` — no deaths.
- `Survived · {Name} †` — deaths (comma-separated if multiple).
- `FAILED` — town did not survive.

Update alive count cell if changed from original.

## Step 6 — Report to user

- List each day file updated.
- Per day: survived/failed, deaths count, who died.
- Current Day N state: alive count, defense, tonight's estimate.
- Backfill: note any days skipped or partially closed due to sparse data.
