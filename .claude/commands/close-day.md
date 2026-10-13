Finalize previous day's log using current morning MCP snapshot (post-attack state). Run at start of new game day. Pass `backfill` to close all unclosed days from day-01 up to N-1.

## Step 1 — Resolve town, current day, target days

- Town ID: the content of `towns/_current_town`; if that file is missing,
  `FATAMORGANA_TOWN_ID` in `.env`.
- Call `get_town_overview` → town name + current game day N.
- Folder: the `towns/*/` whose `cache/_meta.json` has `"town_id"` equal to
  the town ID, e.g. `grep -lE '"town_id": 8212(,|$)' towns/*/cache/_meta.json`.
  Never derive it from the town name.
- No match → stop, tell user.

**Normal mode** (no `backfill`):
- Target: day N-1 only.
- Previous day file: `towns/{folder}/day-{NN-1}.md`.

**Backfill mode** (`$ARGUMENTS` contains `backfill`):
- Check days 1 to N-1: each `towns/{folder}/day-{NN}.md` that lacks a
  `### Night outcome` section, or does not exist, is a target.
- Process each in order (oldest first). Continue to next even if one is sparse.

**Missing day file** (no inspect-town ran that day): do not stop — the night report
comes from the tools, not from the file. Create it with a `# Day D — {date}` header
(day D's date = today minus N-D days), the line
`*No intra-day snapshots were taken on day D; this file holds the night outcome only.*`,
and a row for day D in `daily-log.md` if there is none. Then close it as usual.

## Step 2 — Night report (per target day)

For each target day D call `get_night_report(day=D)`. It returns, computed in code:
result (survived/failed), defense vs actual attack and the estimate, alive at day
start → next morning, and every death of day D with cause and last position
(outside = camping or stranded). Do not recompute any of it, and do not diff
citizen lists by hand.

If the report notes a mismatch with Gest'Hordes' death count, or a death you
cannot place, ask the user to confirm names/causes rather than writing "Unknown".

Read the day file `towns/{folder}/day-{DD}.md` only for context worth keeping in
the outcome (e.g. who was flagged as camping), never to recount deaths.

**Backfill:** same call per day, oldest first. If Fata has no data for a day,
note "insufficient data — partial close" and continue.

## Step 3 — Morning state (once)

Call `get_defense_status` for day N's defense and tonight's estimate, for the report.

## Step 4 — Append night outcome to day file

Append to `towns/{folder}/day-{NN}.md`:

```
---

### Night outcome — {date, e.g. "Mar 24 → 25"}
**Result: SURVIVED** (or FAILED)
**Defense:** {defense} vs **{attack}** zombies (estimate {min}–{max})
**Alive after:** {next morning} ({day start} − {N deaths})

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
