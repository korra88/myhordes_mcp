# Camping: Fata plan upgrades, multi-night chain, nearby defensive items: plan

> **Since 2026-11-21 `get_camping_odds` and `plan_group_camping` are one tool, `plan_camping`**
> (`fata/campplan.py` picks the engine: one camper and one night → `camping.py`, else `groupcamp.py`;
> docs/bot-eval-plan.md 6.8). The tool names below are the old ones.

Status: **approved 2026-11-20, implemented 2026-11-20 (not committed); C changed by the user the same day, see below.** Changes to `plan_group_camping` (and, for A, to
`get_camping_odds` through the shared `camping.resolve_camp_level`). Builds on
`docs/group-camping-plan.md` (the solver, rules, objectives) and `docs/camping-plan.md`.

## The bug (measured on the bot's answer of 2026-11-20, town 8299)

Question: "camping plan for D28 to D31", Korra + Olbananaeyes (both Reclusive 2) at Strange Barn
[14|13]. On Fata, the D28 plan has `pre_existing_upgrades` 7.6 and `new_upgrades` 3
(units of 5% → level_before +38%, level_after +53%: 3 improves). The bot made **4 independent
calls** (`day=28..31`) and answered:

| Night | Start bonus in the answer | What the code computed | Correct |
|---|---|---|---|
| D28 | +38%, 0 AP ("nothing to do, at cap") | Fata zone estimate (= level_before) | +53% if the plan's 3 improves are done: say "check in game" |
| D29 | +38%, then 1 improve → +43% | D28 plan level_after 53 − 15 | 38 ✓ |
| D30 | +23% | D28 plan level_after 53 − 30 (`before` branch, camping.py ~L330) | D29 after 43 − 15 = **28** |
| D31 | +8% | 53 − 45 | D30 after − 15 |

Two defects:
1. **Tonight ignores the Fata plan's upgrades** but later nights assume them (contradiction).
2. **Each night is projected from the last REAL Fata plan**, never from the tool's own plan for
   the night before: the upgrades it recommends for D29 vanish on D30.

## A. Fata plan upgrades are part of the night's plan

Applies wherever a Fata plan for the night on the zone is used (`typed` in
`resolve_camp_level`: `mine`, or the zone's plans when they agree on level_before), tonight AND a
future night, in both tools.

- When `camp_level` is NOT given (-1) and the plan has `level_after > level_before`:
  starting level for the solver = the plan's **level_after**; the plan's upgrades are reported as
  part of the plan, not re-planned. Tonight: "Fata plan (<creator>): upgrades for +15%
  (+38% → +53%). Not a game reading: check in game whether they are done; if not, do them first
  (3 improves = 3 AP, fewer with defensive items)". Future night: "planned in <creator>'s Fata
  plan for day N: upgrades for +15% (+X% → +Y%), counted as done". Improves = round(pct / 5).
- If Fata's zone estimate (`z["camp_level"]`) differs from the plan's level_before, say so in the
  assumptions (one line), and use the plan's numbers.
- `camp_level` given (>= 0) still wins: it is the level **now**; the plan's upgrades are not added
  and the plan line is not printed (the solver then recommends what is needed).
- The AP of the plan's upgrades count in that night's AP total (tonight shown as
  "+3 AP if not done yet").
- Factor the detection into one helper (e.g. `plan_upgrades(typed) -> dict | None` with creator,
  before, after, pct, improves) used by both tools; `resolve_camp_level` must expose it to the
  caller (return a small dataclass or an out-dict; do not parse `assumed` strings).

## B. Multi-night chain in ONE call

New arg `until_day: int = 0` on `plan_group_camping` (0 = only the night `day`). Nights planned:
`first = day or today` … `until_day`, iteratively (the user's "recursive" idea as a loop).

- **Limits**: `until_day < first` → error; at most `MAX_NIGHTS = 6` nights → error saying so.
- **Campers fixed** by the first night's resolution (group "" → that night's / latest earlier
  plan; named → as given). Later nights reuse the same campers; if a real Fata plan for a later
  night on the zone has a different camper set, one assumption line says so (keep the first set).
- **Per camper per night**: nights survived = first night's value + k (k = nights since first;
  an explicit `nN` override also gets + k). Graves never carry (tg_tomb is volatile: reset each
  night), so `tomb` from a plan/override applies only to the night it belongs to. Vest, skill,
  job, camp items carried: unchanged.
- **Zone level**: night 1 as today (A included). Night k > 1:
  - a real Fata plan for that night on the zone → its numbers (A: level_before + its upgrades);
    if the chained value differs, one assumption line "Fata plan for day N types +X%; the chain
    from night N−1 gives +Y%".
  - else `max(0, level_after(night k−1) − NIGHTLY_DROP)` where level_after is the zone level
    after ALL upgrades planned that night (plan upgrades + solver improves/installs/boosted dog).
  - Zombies per night: existing projection (`zone_reading(data, cell, night)` per target day).
- **Finite pools across nights**: `defense_items` (consumed per install) and `steaks` (consumed per
  boosted dog use) are decremented night by night: a later night only sees what is left. Camp
  items (Groundsheet / Festering Flesh) are NOT consumed: same pool every night. Dog use: one per
  Tamer per night. Defensive items lying on the camp zone itself (Fata items of the zone from
  today, `risk.is_defense`) are added to the pool automatically, like camp items and steaks are
  today (say so in the assumptions).
- **AP**: `ap` = per-night group budget (AP reset every night); -1 unlimited. Per night, compare
  the AP needed (plan upgrades + improves + installs + paid graves) with the base daily AP of the
  group, 6 × campers. Above it: warning "Night N needs X AP, more than the 6 each the group has:
  drink/eat for AP, or do K of these improves the night before (each +5% carries over, −15% a
  night)" — K = how many of the excess the previous night could absorb while its level stays
  < 50 at the time of each improve. Joint optimisation across nights is NOT modelled (greedy:
  each night the cheapest plan for that night); say it in the docstring, not in the output.
- **Optional carry-over line** ("for later nights only") is suppressed when `until_day` is used:
  the chain covers the later nights.
- Survival assumed each night (campers alive next night): one assumption line.
- Runtime: one solve per night. Measure 6 campers × 6 nights on the PC (worst you try) and report;
  typical 2-3 campers is < 1 ms per night.

### Output (condensed; numbers illustrative)

```
## Group camping — <town> Day 28
Nights 28–31, Korra and Olbananaeyes at [14|13] Strange Barn (3 places), 19 km. Each night starts
from the previous night's plan (−15% overnight); nights after tonight are projections.

Night 28 (tonight): +38% now (Fata estimate). Fata plan (Korra): upgrades for +15% → +53%: check
  in game whether done; if not, 3 AP first. Nothing more needed. Korra 90%, Olbananaeyes 90%
  (cap), any order. Survivors 1.80/2.
Night 29: starts +38%. 1× improve (1 AP) → +43%. Korra 90%, Olbananaeyes 90%, any order.
Night 30: starts +28%. 5× improve (5 AP) → +53%. ...
Night 31: starts +38%. ... 2 graves (Korra, Olbananaeyes) ...
AP per night: 0 (+3 if not done) / 1 / 5 / 6 — the group has 12 a day (6 each).
Items: defensive 0 used (0 available); steaks 0.
Nearby defensive items (round trip from the camp; AP of the trip are not available for upgrades):
  [15|13] 1 km away, 2 AP round trip (+1 install): Old Door (heavy) — 0 zombies (day 28)
  ...
Assumptions: <deduplicated across nights>
```

Per night: one line when "any order"; the hiding-order list (as today) only when the order
changes the odds. Single-night calls (`until_day` 0): output as today, plus A and C.

## C. Defensive items near the camp (a light signal, user decision 2026-11-20)

C is a SIGNAL, not a planning input: AP for a trip compete with upgrade AP, so the tool only points
out items worth fetching. (Supersedes the earlier "shown only when useful" rule.)

- Block "Defensive items near the camp": zones (not the camp zone: its own floor items are in the
  pool) holding defensive items (`risk.is_defense`, as `pickups.resolve` uses), Manhattan distance
  d <= 12 from the camp, nearest first, **at most 3 zones** (+ "N more" line). Per zone: coords, d,
  round trip `2d` AP (+1 to install), items (`fmt_items`, heavy marked, "one per camper per trip"),
  zombies as last seen and freshness (`_zone_threat` / `_zone_freshness`).
- One reach line: d <= 3 with the day's 6 AP; <= 6 with water or food; <= 9 with water and food;
  <= 12 with a drug too. Inventory unknown: not assumed. EP not counted; zombies on the way ignored.
- **Shown whenever** at least one such zone exists within d <= 12.
- One hint line: the nights with spare AP (6 x campers minus that night's needed AP >= the nearest
  round trip + 1): "Good nights to fetch: 28, 29" (single night: the same test for that night);
  none: omitted. With 3+ campers: "one can fetch while the others upgrade".
- One pointer line: "For an exact route: find_expedition_path / plan_expedition_supplies with
  start = the camp (x,y), round trip." (both accept an off-town start; the Observation Platform
  teleport and the Labyrinth cost apply only to trips starting/ending in town.) Same pointer in the
  `plan_group_camping` docstring.
- The items of the block are NOT added to the `defense_items` pool (only the camp zone's own floor
  items are).

## Also

- `main.py`: `until_day` arg + docstring: "multi-night question (e.g. 'plan D28 to D31') → ONE
  call with day=first and until_day=last; do NOT call once per night (each call alone does not
  know the upgrades planned for the nights before)". Mention the nearby block appears only when
  useful. `get_camping_odds` docstring: for several nights use plan_group_camping until_day.
- Primer (`prompts/game-primer.md`), camping lines: one line for the multi-night call and one for
  "Fata plan upgrades = check in game whether done".
- No new tool ⇒ no Pi toml change; primer changed ⇒ listener restart at deploy.
- Tests: `tests/camping_checks.py`: the 2026-11-20 chain (53 → 38, +1 → 43 → 28 …), pools
  decrement across nights (2 defensive items, 3 nights needing installs → only 2 used), steaks,
  `nN` + k, grave not carried, MAX_NIGHTS / until_day < day errors, A tonight (start = level_after,
  line printed) and `camp_level` given (plan not added), nearby-block distance/tiers/visibility.
  Golden: 3-4 new cases on the v13 fixture (multi-night group, A tonight, nearby block shown).
  Do **not** run `tests/golden.py --update`: report which cases are new and which existing ones
  changed (A changes some `get_camping_odds` / `plan_group_camping` outputs on purpose).
