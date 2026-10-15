# Expedition Planning — Mechanics & Lessons

Hard-won rules for long desert trips. Mechanics interact non-obvious — raw AP+EP totals mislead without restore-to-max rule and thirst step counter.

## Movement & Distance

**Two distance metrics in MyHordes:**

| Metric | Used for | Formula | [0\|0] to [-1\|15] | [0\|0] to [2\|2] |
|---|---|---|---|---|
| **Manhattan** | Movement cost (AP/EP spent) | \|Δx\| + \|Δy\| | **16 zones** | 4 zones |
| **km** | EP use, Observation Platform teleport, km display | round(√(x²+y²)) | 15 km | **3 km** |

- Movement **rook-style** (orthogonal only — up/down/left/right). No diagonal.
- km is the rounded straight-line distance (game code `Zone::getDistance`), **not Chebyshev**.
  Heroic Return and Rescue ranges are in km too (not re-checked in code).
- Mismatch: zone at "15 km" can cost **16 AP**. Always use Manhattan for AP budgets.

## Exploration Points (EP)

Rules checked in the game code (v5.0.6).

### EP sources
| Source | EP | Notes |
|---|---|---|
| Scout | 2 | Daily, part of max EP. **Never refilled** by consumables. |
| Worn-out Sports Shoes | +1 | On equip, once a day. Refilled by consumables. |
| Mountain Bike | +2 | On equip, once a day (heavy slot). Refilled by consumables. |
| Scout's Lair (home action, 1 AP) | +4 scout / +2 others | Next morning. |
| Bloody Hot Coffee | +1 | Up to max EP. Also +4 AP (up to max AP), no daily limit. |

### EP refill from consumables
Water, food, alcohol, Steroids and Twinoid refill EP **only up to the shoes/bike part**
(shoes 1 + bike 2), never the scout's 2. **Without shoes or bike: no EP at all.** Twinoid
refills one more than that (shoes only: up to 2). There is no "4+ AP item" rule.

### When EP is spent
- EP is spent **before AP** when the zone you are **leaving** is **3+ km** from town.
- km = straight-line distance, **rounded**: round(√(x²+y²)). Not Chebyshev, not Manhattan.
  [2|2] is 3 km (EP usable), [2|1] is 2 km (AP only), [3|0] is 3 km.
- Closer than 3 km moves always cost AP. EP is for movement only.

## Thirst Step Counter

**Separate from overnight thirst.** Every move adds 1 (paid with AP or EP). When the
counter passes 10, thirst goes up one level and the counter restarts at 0:

| Moves since the counter was 0 | Effect |
|---|---|
| 11 | → **Thirsty** |
| 22 | → **Dehydrated!** (dies at midnight unless cured) |
| 33 | → **Death** |

- **Only water resets it** (every drink, in every thirst state).
- **Not** reset by entering town, eating or **Hydratone** (Hydratone cures one thirst level, gives no AP, and is a drug).

## Drinking and eating — what the game allows

**THIS IS THE #1 EXPEDITION PLANNING TRAP.** AP items **raise AP to a level, they never add**:
5 AP + food → 6 (net +1), not 11. Use them at **0 AP**.

| Item | AP | Limits |
|---|---|---|
| Water, not thirsty | → max (6) | Once a day (Refreshed) and only below max AP. **A second drink while not thirsty is refused.** |
| Water, Thirsty | → max if not drunk yet today, else 0 | Clears Thirsty, resets the counter. Always allowed. |
| Water, Dehydrated | **0** | Only back to Thirsty (counter reset). A **second ration** clears thirst (and gives AP if not drunk yet today). |
| 6 AP food | → 6 | Once a day, only below max AP |
| 7 AP food | → 7 | Same (noodles, steak, tasty vegetable/dish, eggs...) |
| Anabolic Steroids | → 6 | Drug |
| Twinoid 500mg | → 8 | Drug |
| Alcohol | → 6 | Drunk; not when drunk or hungover (hungover the next day) |
| Bloody Hot Coffee | +4, up to max | +1 EP; no limit |

- Max AP is 6, **5 when wounded** (7 AP food then gives 6).
- **Drugs:** a second drug the same day makes you an **addict** (permanent; an addict who is not drugged at night dies). One drug a day.
- **Overnight:** no water at all during the day → thirst goes up one level at night; Dehydrated at night → death.

### Planning order
1. Walk to 0 AP, then use the item. Never two AP items in a row: the second overwrites the first.
2. Water when Thirsty and at 0 AP gives AP **and** clears thirst in one go: aim to hit 0 AP between move 11 and 21.
3. Drink at more than 0 AP only to avoid becoming Dehydrated (exception).
4. Each item is a rucksack slot: carry the minimum. A Water Cooler Bottle holds 3 rations in one slot.

**`plan_expedition_supplies` does all of this**: give it the waypoints, AP/EP, job/equipment
and what you can carry; it returns the items to bring, the slots, where to use each one,
and warnings. Report its plan instead of placing consumables by hand.

## Return to town
- **Observation Platform** level 3 / 4: teleport home from zones up to 1 / 2 km (same rounded
  km), gate open. Up to 3 moves saved (e.g. from [2|1]); a teleport is not a move (no thirst).
- **Labyrinth:** entering town from [0|0] costs 1 AP.

## Rescue & Heroic Return

| Skill | Level | Range (Chebyshev km) | Notes |
|---|---|---|---|
| Heroic Return | R1/R2/R3/R4 | 9/11/13/15 | Self-teleport home. Works even with gate closed or Trapped. |
| Rescue | U1/U2/U3 | 1/2/3 | Used from town, teleports a citizen in range home. |
| Rescue | U4 | — | Rudimentary healing (removes Thirst/Infection on others). |

- Rescue cast from **town** — rescued citizen spends no AP.
- Both use **Chebyshev** for range.
- Rescue = safety net for stranded citizen at trip end.

## Expedition Checklist

1. Route: `find_expedition_path` (safety, CP, traps).
2. Supplies: `plan_expedition_supplies` with the same waypoints, start AP/EP, scout/shoes/bike,
   thirst counter, what was already drunk/eaten/taken today, and what is available.
3. Check route safety: scouted vs unscouted zones, zombie counts, camouflage reliability.
4. Confirm rescue availability if the plan depends on it.
5. Loadout: items consumed on the way free their slot for loot coming home.

## Common Mistakes (from experience)

- **Using Chebyshev for AP budget.** [-1\|15] is "15 km" but costs 16 AP to walk (Manhattan).
- **Using Chebyshev for EP.** EP starts at rounded straight-line 3 km: [2|2] already counts.
- **Treating food/water as additive.** "6 AP base + 6 food + 6 water = 18" only if each is used at 0 AP.
- **Drinking twice to reset the counter.** Not thirsty and already drunk today → the game refuses.
- **One ration for Dehydrated.** It only makes you Thirsty; a second one is needed.
- **Hydratone for the counter.** It cures one thirst level but does not reset the counter, and it is a drug.
- **Expecting EP back without shoes/bike.** Consumables never refill the scout's EP.
- **Stacking consumables.** Twinoid (→8) then water (→6) wastes everything above 6.
