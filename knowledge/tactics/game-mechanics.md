# Core Game Mechanics

## Action Points (AP)
- Players start 6 AP/day. AP used for moving, building, working.
- **Wounded** cuts max AP 6→5 (all AP sources restore 1 less). Heal with Bandage before midnight or citizen becomes Infected.
- **Exhausted** (0 AP): disables melee weapons, Scout/Scavenger Sense, desert entry.

## Return to town — Observation Platform teleport
- At **level 3 or 4** the Observation Platform adds a "return to town" option in zones near town: teleport straight inside, **saving up to 3 AP**. Level 3 = zones up to 1 km, level 4 = up to 2 km, where km = round(√(x²+y²)): [1|1] and [2|1] count, [2|2] (3 km) does not. (Season 19: 4 levels, each range unlocked one level earlier than before.)
- Works even **without Control or when Terrorised**, so it is an exit for a citizen trapped near town.
- **Gate closed → no teleport.** With the Labyrinth built it also skips the gate's AP cost; from the gate zone itself, entering still costs 1 AP (unless Ventilation System).
- AP-spent estimate for a returning citizen (used by inspect-town): `max(0, Manhattan(last_pos, [0|0]) − discount)`, discount **2 AP at level 3, 3 AP at level 4**. Not built → no discount.

## Free Actions (0 AP)
Eating, drinking, drugs, collecting water, searching zones, using weapons in desert, combining items, cooking, stealing, picking up/dropping items, taking from bank, estimating attacks.

## Other AP Sources
Dice (chance 1 AP), Cards (chance 1 AP), Makeshift Guitar (1 AP to all in town, 2 if Drunk/Drugged), Siesta Time (chance 2 AP), EMS System (up to 5 AP but causes Wound), Bloody Hot Coffee (up to 4 AP).

## Eating & Drinking
- Citizen eats only ONCE/day ("Fed" status). Basic food restores AP to max (6). Premium restores AP to max+1 (7 AP, or 6 if Wounded).
- First water ration restores AP to max (6), gives "Refreshed" status, resets thirst counter. Further drinks don't restore AP but can improve thirst status.
- Dehydrated citizen dies at midnight regardless of Refreshed status.
- Drinking when Dehydrated does NOT restore AP — only improves status to Thirsty.

### Thirst counter (in-desert movement)
- Moving through zones increments thirst counter. After **11 zones** since last water ration → **Thirsty**.
- **Thirsty and Refreshed are independent statuses** — both simultaneously possible. Drinking water ration gives Refreshed, resets counter; does not clear existing Thirsty.
- **Overnight progression depends on Refreshed, not Thirsty:**
  - Normal, not Refreshed → Thirsty at midnight
  - Thirsty, not Refreshed → Dehydrated at midnight
  - Thirsty + Refreshed → stays Thirsty next morning (no degradation, not reset to Normal)
  - Dehydrated → Death at midnight regardless of Refreshed status
- **Expedition goal:** return **Refreshed** — Thirsty + Refreshed on arrival is safe overnight. Returning without Refreshed risks overnight degradation.

## Alcohol
Restores AP to max (6), gives "Drunk" status. Drunk citizens suffer -20% scavenging penalty and scrambled forum/note messages. Next day → "Hungover", cannot drink alcohol. Exception: Ergot Homebrew consumable while Drunk or Hungover.

## Drugs
Taking drug gives "Drugged" status, restores AP. Second drug while Drugged → "Hooked!" status — permanent, irreversible. Hooked citizen MUST take drug every day or die from withdrawal overnight.

## Midnight Attack
Every night at 23:59 CET, zombie horde attacks. Town total defense must exceed zombie attack estimation or citizens slaughtered. Town Gates MUST be closed before attack, usually after 23:00, or if every citizen is in town.

**Unfilled towns:** Town without 40 citizens by midnight — attack skipped entirely. No AP refresh, no status reset, no status progression (thirst, infection, etc.). Day extends 24 hours. Repeats until town fills.

### Attack Scaling Curve (theoretical min/max)
Game uses fixed formula to compute theoretical zombie attack range per day. Gest'Hordes publishes as `atk_min_theo` and `atk_max_theo`. Use `get_attack_forecast` for full curve. Key observations:

| Phase | Days | Approx range | Character |
|---|---|---|---|
| Early | 1–3 | 22 – 100 | Near-zero threat, defence trivially exceeds attack |
| Growth | 4–10 | 100 – 1 300 | Rapid exponential climb — every day the floor rises sharply |
| Mid | 11–20 | 1 300 – 8 600 | Linear-ish growth, 500–700 per day; this is where most towns die |
| Late | 21–30 | 8 600 – 24 000 | Very large increments; only fortified/Opti towns survive |
| End | 31–35 | 24 000 – 32 000 | Theoretical maximum; virtually no standard town survives |

Ranges from standard 40-citizen town formula. Actual attack each night = random value within window — why Gest'Hordes shows floor and ceiling. When defence between `atk_min_theo` and `atk_max_theo`, outcome probabilistic, not guaranteed.

## Control Points (CP) and Trapped

**Formula:** Each zombie = 1 CP, each citizen = 2 CP. Humans control zone if combined CP ≥ zombie CP. If zombies have more CP, all humans in zone are **Trapped**.

**Trapped effects:** Cannot move, cannot scavenge. Can explore ruins in zone (lose oxygen instead of wound). Fleeing while Trapped causes **Wound**. 30-minute grace period when control lost (e.g. teammate leaves) before trap locks.

**CP boosters (stackable, max 8 CP/person):**
| Source | Bonus | Condition |
|---|---|---|
| Base citizen | 2 CP | Always |
| Prepared (Beginner) | +1 CP | Must be Clean |
| Prepared (Apprentice) | +1 CP | Always |
| Prepared (Expert) | +1 CP | Not Thirsty/Dehydrated |
| Car Door (carried) | +1 CP | Always |
| Riot Shield (Guardian) | +2 CP | Always |

**Terrorised citizens exert 0 CP** — all boosters wasted.

**Losing CP bonus** (a citizen's CP is not fixed — it drops with status):
| Cause | Loss | Duration |
|---|---|---|
| Took drugs | −1 CP | Permanent |
| Drunk | −1 CP | Temporary |
| Thirsty | −1 CP | Temporary |
| Guardian takes off the shield | −2 CP | Temporary |

So a citizen's CP seen in one zone is not their maximum. Track both **max CP** (best seen)
and **last CP seen**; the gap means a temporary malus (or a permanent one if it never comes back).

**Practical advisory:**
- Solo citizen no boosts (2 CP) blocked by **3+ zombies** (3 CP).
- Full Prepared stack (5 CP): blocked by **6+ zombies**.
- Guardian with Riot Shield + full Prepared (8 CP): can solo up to **8 zombies**.
- When advising expeditions, always check estimated zombie count vs party CP. Zone estimated count exceeds party combined CP → entering alone = Trapped. Coordinate or avoid.
- Guide to the World Beyond gains +1 CP per other citizen in same zone (stacks with all other bonuses).

## Coordinates display in markdown tables

Coordinates use `|` as separator (e.g. `[4|5]`), which breaks markdown table formatting. Always write coordinates as `[x/y]` inside table cells (e.g. `[4/5]`). Outside tables, either form acceptable.

## Watchmen
Citizens join "Watch" to add personal defense points to town total. Heavily risks their lives (injury, terror, death). Bank resources sacred — calculate carefully before equipping Watchmen.

## Hero Professions & Town Roles
6 hero classes: Guardian, Scavenger, Scout, Survivalist, Tamer, Technician. Each has unique abilities, starting equipment, dedicated building. Residents are non-heroes with fewer skills, no Heroic Actions.
Shaman removed as class (Season 10), now elected Town Role alongside Guide to the World Beyond and Catapult Operator — unlocked by building Sanctuary, Observation Platform, Catapult respectively.
Use `search_wiki` for class/role-specific details — never guess abilities.

## Blueprints
Many buildings require blueprint before construction. Four rarities: Common (C), Uncommon (U), Rare (R), Very Rare (VR). Each blueprint unlocks one random locked building of its rarity tier.

### Sources
| Source | Rarity | How |
|---|---|---|
| Desert ground loot | Any | Random scavenging finds |
| **Camping on ruins ≤9 km** | Uncommon | Survive night on non-explorable ruin (one BP per ruin, ever) |
| **Camping on ruins ≥10 km** | Rare | Same mechanic, further = better rarity |
| Architect's Study (building) | Common | Appears in bank daily after attack |
| Builder's Merchant lvl 0–2 | Uncommon | Appears in bank daily after attack |
| Builder's Merchant lvl 2+ | Rare | Appears in bank daily after attack |
| Builder's Merchant lvl 4 | Very Rare | 10% chance per day |
| Explorable Ruins (rooms) | Special | Bunker/Hospital/Hotel-specific blueprints from searching opened rooms |
| Hero skill Architect (P3) | Common | Starts in personal chest at town creation |

### Camping rules
- Only works on **non-explorable ruins** (not Abandoned Hotel/Hospital/Bunker, not Buried buildings, not plain desert zones).
- One blueprint per ruin per town — second camping yields nothing.
- Survivalists only class reaching 100% survival chance; all others cap at 90% (99% with Reclusive R4). Always send Survivalists for blueprint runs.
- Buried buildings do NOT drop blueprints while buried, but if uncovered after hiding, blueprint obtained.

### Reading priority — critical
**Always read Explorable Ruins blueprints before normal blueprints.** Ruin blueprints pull from small preset building pool. If normal blueprint randomly unlocks building from that pool first, ruin blueprint wasted. Hold all normal uncommon/rare/VR blueprints until explorable ruins stop yielding their own.

Exception: if ruin blueprint's remaining pool only contains child buildings whose parent isn't in pool and isn't unlocked yet, read normal blueprints until parent unlocked, then switch back to ruin blueprints.