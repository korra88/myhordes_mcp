# Expedition Planning — Mechanics & Lessons

Hard-won rules for planning long desert trips. These mechanics interact in non-obvious ways — raw AP+EP totals are misleading without understanding the restore-to-max rule and thirst step counter.

## Movement & Distance

**Two different distance metrics coexist in MyHordes:**

| Metric | Used for | Formula | [0\|0] to [-1\|15] |
|---|---|---|---|
| **Manhattan** | Movement cost (AP/EP spent) | \|Δx\| + \|Δy\| | **16 zones** |
| **Chebyshev** | EP activation, skill ranges, km display | max(\|x\|, \|y\|) | 15 km |

- Movement is **rook-style** (orthogonal only — up/down/left/right). No diagonal movement.
- "Distance from town" for EP activation, Heroic Return, Rescue, etc. uses **Chebyshev**.
- This mismatch means a zone at "15 km" can cost **16 AP** to reach. Always calculate Manhattan distance for AP budgets.

## Exploration Points (EP)

### Daily EP income
| Source | EP | Refreshes mid-day? |
|---|---|---|
| Scout (Camouflage Vest) | 2 | No — one-time daily grant |
| Worn-out Sports Shoes | 1 | **Yes** — regens when using a 4+ AP item |
| Mountain Bike | 2 | **Yes** — same regen trigger |
| Shoes + Bike combined | 3 | Yes (each item regens its own contribution) |

### EP regen triggers
When you consume an item that **restores 4+ AP** (food, water, twinoid, alcohol, anabolics), each equipped mobility item (shoes/bike) regenerates its daily EP contribution. The base Scout 2 EP do NOT regen.

Special cases:
- **Twinoid 500mg:** triggers shoe/bike regen AND gives **+1 EP above maximum** (unique to Twinoid).
- **Bloody Hot Coffee:** always gives +1 EP regardless of equipment.
- Regen is capped at the item's daily amount. You can't exceed max EP (except via Twinoid bonus).

### EP activation zone
- EP is consumed **before AP** when you are at **Chebyshev distance ≥3 km** from town.
- EP **cannot** be used at ≤2 km from town (those zones always cost AP).
- EP cannot be used for actions (repairs, debris clearing) — movement only.
- Exception: entering an Explorable Ruin costs EP (treated as movement).

### Example: Scout with Shoes
Daily: 2 (scout) + 1 (shoes) = 3 EP, max 3.
Using food (6 AP, ≥4): +1 EP (shoes regen). Using Twinoid (8 AP): +1 EP (shoes) + 1 EP (bonus) = +2 EP.
Total EP in a day with food + twinoid + water: 3 + 1 + 2 + 1 = **7 EP**.

## Thirst Step Counter

**Separate from the overnight thirst chain.** Walking in the desert triggers thirst on its own:

| Total zones walked | Effect |
|---|---|
| 11 | → **Thirsty** (-5 watch, visible debuff) |
| 22 (11 more while Thirsty) | → **Dehydrated!** (die at midnight, -3 survival) |
| 33 (11 more while Dehydrated) | → **Instant death** (no Meaty Bone if outside) |

Critical rules:
- **Counter does NOT reset** by returning to town and going out again.
- **Drinking water resets the counter** AND clears the current thirst level (if not Dehydrated).
- **Hydratone** clears Thirsty status but does NOT give AP and does NOT give Refreshed.
- Drinking while **Dehydrated** only improves to Thirsty — no AP, no Refreshed. Need to drink AGAIN for AP.
- The counter interacts with Refreshed: you can be **Refreshed AND Thirsty** (from step counter). Refreshed protects from overnight thirst chain, but not from step counter progression.

## AP Consumables — The Restore-to-Max Rule

**THIS IS THE #1 EXPEDITION PLANNING TRAP.**

Food, water, and alcohol **restore AP to maximum** — they do NOT add AP. If you have 5 AP and eat, you go to 6 (net +1), not 11.

| Consumable | Sets AP to | EP trigger | Status given |
|---|---|---|---|
| Basic food | 6 (max) | Yes (≥4) | Fed |
| Premium food | 7 (max+1) | Yes | Fed |
| Water Ration | 6 (max) | Yes (≥4) | Refreshed |
| Alcohol | 6 (max) | Yes (≥4) | Drunk |
| Twinoid 500mg | **8 (max+2)** | Yes + bonus EP | Drugged |
| Anabolic Steroids | 6 (max) | Yes (≥4) | Drugged |

**Consequence:** Always consume AP items at **0 AP** for maximum value. Consuming at any other AP wastes the difference.

### Optimal consumable ordering
For a long expedition, sequence consumables so each one lands at 0 AP:

1. Walk until 0 AP → use **highest-value** consumable (Twinoid: 8 AP + 2 EP)
2. Walk until 0 AP → use **next** consumable
3. Walk until 0 AP → use **last** consumable

**Never stack consumables.** Using Twinoid at 0 AP (→8) then immediately drinking water (→6) WASTES 6 AP because water resets to max=6, overwriting the 8.

### Thirst constraint on ordering
If the trip exceeds 11 zones, you MUST drink water before the step counter hits 22 (Dehydrated). This may force you to drink water at non-zero AP.

**Minimize waste:** arrange the trip so you hit 0 AP at a step count between 11–21. This lets you drink for full AP value AND clear Thirst in one action.

**Worked example (Scout + Shoes, [0\|0] to [-1\|15] round trip):**
- Twinoid at step 9 (outbound, 0 AP) → +8 AP, +2 EP
- Water at step 19 (return, 0 AP, Thirsty c=19) → +6 AP, +1 EP, clears Thirst
- Food at step 26 (return, 0 AP) → +6 AP, +1 EP
- All three at 0 AP = zero waste. Total: 26 AP + 7 EP = 33 movement for 30 zones.

## Rescue & Heroic Return

| Skill | Level | Range (Chebyshev km) | Notes |
|---|---|---|---|
| Heroic Return | R1/R2/R3/R4 | 9/11/13/15 | Self-teleport home. Works even with gate closed or Trapped. |
| Rescue | U1/U2/U3 | 1/2/3 | Used from town, teleports a citizen in range home. |
| Rescue | U4 | — | Rudimentary healing (removes Thirst/Infection on others). |

- Rescue is cast by someone **in town** — the rescued citizen doesn't spend AP.
- Heroic Return and Rescue both use **Chebyshev distance** for range.
- Rescue can save a stranded citizen as a safety net at the end of a trip.

## Expedition Planning Tables

When presenting a trip plan, always include a step-by-step table with the thirst status column. The goal is to **return to town without Thirst** — avoid consuming extra water just to clear a status on the doorstep.

Required columns: **Step · Zone · AP before · Action · AP after · EP · Thirst counter · Thirst status**

Example format:

| Step | Zone | AP | Action | AP after | EP | Counter | Thirst |
|---|---|---|---|---|---|---|---|
| 1 | [0\|1] | 6 | move | 5 | 2 | 1 | OK |
| 2 | [0\|2] | 5 | move | 4 | 2 | 2 | OK |
| 3 | [0\|3] | 4 | move (EP) | 4 | 1 | 3 | OK |
| … | … | 0 | consume food | 6 | … | … | OK |
| 11 | [0\|x] | … | move | … | … | 11 | **Thirsty** |
| … | … | 0 | consume water | 6 | … | 0 | OK (reset) |

**Thirst status values:** `OK` · `Thirsty` (step ≥11) · `Dehydrated` (step ≥22, dies at midnight) · `Dead` (step ≥33)

**Goal:** plan consumable timing so the water is consumed at or before step 11, resetting the counter, and the return leg ends at step ≤10 (no Thirst on arrival). If a second water is unavailable, aim to arrive Thirsty rather than Dehydrated.

## Expedition Checklist

Before sending anyone on a long trip:

1. **Calculate Manhattan distance** (|Δx| + |Δy|) both ways. If rescue is planned, subtract saved zones.
2. **Count AP-only zones** (Chebyshev ≤2km from town, both legs).
3. **Total EP available** (daily + regen triggers from each consumable).
4. **Plan consumable order** — each at 0 AP, respecting thirst counter (drink between steps 11–21).
5. **Verify thirst timeline**: which step triggers Thirsty, when must water be consumed.
6. **Show the full step table** with thirst status column — goal is to return without Thirst.
7. **Check route safety**: scouted vs unscouted zones, zombie counts, camouflage reliability.
8. **Confirm rescue availability** if the plan depends on it.
9. **Loadout check**: items consumed en route free slots for loot coming home.

## Common Mistakes (from experience)

- **Using Chebyshev for AP budget.** [-1\|15] is "15 km" but costs 16 AP to walk.
- **Treating food/water as additive.** "6 AP base + 6 food + 6 water = 18" is only true if each is consumed at 0 AP.
- **Ignoring the step counter.** Overnight thirst (not Refreshed) and step-counter thirst (11 zones) are independent. You can be Refreshed and still become Thirsty from walking.
- **Stacking consumables.** Using Twinoid (→8) then water (→6) wastes everything above 6.
- **Forgetting EP zone restrictions.** EP don't work within 2km of town — those zones always cost AP.
