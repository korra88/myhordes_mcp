# Garbage Dump sheet — structure and rebuild instructions

A hand-rebuildable spec for the coalition's Garbage Dump calculator, captured from the
season-19 sheet on **2026-09-12** (town: Ensenada Colérica de la Tierra del Fuego, day 26).

Purpose: decide which bank items to throw on the Garbage Dump, and what temporary
defence that yields tonight, without overspending the bank stock that feeds an
All or Nothing build.

Rebuild this if access to the original spreadsheet is lost or the coalition starts a new
town. Only the `Garbage Dump` tab and its `List 11` lookup block are covered — the other
tabs in the original workbook are unrelated.

The `/update-garbage-dump-list` skill refreshes column D of a sheet built to this spec.

## Files

| File | Use |
|---|---|
| `items.csv` | 103 item rows, `Item group` + `Item`. Paste into `A6:B108`. |
| `list11.csv` | The tempDP lookup table. Paste into `List 11!E1:H16`. |

## Tab 1 — `Garbage Dump`

### Config block (rows 1-4)

Columns A and D are empty spacers. Column C holds the inputs you edit; column F and
column I are computed.

| Cell | Content | Type |
|---|---|---|
| `B1` | `Dump Upgrade` | label |
| `C1` | `No` / `Yes` | **input** — is the Dump Upgrade building built? |
| `B2` | `Organised Dump` | label |
| `C2` | `No` / `Yes` | **input** — reference only, used by no formula (it changes AP cost, not defence) |
| `B3` | `Garbage Dump Level` | label |
| `C3` | `0`, `1` or `2` | **input** — dump upgrade level |
| `B4` | `Defensive Adjustment` | label |
| `C4` | e.g. `0.13` (formatted as `13%`) | **input** — the town's Defensive Adjustment percentage |
| `E1` | `Dump items sum:` | label |
| `F1` | `=sum(D6:D)` | total dumpable items held in bank |
| `E2` | `Final defence sum:` | label |
| `F2` | `=round(sum(G6:G)+(sum(G6:G)*C4))` | tempDP from the planned dump, after adjustment |
| `H1` | `Total Bank items:` | label |
| `I1` | a number, e.g. `3311` | **input, maintained by hand** — total items in bank |
| `H2` | `Bank items without dump items:` | label |
| `I2` | `=I1-F1` | what would remain as AoN fuel |
| `H3` | `No. of items that will be used:` | label |
| `I3` | a number, e.g. `120` | **input** — items citizens will consume before the AoN night |
| `H4` | `AoN defence:` | label |
| `I4` | `=round(((I2-I3+55)*2)+(((I2-I3+55)*2)*C4))` | projected All or Nothing defence |

Keep `F1` and `F2` **open-ended** (`D6:D`, `G6:G`). Hardcoding an end row silently drops
any item row added below it.

`C1` and `C3` hold the level expected **tonight**, after the day's free vote resolves —
free-vote upgrades apply before the attack. They will legitimately read higher than the
current in-game level.

### Header row (row 5)

`A5:G5` = `Item group`, `Item`, `Defence`, `Towns Bank`, `Left to dump`, `Dump Quantity`, `Sum`

### Item rows (6-108)

Paste `items.csv` into `A6:B108`. Group spans, in order:

| Group | Rows | Count |
|---|---|---|
| Resources | 6-9 | 4 |
| Weapons | 10-55 | 46 |
| Foods | 56-89 | 34 |
| Animals | 90-98 | 9 |
| Defences | 99-108 | 10 |

Then fill the formula columns. For row `N`:

**`C{N}` — Defence (tempDP per item).** Looks the rate up from `List 11` by dump level
and item group, picking the with/without Dump Upgrade column off `C1`:

```
=IFERROR(if($C$1="No";INDEX(FILTER('List 11'!$G$2:$G$16;'List 11'!$F$2:$F$16=A6;'List 11'!$E$2:$E$16=$C$3);1);if($C$1="Yes";INDEX(FILTER('List 11'!$H$2:$H$16;'List 11'!$F$2:$F$16=A6;'List 11'!$E$2:$E$16=$C$3);1))))
```

Shown for row 6; fill down. `A6` is the only relative reference. **Never hand-edit
column C** — correct `C1` / `C3` and every row recalculates.

Note the semicolon argument separators. That is a locale setting; in a comma-locale
sheet write `,` instead.

**`D{N}` — Towns Bank.** The count held in the bank. This is the only manually refreshed
column, and what `/update-garbage-dump-list` writes. Write `0`, never blank.

**`E{N}` — Left to dump.** `=D6-F6`

**`F{N}` — Dump Quantity.** **Input.** How many of this item you plan to throw. Leave
blank for none.

**`G{N}` — Sum.** `=F6*C6`

## Tab 2 — `List 11` (lookup block only)

Paste `list11.csv` into `E1:H16`. Columns:

`E` Garbage Dump lvl · `F` Item Group · `G` WO Dump Upgrade · `H` With Dump Upgrade

One row per (level, group) pair. The column C formula filters on `$E$2:$E$16` and
`$F$2:$F$16`, so the block must start at row 2 and the group strings must match column A
of the Garbage Dump tab **exactly**.

Values (these are the game's, from the wiki):

| Level | Resources | Weapons | Foods | Animals | Defences |
|---|---|---|---|---|---|
| 0 | 1 | 1 | 1 | 1 | 1 |
| 1 | 1 | 6 | 4 | 1 | 1 |
| 2 | 1 | 6 | 4 | 7 | 3 |

Add 1 to every figure for the Dump Upgrade column. Level 2 is the maximum. Resources
never exceed 1 — the level-3 Resources upgrade was removed in season 17.

The original workbook's `List 11` tab also holds an unrelated watch-day penalty table in
columns A-C. Not needed here.

## Mechanics the sheet does not model

- **Dump actions cost AP.** Each citizen gets one free action per day, covering 1-20
  items **of a single type**. Further actions cost 2 AP, or 1 AP once Organized Dump is
  built. A `Dump Quantity` of 500 is 25 actions, not one. Consider a column
  `=CEILING(F6/20)`.
- **Dumped items leave the bank**, so they stop counting as All or Nothing fuel. `I2`
  captures this, but only against the hand-maintained `I1`.
- **Recovery** is possible until the attack, at the same action cost.

## Known open points in the original sheet

- `I4` uses `+55` where the game lists All or Nothing at `+50` def. Unresolved; the sheet
  owner has not confirmed whether the extra 5 is an intended building bonus or an error.
  Note that `C4` then multiplies the whole expression, so any bonus baked into the 55 is
  applied twice on that term (~11 def).
- `I1` is a literal, not a formula. It is correct just after a manual refresh and drifts
  afterwards.
- Bank items with no row, as of capture: `Collector Pins`, `Stake Launcher`,
  `Fistful of insects`. Also unresolved: whether the sheet's `Open Can` is the bank's
  `Can`.
- `Unshaped Concre` in `items.csv` is truncated in the source sheet; the game item is
  `Unshaped Concrete Blocks`. Either spelling works — the skill aliases the short form —
  but a fresh build should use the full name.
- Several sheet rows name loaded weapon variants (`Water Pistol (3 shots)`,
  `Battery Launcher 1-ITF (loaded)`) while the bank reports the emptied ones. Emptied
  weapons still dump for full weapon value; the skill folds them into the loaded row.
- An item must appear in exactly one group. `Fat Serpent` was listed under both Weapons
  and Animals; the groups carry different rates at level 2, so the duplicate was deleted
  and Animals kept.
