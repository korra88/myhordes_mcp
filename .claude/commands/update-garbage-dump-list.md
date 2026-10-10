Refresh the "Towns Bank" column of a coalition Garbage Dump spreadsheet from live bank data, so the dump calculator plans against real stock.

This skill writes to a **shared Google Sheet**. It never guesses which one.

## Step 0 — Ask which spreadsheet. Every time.

Ask the user for the spreadsheet URL or ID **on every run, without exception**.

- Do not reuse an ID from memory, from `reference_dump_spreadsheet.md`, from an
  earlier run, or from earlier in this same conversation.
- Do not offer a remembered ID as a default, a pre-filled option, or a "last used"
  suggestion. The user asked for this guard specifically to stop a write landing
  on the wrong coalition's sheet.
- If `$ARGUMENTS` already contains a URL or a 44-character sheet ID, that counts as
  the answer — echo the ID back and continue without asking again.

Extract the ID from `https://docs.google.com/spreadsheets/d/{ID}/edit#gid=...`.

Then confirm you have the right document before reading anything else:

```
composio execute GOOGLESHEETS_GET_SHEET_NAMES -d '{"spreadsheet_id":"<ID>"}'
```

Show the user the returned tab list and the spreadsheet title. If there is no
`Garbage Dump` tab, stop and say so — do not fall back to another tab.

## Step 1 — Check Composio access

```
composio whoami
composio connections list
```

Needs a `googlesheets` entry with `status: ACTIVE`. If none, run `composio link googlesheets`.
If not logged in, run `composio login --no-browser --no-wait`, show the user the URL,
then `composio login --poll` in the background.

CLI gotchas, both real:
- Piping composio output to `head` silently loses it to SIGPIPE. **Redirect to a file**
  in the scratchpad, then read the file.
- `GOOGLESHEETS_BATCH_GET` takes camelCase `valueRenderOption` / `dateTimeRenderOption`,
  while every other key is snake_case.

## Step 2 — Read the sheet

Read the config block and the item rows in one batch:

```
composio execute GOOGLESHEETS_BATCH_GET -d '{"spreadsheet_id":"<ID>","ranges":["'"'"'Garbage Dump'"'"'!A1:I4","'"'"'Garbage Dump'"'"'!A5:G200"]}'
```

Row 5 is the header: `A` Item group, `B` Item, `C` Defence, `D` **Towns Bank**,
`E` Left to dump, `F` Dump Quantity, `G` Sum.

Item rows start at 6 and run to the last non-empty row in column B — **do not assume a
fixed end**. Rows get added and deleted, and layouts drift between seasons and
coalitions. Derive the last row from the response and use it for every range afterwards.

`docs/garbage-dump-sheet/` holds the full structure — config cells, every formula, the
103-row item list and the `List 11` lookup — for rebuilding the sheet from scratch.
Consult it if the layout you find does not match what this skill expects.

Groups seen so far: Resources, Weapons, Foods, Animals, Defences.

Only column D is refreshed. E, F and G are formulas — never write to them.

## Step 3 — Map the bank onto the sheet rows

Call `map_bank_to_dump_sheet(sheet_items=...)` with column B of the item rows, one
name per line in row order (blank rows as empty lines). It reads the live bank and
applies the mapping rules in code:

- broken items count (they dump for full value);
- `Water Bomb` = Water Bomb + Plastic Bag, `Exploding Water Bomb` = Exploding Water
  Bomb + Plastic Bag and Semtex (bags are filled for free at the Faucet — do not
  "correct" this to 1:1);
- emptied weapons (`X (empty)`) fold into their loaded row; with several candidate
  rows (Aqua-Splash 1–5 shots) the first one, reported as a decision;
- a truncated sheet name (`Unshaped Concre`) takes the unique bank name it prefixes;
  `(incomplete)` items are never mapped (Misc components, not weapons);
- duplicate sheet rows are reported — ask which one owns the item.

It returns one value per row (ready for the write), the decisions to confirm, and
bank items with no row by category. Most unmapped items are correctly excluded
(water, drugs, blueprints, boxes); report any **dumpable weapon or defence** among
them — `Collector Pins` and `Stake Launcher` have shown up this way. Adding a row
is a structure change: propose, never do it unasked.

Say which town and day the bank snapshot came from.

## Step 4 — Show the diff, then ask

Print every changed row as `row | group | item | old -> new`, plus the change count
out of total rows, plus old and new column-D sums.

Then ask the user to confirm before writing, listing separately:
- every ambiguous mapping you resolved by rule above,
- every item you could not map at all,
- the exact target range.

Writing to a shared spreadsheet is outward-facing and hard to undo. Get the
confirmation even when the diff looks trivial.

## Step 5 — Write column D only

Build the full column (every row, not just changed ones — a partial write misaligns
the range) and send:

```
composio execute GOOGLESHEETS_VALUES_UPDATE -d @payload.json
```

```json
{
  "spreadsheet_id": "<ID>",
  "range": "'Garbage Dump'!D6:D<last>",
  "values": [[790], [77], ...],
  "value_input_option": "USER_ENTERED"
}
```

One value per inner array, `majorDimension` left at the default `ROWS` so a 104-row
column is 104 single-element rows. Nulls are rejected — write `0`, never `""`.

Check `updatedCells` equals the row count.

## Step 6 — Verify and report

Re-read `E1:I4` to get the recalculated totals. Report:

- town + game day of the bank snapshot
- cells written, rows changed
- before/after for: Dump items sum, Bank items without dump items, AoN defence
- every alias and duplicate-row decision applied
- dumpable bank items still unrepresented, with the defence they would add

## Step 7 — Audit the sheet's formulas

Re-read `A1:G20` with `"valueRenderOption":"FORMULA"` and check the following.
**Report findings only. Never fix them unasked** — they are the sheet owner's formulas
and other tabs reference them.

**Do not mistake these for bugs:**

- Column C is a live `IFERROR(IF(...INDEX(FILTER('List 11'...))))` lookup keyed on
  (`C3` dump level, `A` item group), reading `List 11!G` when `C1="No"` and
  `List 11!H` when `C1="Yes"`. It is not hardcoded. Never hand-edit column C —
  correct the config cell and every row recalculates.
- `C1` and `C3` hold the **level expected tonight**, after the day's free vote
  resolves — free-vote upgrades apply before the attack. A mismatch against the
  current level in `get_buildings` is normal and intended. Raise it only if the
  day's free vote has already gone to a different building, in which case say so
  plainly and give the defence delta for both branches.
- `I4` AoN uses `+55` where the game lists All or Nothing at +50 def. This is a known
  open question the sheet owner has yet to settle. **Do not raise it as a new finding
  and do not change it.**
- `List 11` covering only dump levels 0-2 is correct — max Garbage Dump level is 2.
  The wiki's lvl3-5 rows are placeholders for future balance changes.

**Real findings worth reporting:**

1. `I1` "Total Bank items" is a hardcoded constant, not a formula. Compare against the
   live bank total and report the drift — it feeds `I2` and therefore the AoN estimate.
   It gets corrected by hand, so expect it to be right just after a refresh and to drift
   again afterwards.
2. Range consistency: `F1` and `F2` must cover the same rows. Both should be open-ended
   (`sum(D6:D)`, `sum(G6:G)`); a hardcoded end row misses anything added below it.
3. Duplicate item rows across groups (see Step 3). Zeroing one is a stopgap; the row
   should be deleted, because the two groups carry different tempDP rates at lvl2.
   (The historical `Fat Serpent` Weapons/Animals duplicate was deleted by the owner
   on 2026-09-14 — do not expect it.)
4. No column models dump AP. Each citizen gets one free action per day covering 1-20
   items **of a single type**; further actions cost 2 AP, or 1 AP with Organized Dump.
   A planned quantity of 500 in column F is 25 actions. Suggest `=CEILING(F/20)`.
5. Bank items with no sheet row (see Step 3). Report them; the owner adds rows in batches
   rather than one at a time, so re-report any that are still missing without treating a
   previous mention as resolved.

## Reference — tempDP per item by dump level

From the wiki, matching `List 11`. Values are without Dump Upgrade; add +1 to every
figure when `C1="Yes"`.

| Level | Resources | Weapons | Foods | Animals | Defences |
|---|---|---|---|---|---|
| 0 | 1 | 1 | 1 | 1 | 1 |
| 1 | 1 | 6 | 4 | 1 | 1 |
| 2 | 1 | 6 | 4 | 7 | 3 |

Level 2 is the maximum. Resources never exceed 1 (+1) — the level-3 Resources upgrade
was removed in S17.

Note: `knowledge/tactics/opti-town-meta.md` describes the dump as a flat
"2 DP/stored item". That holds only at level 0 with Dump Upgrade built. Use the table
above, not that line.
