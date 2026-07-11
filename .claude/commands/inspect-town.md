Seed baseline (if needed) and run a town snapshot: movements, AP spend, bank changes, write to day log. For recurring cron, use `track-town`.

## Log structure

- `towns/{folder}/daily-log.md` — index, one summary row per day
- `towns/{folder}/day-{NN}.md` — one file per game day
- `towns/{folder}/_baseline.md` — last-known state for delta checks

## Step 1 — Resolve town folder

- Read `.env`, note `FATAMORGANA_TOWN_ID`.
- Call `get_town_overview` → town name + current game day N.
- List `towns/` subdirs (exclude `_template`). Case-insensitive slug match on `s{season}-{slug}`.
- No match → tell user, stop.
- Confirm `towns/{folder}/daily-log.md` exists.

## Step 2 — Seed baseline (first run only)

If `_baseline.md` missing: call `get_town_overview(detail='compact')` + `get_buildings(mode='history')` (Observation Platform level shows as `[Lv.N]` in the built list). Create:

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

Write this entry to the active day log and stop (skip Steps 3–8):
```
### {HH:MM} CET — baseline seeded
State: {N} alive — {inside} inside, {outside} outside · Defense {D} · Gate {OPEN/CLOSED} · Tonight: {estimate}
Baseline established. {N} citizens outside logged. No prior state to compare.
```

## Step 3 — Day transition check

Call `get_town_overview(detail='compact')` and `get_bank_inventory(detail='summary')` in parallel. Read `_baseline.md` for last known state.

Compare baseline day to current game day.

**If baseline day < current game day (new day detected):**
- Check if `towns/{folder}/day-{NN-1}.md` contains `### Night outcome`.
  - If NOT found: prepend `⚠ Day N-1 not yet closed — run /close-day when ready.` as first line of today's log entry.
- Reset ALL ap_spent to 0 for every citizen (outside and returned).
- Use current positions as new Day N baseline. Do NOT compute deltas from previous day positions.
- Update baseline day to N.

## Step 4 — Active day log

Active log: `towns/{folder}/day-{NN}.md`. If missing, create with `# Day N — {date}` header and add row to `daily-log.md` (outcome TBD).

## Step 5 — Movements

Compact overview format: outside citizens are listed one per line with coordinates; inside citizens appear on a single `In town: Name, Name, …` roster line. A citizen absent from the outside lines but present in the roster is IN TOWN.

Compare current citizen list to baseline:
- Returned: was in Outside table, now IN TOWN.
- Went out: was IN TOWN (not in any baseline table), now has coordinates.
- Position change: outside → outside at different coords.

## Step 6 — AP spent tracking

Read platform level from baseline `## Platform` (default Level 3 = 2 AP return discount; Level 4 = 3 AP return discount).

**Outside → new outside position:**
- delta = Manhattan(old, new)
- ap_spent += delta

**Outside → IN TOWN (returned):**
- raw_leg = Manhattan(last_pos, [0|0])
- ap_spent += max(0, raw_leg − platform_discount)
- Move citizen from Outside → Returned today in baseline.

**IN TOWN → outside (freshly departed):**
- Already in Returned today → carry existing ap_spent.
- Otherwise → ap_spent = 0.
- Add to Outside citizens table.

No position change → ap_spent unchanged.

Log format: `PlayerD [-6|-2]→[-6|-4] (+2 AP, ~15 AP total)` / `PlayerC returned from [-2|-4] (4 AP net, ~4 AP total)`

## Step 7 — Player depleted zone check

Read `PLAYER_NAME` from `.env`. If player outside, call `get_zone_details(x1=X, y1=Y, x2=X, y2=Y)` for current coords. If depleted: `⚠ {PLAYER_NAME} in depleted zone [X|Y] — consider moving`.

## Step 8 — Gate

Flag urgent if gate OPEN at 23:30 CET or later.

## Step 9 — Bank

Flag decreases as PULLED (old→new) and increases (deposits) for:
HNB · Wire Reel · Electronic component · Laser Diode · Compact detonator · Copper Pipe · Semtex · Anabolic Steroids · Vodka Marinostov · Blueprint (rare) · Blueprint (very rare)

## Step 10 — Write log entry

**No changes:** append single line:
```
no changes — {HH:MM} CET
```

**With changes:** append:
```
### Cron check ({HH:MM} CET)
**{N} alive — {inside} inside, {outside} outside** · Defense {D} · Gate {OPEN/CLOSED} · Tonight: {estimate}

**MOVEMENTS:**
- {Citizen} [{old}] → [{new}] ({delta} AP, ~{total} AP total)
- {Citizen} [{old}] → IN TOWN ({net} AP net, ~{total} AP total)
- Went out: {Citizen} [{pos}] (~0 AP)

**BANK — deposits:**
- {Item}: {old} → {new} (+N deposited)

**BANK — pulled:**
- {Item}: {old} → {new} (−N)

⚠ {warning if any}
```
Omit MOVEMENTS block if none. Omit BANK block if no tracked-item changes. Omit ⚠ lines if no warnings.

## Step 11 — Overwrite baseline

Overwrite `_baseline.md`:
- Timestamp + day number
- Platform section (preserve level unless get_buildings confirms change)
- State (alive/inside/outside counts, defense, gate)
- Outside citizens: Citizen | Position | AP spent (updated)
- Returned today: Citizen | AP spent (cumulative for day)
- Critical items (updated counts)
