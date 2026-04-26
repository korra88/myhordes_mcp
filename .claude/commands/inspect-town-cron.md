Run a recurring town snapshot: detect movements, AP spend, bank changes, and write to the active day log. Called by the cron job or directly by inspect-town.

Requires: `towns/{folder}/_baseline.md` already exists (seeded by `inspect-town`).

## STEP 1 — DAY TRANSITION CHECK

Call `get_town_overview(detail='compact')` and `get_bank_inventory(detail='summary')` in parallel. Read `towns/{folder}/_baseline.md` for last known state.

Compare baseline day number to current game day.

**If baseline day < current game day (new day detected):**
- Check if `towns/{folder}/day-{NN-1}.md` contains `### Night outcome`.
  - If NOT found: prepend `⚠ Day N-1 not yet closed — run /close-day when ready.` as first line of today's log entry.
- Reset ALL ap_spent to 0 for every citizen (outside and returned).
- Use current positions as new Day N baseline. Do NOT compute deltas from previous day positions.
- Update baseline day to N.

## STEP 2 — ACTIVE DAY LOG

Active log: `towns/{folder}/day-{NN}.md`. If missing, create with `# Day N — {date}` header and add row to `daily-log.md` (outcome TBD).

## STEP 3 — MOVEMENTS

Compare current citizen list to baseline:
- Returned: was in Outside table, now IN TOWN.
- Went out: was IN TOWN (not in any baseline table), now has coordinates.
- Position change: outside → outside at different coords.

## STEP 4 — AP SPENT TRACKING

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

## STEP 5 — PLAYER DEPLETED ZONE CHECK

Read `PLAYER_NAME` from `.env`. If player outside, call `get_zone_details(x1=X, y1=Y, x2=X, y2=Y)` for current coords. If depleted: `⚠ {PLAYER_NAME} in depleted zone [X|Y] — consider moving`.

## STEP 6 — GATE

Flag urgent if gate OPEN at 23:30 CET or later.

## STEP 7 — BANK

Flag decreases as PULLED (old→new) and increases (deposits) for:
HNB · Wire Reel · Electronic component · Laser Diode · Compact detonator · Copper Pipe · Semtex · Anabolic Steroids · Vodka Marinostov · Blueprint (rare) · Blueprint (very rare)

## STEP 8 — WRITE LOG ENTRY

**No changes:** append single line:
```
no changes — {HH:MM} CET
```

**With changes:** append a full entry using this format:
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

## STEP 9 — OVERWRITE BASELINE

Overwrite `_baseline.md`:
- Timestamp + day number
- Platform section (preserve level unless get_buildings confirms change)
- State (alive/inside/outside counts, defense, gate)
- Outside citizens: Citizen | Position | AP spent (updated)
- Returned today: Citizen | AP spent (cumulative for day)
- Critical items (updated counts)
