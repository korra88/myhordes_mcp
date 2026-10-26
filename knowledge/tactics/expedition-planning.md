# Expedition Planning — Mechanics & Lessons

Rules for long desert trips, checked in the game code (v5.0.6). **Do not compute plans from
this file**: the tools apply these rules exactly.

- Route, safety, CP, traps → `find_expedition_path`.
- What to carry, where to drink/eat, AP/EP/thirst per step → `plan_expedition_supplies`
  (same waypoints, start AP/EP, scout/shoes/bike, thirst counter, what was already
  drunk/eaten/taken today, what is available). Report its plan; never place consumables by hand.

This file is for explaining the rules to a player, or checking a tool answer that looks odd.

## Movement & Distance

| Metric | Used for | Formula | [0\|0] to [-1\|15] | [0\|0] to [2\|2] |
|---|---|---|---|---|
| **Manhattan** | Movement cost (AP/EP spent) | \|Δx\| + \|Δy\| | **16 moves** | 4 moves |
| **km** | EP, Observation Platform, Heroic Return, Rescue, km display | round(√(x²+y²)) | 15 km | **3 km** |

- Movement orthogonal only (no diagonal): a zone at "15 km" can cost **16 AP**.
- km is the rounded straight-line distance (game code `Zone::getDistance`), **not Chebyshev**.

## Exploration Points (EP)

| Source | EP | Notes |
|---|---|---|
| Scout | 2 | Daily, part of max EP. **Never refilled** by consumables. |
| Worn-out Sports Shoes | +1 | On equip, once a day. Refilled by consumables. |
| Mountain Bike | +2 | On equip, once a day (heavy slot). Refilled by consumables. |
| Scout's Lair (home action, 1 AP) | +4 scout / +2 others | Next morning. |
| Bloody Hot Coffee | +1 | Up to max EP. |

- EP is spent **before AP** when the zone you are **leaving** is **3+ km** from town.
  [2|2] is 3 km (EP usable), [2|1] is 2 km (AP only). EP is for movement only.
- Water, food, alcohol, Steroids, Twinoid refill EP **only up to the shoes/bike part**, never
  the scout's 2 (Twinoid one more). **Without shoes or bike: consumables give no EP.**

## Thirst Step Counter

Separate from overnight thirst. Every move adds 1 (AP or EP). Past 10 the thirst level goes
up and the counter restarts:

| Moves since the counter was 0 | Effect |
|---|---|
| 11 | → **Thirsty** |
| 22 | → **Dehydrated!** (dies at midnight unless cured) |
| 33 | → **Death** |

- **Only water resets it** (every drink, in every thirst state), and it restarts at midnight
  (`NightlyHandler`: walking distance 0). Not entering town, not
  eating, not Hydratone (cures one thirst level, no AP, and it is a drug).

## Drinking and eating

**AP items raise AP to a level, they never add**: 5 AP + food → 6 (net +1), not 11.
Used at 0 AP they give the most.

| Item | AP | Limits |
|---|---|---|
| Water, not thirsty | → max | Once a day (Refreshed), only below max AP. **A second drink while not thirsty is refused.** |
| Water, Thirsty | → max if not drunk yet today, else 0 | Clears Thirsty, resets the counter. Always allowed. |
| Water, Dehydrated | **0** | Only back to Thirsty. A **second ration** clears thirst. |
| 6 AP food | → 6 | Once a day, only below max AP |
| 7 AP food | → 7 | Same (noodles, steak, tasty vegetable/dish, eggs...) |
| Anabolic Steroids | → 6 | Drug |
| Twinoid 500mg | → 8 | Drug |
| Alcohol | → 6 | Drunk; not when drunk or hungover (hungover the next day) |
| Bloody Hot Coffee | +4, up to max | +1 EP; no daily limit |

- Max AP 6, **5 when wounded** (7 AP food then gives 6).
- Second drug the same day → **addict** (permanent; an addict not drugged at night dies).
- Each item takes a rucksack slot; a Water Cooler Bottle holds 3 rations in one slot.

## Heavy items and defensive objects

Checked in the game code: `InventoryHandler::getHeavyItemSize`, items with `heavy(true)`.

- A citizen carries **one** heavy item. A Guardian with the shield lowered (`shield_off`)
  carries **two**, but loses the shield's 2 zombies of protection; the night raises the
  shield again (`NightlyHandler`). A heavy item still takes a rucksack slot.
- **Defensive objects** (Armor category, all heavy): Old Door, Sheet Metal, Solid Wooden
  Board, Trestle, Unshaped Concrete Blocks, Jarpen Table, Mattress, Car Door.
- **Incomplete defensive objects** (heavy, worth carrying, assembled later): Sheet Metal
  (parts), Crate Lid, Bag of Cement, Flatpacked Furniture, Car Door (incomplete).
- Other heavy items: boxes and chests, big furniture, water dispensers, Mountain Bike,
  corpses, Python and Pig.

### Bringing defensive objects home (relay)

A play style for coordinated towns, not a rule:

1. Going out, pick up nothing but what the expedition needs (food, water, weapons).
2. Dig at the farthest point of the day.
3. On the way back, pick up a defensive object and carry it toward town; when a better
   one (or one closer to its goal) is on the path, swap it.
4. What is left on the ground is closer to town than before: another citizen, or you on
   another day, brings it the rest of the way.

Planning a run: dig zone as far as the AP allow (out and back on the same AP), not dried,
with defensive objects on the return path (`get_zone_details` lists the items per zone).
One object per citizen, two for a Guardian with the shield lowered.

## Return to town

For one zone, `get_zone_details(x1=x, y1=y, x2=x, y2=y)` prints moves, km, EP, and which
of these reach it (platform level and gate included).

- **Observation Platform** level 3 / 4: teleport home from zones up to 1 / 2 km, gate open.
  A teleport is not a move (no thirst).
- **Labyrinth:** entering town from [0|0] costs 1 AP.
- **Heroic Return** (km, Reclusive): R1/R2/R3/R4 = 9/11/13/15 km. Self-teleport home, gate closed or not.
- **Rescue** (km, cast from town on a citizen outside): U1/U2/U3 = 1/2/3 km. The rescued
  citizen spends no AP. Safety net for a stranded citizen.

## Common player mistakes

- Using km for the AP budget: [-1\|15] is "15 km" but 16 moves.
- Adding food/water as "+6 each": they only refill to max.
- Drinking twice to reset the counter when not thirsty: refused.
- One ration for Dehydrated: only makes you Thirsty.
- Expecting EP back without shoes/bike.
