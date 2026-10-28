Run a town snapshot: movements, AP spent, bank changes, warnings — and write it to the day log.

All numbers come from `get_town_changes`: do not recompute distances, AP or bank
deltas. Your job is to write the log entry and judge what deserves a warning.

**Auto log.** With `TOWN_LOG_AUTO` on, the server already appends the Check entry
itself (the tool header says "Town log: check HH:MM logged"). Then do not duplicate it:
add only the one-line judgment, and the day-transition warning if still relevant.

## Log structure

- `towns/{folder}/daily-log.md` — index, one summary row per day
- `towns/{folder}/day-{NN}.md` — one file per game day

(The old `_baseline.md` is no longer used: snapshots are stored by the server.)

## Step 1 — Fetch changes

Call `get_town_changes()` with no arguments. It compares against the previous
check today and moves that marker forward. Its header gives town name, day N and
which snapshot it compared against.

Resolve the folder (`{folder}` below): the server already created it while fetching.
It is the `towns/*/` whose `cache/_meta.json` has `"town_id"` equal to the town ID
(content of `towns/_current_town`; if missing, `FATAMORGANA_TOWN_ID` in `.env`),
e.g. `grep -lE '"town_id": 8212(,|$)' towns/*/cache/_meta.json`.
Never derive the folder name from the town name yourself. No match (archive
failed) → create `towns/s{season}-{slug}/` (lowercase, accents stripped, hyphens).
If `daily-log.md` or `notes.md` is missing in the folder, copy it from `templates/town/`.

## Step 2 — Day transition

If the tool says it compared against the first snapshot of the day ("no previous
check"), this is the first check of day N:
- Check whether `towns/{folder}/day-{NN-1}.md` contains `### Night outcome`.
  If not, start today's entry with `⚠ Day N-1 not yet closed — run /close-day when ready.`
- If the tool also says there is nothing to compare, log the state line only.

## Step 3 — Active day log

Active log: `towns/{folder}/day-{NN}.md`. If missing, create it with a
`# Day N — {date}` header and add a row to `daily-log.md` (outcome TBD).

## Step 4 — Write the entry

**No changes** (tool says so and no warnings): append one line:
```
no changes — {HH:MM} CET
```

**Otherwise** append, copying the tool's lines (translate nothing, drop nothing):
```
### Check ({HH:MM} CET)
{State line}

**MOVEMENTS:**
- {each movement line}

**BANK:**
- {each bank line}

**CONSTRUCTIONS:** {line, if any}

**AP today:** {top movers, "Name ~N AP", comma-separated}

⚠ {each warning}
```
Omit any empty block. Add at most one line of your own judgment after the
warnings — only for something an experienced player would actually worry about
(see `knowledge/tactics/session-protocols.md`, "Don't flag normal game states").

## Step 5 — Report

Tell the user the file written and the 2–3 most important changes or warnings.
