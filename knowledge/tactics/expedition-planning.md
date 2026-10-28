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
| Second Wind (hero skill) | +3/+3/+4/+4 AP (Enduring level 1/2/3/4), up to max | +1/+3/+4/+6 EP, even above max; the day's heroic action |

- Max AP 6, **5 when wounded** (7 AP food then gives 6).
- Second drug the same day → **addict** (permanent; an addict not drugged at night dies).
- Each item takes a rucksack slot; a Water Cooler Bottle holds 3 rations in one slot.

## Rucksack capacity

Keywords: rucksack, backpack, bag, slots, space, carry, carrying, inventory.
Checked in `InventoryHandler::getSize`.

- **4 slots** for a resident. Profession tools and the uniform add their own slot (they
  never take free space). Hero skills add 1–3 slots (wiki: a hero has 5; "A place for
  everything" adds more).
- Ultra-Rucksack or Shopping Trolley +3, else Manbag +2; Utility Belt +2 stacks with them.
  The container takes a slot itself: net +2 / +1 / +1. The Shopping Trolley is heavy.

## Digging (scavenging a zone)

Keywords: dig, digging, scavenge, scavenging, search, auto-search, dried, depleted,
exhausted zone, find items, dig all day.
Checked in `CitizenChanceQueryListener::getDigChances`, `ZoneHandler`, `MapMaker`, town defaults.

- **Chance per dig: 60%**, **80% for a Scavenger**. A **dried / depleted** zone: **35%**
  for everyone (no profession or status bonus there), and it gives only Rotting Log and
  Scrap Metal (wiki).
- Night (in-game 19:00–06:59): −10%, a quarter of that with a light (Torch, lit lamp) on
  the zone floor. Not depleted only: Learned Camper +10%, Drunk −20%, eye wound halves it.
  Result kept between 10% and 90%.
- After the first dig, **auto-search every 2 h** (Scavenger 1 h 30) while you stay in the
  zone. **One dig per zone per day**: leaving stops it, and the zone cannot be dug again
  until midnight (`desert_dig_api`: a dig timer on the zone refuses a new dig; timers are
  cleared at night; the town option "allow redig" is off by default).
- A zone starts with **4–8 finds**; each successful dig uses one; at 0 it is dried. Night
  winds can refill zones in one compass direction (the Search Tower shows which).
- "Dig all day": every 2 h × 60% is about one item every 3 h 20 min, so a day's dig fills
  2–4 slots: leave rucksack space for it.

## Route shape: a loop, ending off the axes

Keywords: route, loop, return path, way back, same zones, teleport, observation platform,
axis, row 0, column 0, diagonal, farthest, max distance, AP budget.

- `find_expedition_path(..., round_trip=True)` plans this loop: way back over other zones,
  ending on the best teleport zone, with the round-trip AP and the AP saved.
- **Go out and come back over different zones.** Each zone can be dug once a day, so a
  return over the outbound zones finds nothing new to dig.
- **With the Observation Platform, end the walk on a diagonal zone, not on row 0 or
  column 0.** The teleport works by km (rounded straight line) but walking costs
  |x| + |y|: the farthest walk it saves is off the axes.

| Platform | Teleports from | Best last zone | AP saved | On an axis |
|---|---|---|---|---|
| level 3 | 1 km | [±1\|±1] | 2 | [±1\|0] saves 1 |
| level 4 | 2 km | [±2\|±1], [±1\|±2] | 3 | [±2\|0] saves 2 |

  The gate must be open for the teleport; it is not a move (no thirst).
- **Budget example** (level 4, water + 7 AP food, used when AP hit 0): 6 + 6 + 7 = 19 AP
  walked + 3 saved = 22 AP of round trip → farthest zone **11 AP** away: 11 out, 8 back to
  [2|1], teleport.

## Heavy items and defensive objects

Keywords: heavy, carry, defensive objects, defence, defense items, DO, guardian shield.
Checked in the game code: `InventoryHandler::getHeavyItemSize`, items with `heavy(true)`.

- A citizen carries **one** heavy item. A Guardian with the shield lowered (`shield_off`)
  carries **two**, but loses the shield's 2 zombies of protection; the night raises the
  shield again (`NightlyHandler`). A heavy item still takes a rucksack slot.
- **Defensive objects** (item property `defence`, Fata category Defences; each one in the
  bank adds defense). Heavy: Old Door, Sheet Metal, Solid Wooden Board, Trestle, Unshaped
  Concrete Blocks, Järpen Table, Mattress, Car Door. Light: Guard Dog, Mangy Dachshund,
  Torch, Lit Pumpkin.
- **Incomplete defensive objects** (heavy, worth carrying, assembled later): Sheet Metal
  (parts), Crate Lid, Bag of Cement, Flatpacked Furniture, Car Door (incomplete).
- **Heavy resources:** Patchwork Beam, Metal Support, Engine.
- Heavy weapons: Lawnmower, Chainsaw, Kalashni-Splash, Retro Overhead Projector, Stake
  Launcher, appliances (Washing Machine, Oven, Beer Fridge, PC Base Unit, chairs).
- Other heavy items: boxes and chests, big furniture, water dispensers, Mountain Bike,
  Shopping Trolley, corpses, Huge Snake and Stinking Pig.

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
- **One heroic action per day**: Second Wind, Heroic Return and the other hero actions share
  one daily use (status `tg_hero`, cleared at night). Using Second Wind on the way out
  means no Heroic Return that day; a Rescue cast by another citizen still works.
- **Rescue** (km, cast from town on a citizen outside): U1/U2/U3 = 1/2/3 km. The rescued
  citizen spends no AP. Safety net for a stranded citizen.

## Common player mistakes

- Using km for the AP budget: [-1\|15] is "15 km" but 16 moves.
- Adding food/water as "+6 each": they only refill to max.
- Drinking twice to reset the counter when not thirsty: refused.
- One ration for Dehydrated: only makes you Thirsty.
- Expecting EP back without shoes/bike.
