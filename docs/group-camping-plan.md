# Group camping planner: plan

Status: **approved 2026-11-18, not implemented.** One new MCP tool, `plan_group_camping`, that
answers "how should our group camp on this zone tonight / on day N?": who hides in which order,
who digs a grave, who carries which camp item, how many upgrades, with every camper's odds.

Builds on `fata/camping.py` (formula verified 60/60 against Fata's planner, docs/camping-plan.md
§1.2-1.3) and the Fata camp plans (`towndata.camp_plans`, `plans_for_*`).

## Rules (verified in the game source, myhordes-docker/myhordes)

- Odds per camper = sum of `camping_terms` / 100, clamped to [0, cap] (`CitizenHandler::getCampingValues`).
- **Crowd** (`campers`): by citizens already hidden on the zone when this one hides:
  `[0, 0, -10, -30, -50, -70]`. **Ruin room**: ruin bonus while `hidden_before < camp_slots`,
  else -25 (`ruin_term`). Both depend on the hiding order.
- **Improve campsite** `cm_campsite_improve`: 1 AP, +5 to the zone, anyone in the group.
  **Install a defensive item** `improve`: 1 AP + the item (CONSUMED, `consume_item`), +9. Both only
  while the zone level is < 50 (the last action may cross it). The zone level is shared.
- **Grave** `cm_campsite_tomb`: 1 AP of the camper themself, +8 to that camper only (`tg_tomb`).
- **Camp items**: Groundsheet (`sheet_#00`, Fata item 46) and Festering Flesh (`smelly_meat_#00`,
  Fata item 231): +5 each **in the hiding camper's rucksack**, not consumed
  (`countSpecificItems(inventory, 'camp_bonus')`). They can be handed to whoever needs them; each
  takes a rucksack slot: at most `slots` per camper (default 5, conservative).
- **Tamer's dog** (`hero_tamer_5`): digs the Tamer's grave for free (0 AP), one use. Fed with a
  Tasty-looking Steak (`meat_#00`, Fata item 44, consumed by `hero_tamer_3`), the dog's version
  `hero_tamer_5b` digs the grave **and** improves the zone +5 (needs the zone improvable). One dog
  use per Tamer; boosted uses <= steaks available. A Tamer = job `tamer` in Fata (or declared).
- Stated in the output, not modelled: "tired" (0 AP: AP are a group total anyway), dog uses
  already spent today, zombies arriving before hiding (they count at hide time).

## User decisions (2026-11-18)

Objectives, lexicographic:
1. **Survival**: default `objective="expected"` = maximise the sum of capped odds (expected
   survivors), ties: maximise the lowest. Option `objective="weakest"`: maximise the lowest first,
   then the sum. At or above the cap counts as the cap (surplus is worth nothing).
2. Fewest **defensive items** (prefer plain improves).
3. Fewest **paid graves** (a grave helps one camper, an improve helps all and carries over).
4. Fewest **AP** (improves + installs + paid graves).
5. Fewest steaks, then fewest dog uses (free, but kept for other uses).
6. Ties: keep the order of the Fata plan if there is one, else a stable order.
- AP are **one group total**. AP beyond the best plan go to a separate **carry-over** line at
  the end: "Optional, for later nights only: N× improve → +X% that night, +Y% left the next
  night (only the bonus above +15% survives)". Shown only when Y > what the plan leaves.
- Show the hiding order explicitly ("1st", "2nd", ...) when it changes the odds; when it does not,
  say "any order".

## Tool

`plan_group_camping(x=None, y=None, group="", day=0, ap=-1, defense_items=0, camp_items=0,
steaks=-1, slots=5, camp_level=-1, hidden_before=0, objective="expected", town_id=0)`

- **Zone**: x/y, else the zone of the group's Fata plan for that night (same lookup as
  `get_camping_odds`, incl. an earlier plan for a future night).
- **day**: same meaning and projection rules as `get_camping_odds` (0 = tonight; future = from
  today's data: zombies today's count, camp bonus from that night's plan, else an earlier plan on
  the zone minus 15 a night, else today's level minus 15 a night).
- **group**: "" = the campers of the Fata plan(s) for that night on the zone (for a future night
  without one: the latest earlier plan on the same zone). Else a comma list of names, each with
  optional overrides after colons: `Korra:R2:n2, Ammonia:R4:n2:tomb:items=1, Bob:tamer:vest`
  (`R1-R4`/`pro`/`none` hero skill, `nN` nights survived, `tomb` already dug, `items=K` camp items
  carried, `vest`, `tamer`, `surv` Survivalist). Per camper, defaults in this order: override >
  that night's plan entry > earlier plan entry (nights + nights in between, as get_camping_odds) >
  camping log (nights) > job from Fata citizens (Survivalist cap, Scout vest, Tamer) > none/0.
  Unknown names → error listing the closest living citizens. Max 6 campers (more = error: say so).
- **ap**: group AP for upgrades and graves; -1 = unlimited: the plan says how many it needs.
- **defense_items**: defensive items available (consumed when installed).
- **camp_items**: extra Groundsheets / Festering Flesh available besides what the campers carry
  (plan `camping_aids`/overrides); plus those on the zone floor when the zone's Fata items are
  from today (zone item ids 46, 231; say so).
- **steaks**: -1 = those on the zone floor (item 44, zone updated today), else the number given.
- **hidden_before**: citizens outside the group already hidden on the zone.
- Reuse camping.py functions (`camping_terms`, `camping_odds`, `odds_cap`, `ruin_term`, the zone /
  day / projection helpers): refactor the shared "zone context" out of `format_camping_odds` rather
  than copying it; `get_camping_odds` output must not change (goldens).

## Search

Exact, not heuristic. Suggested: enumerate (improves i, installs j, boosted dog uses s) feasible
under the level rule; for each zone level, enumerate hiding orders (n! <= 720) and, per order,
allocate graves and camp items with a small DP / exhaustive search over the shared pools (items,
AP). Prune by the objective. **Runtime target: < 0.3 s for 6 campers on the PC** (the Pi 3B+ is
~10× slower; measure and report both the PC time and the worst case you tried).

## Output (condensed, the server is used by small models; numbers below are illustrative)

```
## Group camping — <town> Day 26
Night of day 27 (tomorrow): a projection from today's data.
Zone [14|13], Strange Barn (3 places), 19 km. Camp bonus now +0% (<source>). 0 zombies (today).

Plan: 2× improve (2 AP), no item, no grave → camp bonus +10%. Everyone at their cap.
Hiding order (after the upgrades, after 19:00):
  1st Ammonia  (Scout, Reclusive 4, 2 nights, grave, 1 Groundsheet)  99% (cap 99)
  2nd Korra    (Guardian, Reclusive 2, 2 nights)                     90% (cap 90)
  3rd Olbananaeyes (Technician, Reclusive 2, 2 nights, grave, 1 item) 90% (cap 90, -10 crowd absorbed)
Expected survivors 2.79 / 3.

Optional, for later nights only: 4× improve (4 AP) → +30% that night, +15% left the next night.
Assumptions: ...
```
Per camper only the terms that differ between campers if needed for the "why"; no full breakdown
per camper (get_camping_odds does that).

## Also

- main.py tool + docstring (when to use it vs get_camping_odds: a group / "who hides first" /
  "who digs a grave" → this tool; one camper → get_camping_odds; do NOT call get_camping_odds per
  camper for a group question). get_camping_odds docstring: one line pointing to it.
- Primer (prompts/game-primer.md) one line; KB `knowledge/tactics/game-mechanics.md` camping:
  grave 1 AP self only, camp items in the rucksack, dog grave / steak.
- `discord-listener.example.toml`: add the tool to both `allowed_tools` lists (the Pi toml is
  edited by the maintainer session at deploy).
- CLAUDE.md "Current state" list.
- Tests: `tests/camping_checks.py` (pure search: small hand-made groups with known optimum —
  crowd absorbed by the camper with most surplus, ruin room, grave only when improves cannot
  reach the cap, items to the right camper, slots limit, steak/dog, objective switch, AP limit,
  runtime) and 3-4 golden cases on the v13 fixture (Korra's group tonight, day 27, a tamer case,
  an AP-limited case). Do not run `tests/golden.py --update`: report new/different cases.
