Finalize the **previous** day's log using the current morning MCP snapshot (which reflects the post-attack state).

Run this at the start of a new game day to close out yesterday's entry: record night deaths, confirm survival, and update the daily-log index.

## Step 1 — Resolve town, current day, and previous day file

- Read `.env` in the project root and note the `FATAMORGANA_TOWN_ID` value.
- Call `get_town_overview` to get the current town name and **current game day number N**.
- List subdirectories under `towns/` (excluding `_template`). Match the town name to the correct folder (case-insensitive slug match, convention `s{season}-{slug}`).
- If no match is found, stop and tell the user.
- Previous day number = N − 1. Previous day file = `towns/{folder}/day-{NN-1}.md` (zero-padded to 2 digits).
- If the previous day file does not exist, stop and tell the user.
- Read the previous day file fully. Extract:
  - The **last alive count and citizen list** logged (from the final cron check or manual check section).
  - The **last known defense** and tonight's attack estimate (look for the most recent values).
  - The **last critical items baseline table**.
  - Who was **outside at end of day** (last positions snapshot).

## Step 2 — Fetch current morning state

Call in parallel:
- `get_citizen_positions` — current alive count, who is inside/outside, and (if exposed by the tool) any dead citizens.
- `get_defense_status` — current defense total and tonight's estimate (this is now Day N's estimate).
- `get_bank_inventory` — current bank.

## Step 3 — Reconstruct the night outcome

- **Deaths:** Compare the previous day's last citizen list to today's alive list. Anyone present yesterday but absent today died overnight.
  - Cross-reference with who was outside at end of day: if they were outside → "zombie attack while camping". If they were inside → "unknown / likely infection or wound".
- **Survival verdict:** If the town has citizens alive today, it survived. Note: the previous day's defense vs. the previous day's attack estimate (partial or confirmed).
- **Net alive change:** yesterday's last count → today's count.

## Step 4 — Append night outcome to previous day file

Append a section at the end of `towns/{folder}/day-{NN-1}.md`:

```
---

### Night outcome — {date of the attack night, e.g. "Mar 24 → 25"}
**Result: SURVIVED** (or FAILED if applicable)
**Defense:** {final defense from last Day N-1 snapshot} vs **{attack estimate}** zombies
**Alive after:** {today's count} ({yesterday's last count − deaths} — {N deaths} overnight)

#### Deaths
| Citizen | Last position | Cause |
|---|---|---|
| **Name** | [x\|y] or IN TOWN | Zombie attack / Infection / Unknown |

*(No deaths — all survived the night.)* [use this line if zero deaths]
```

If the bank changed significantly overnight (items built or deposited before the attack that weren't in the last baseline), note it briefly.

## Step 5 — Update daily-log.md

In `towns/{folder}/daily-log.md`, find the row for Day N−1. Replace the **TBD** outcome cell with:

- `Survived` if no deaths overnight.
- `Survived · {Name} †` for each death (comma-separated if multiple).
- `FAILED` if the town did not survive (all dead).

Also update the alive count cell if it changed from what was originally logged.

## Step 6 — Report to user

Tell the user:
- Which previous day file was updated (`towns/{folder}/day-{NN-1}.md`)
- The outcome: survived/failed, how many deaths, who died
- The current Day N state at a glance (alive count, defense, tonight's estimate)
