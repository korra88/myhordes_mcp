# Core Game Mechanics

## Action Points (AP)
- Players start with 6 AP per day. AP is used for moving, building, and working.
- **Wounded** reduces max AP from 6 to 5 (all AP sources restore 1 less). Must be healed with a Bandage before midnight or the citizen becomes Infected.
- **Exhausted** (0 AP): disables melee weapons, Scout/Scavenger Sense, and desert entry.

## Free Actions (0 AP)
Eating, drinking, drugs, collecting water, searching zones, using weapons in desert, combining items, cooking, stealing, picking up/dropping items, taking from bank, estimating attacks.

## Other AP Sources
Dice (chance 1 AP), Cards (chance 1 AP), Makeshift Guitar (1 AP to all in town, 2 if Drunk/Drugged), Siesta Time (chance 2 AP), EMS System (up to 5 AP but causes Wound), Bloody Hot Coffee (up to 4 AP).

## Eating & Drinking
- A citizen can eat only ONCE a day ("Fed" status). Basic food restores AP to max (6). Premium food restores AP to max + 1 (7 AP, or 6 if Wounded).
- The first water ration restores AP to max (6) and gives "Refreshed" status. Further drinks don't restore AP but can improve thirst.
- Thirst chain overnight if not Refreshed: Normal → Thirsty → Dehydrated! → Death.
- A Dehydrated citizen dies at midnight regardless of Refreshed status.
- Drinking when Dehydrated does NOT restore AP — it only improves status to Thirsty.

## Alcohol
Restores AP to max (6), gives "Drunk" status. Drunk citizens suffer -20% scavenging penalty and scrambled forum/note messages. The next day they become "Hungover" and cannot drink alcohol. Exception: Ergot Homebrew can be consumed while Drunk or Hungover.

## Drugs
Taking a drug gives "Drugged" status and restores AP. Taking a second drug while already Drugged gives "Hooked!" status — permanent and irreversible. A Hooked citizen MUST take a drug every day or die from withdrawal overnight.

## Midnight Attack
Every night at 23:59 CET, a horde of zombies attacks. The town's total defense must exceed the zombie attack estimation or citizens will be slaughtered. The Town Gates MUST be closed before the attack.

**Unfilled towns:** If the town doesn't have 40 citizens by midnight, the attack is skipped entirely. No AP refresh, no status reset, no status progression (thirst, infection, etc.). The day effectively extends by 24 hours. This repeats until the town fills.

## Watchmen
Citizens can join the "Watch" to add their personal defense points to the town's total. This heavily risks their lives (injury, terror, or death). Bank resources are sacred — calculate carefully before equipping Watchmen.

## Hero Professions & Town Roles
6 hero classes: Guardian, Scavenger, Scout, Survivalist, Tamer, Technician. Each has unique abilities, starting equipment, and a dedicated building. Residents are non-heroes with fewer skills and no Heroic Actions.
Shaman was removed as a class (Season 10) and is now an elected Town Role alongside Guide to the World Beyond and Catapult Operator — unlocked by building Sanctuary, Observation Platform, and Catapult respectively.
Use `search_knowledge_base` for class-specific or role-specific details — never guess abilities.

## Blueprints
Many buildings require a blueprint to unlock before they can be constructed. Blueprints come in four rarities: Common (C), Uncommon (U), Rare (R), Very Rare (VR). Each blueprint unlocks one random locked building of its rarity tier.

### Sources
| Source | Rarity | How |
|---|---|---|
| Desert ground loot | Any | Random scavenging finds |
| **Camping on ruins ≤9 km** | Uncommon | Survive the night on a non-explorable ruin (one BP per ruin, ever) |
| **Camping on ruins ≥10 km** | Rare | Same mechanic, further = better rarity |
| Architect's Study (building) | Common | Appears in bank daily after the attack |
| Builder's Merchant lvl 0–2 | Uncommon | Appears in bank daily after the attack |
| Builder's Merchant lvl 2+ | Rare | Appears in bank daily after the attack |
| Builder's Merchant lvl 4 | Very Rare | 10% chance per day |
| Explorable Ruins (rooms) | Special | Bunker/Hospital/Hotel-specific blueprints from searching opened rooms |
| Hero skill Architect (P3) | Common | Starts in personal chest at town creation |

### Camping rules
- Only works on **non-explorable ruins** (not Abandoned Hotel/Hospital/Bunker, not Buried buildings, not plain desert zones).
- One blueprint per ruin per town — second camping yields nothing.
- Survivalists are the only class that can reach 100% survival chance; everyone else caps at 90% (99% with Reclusive R4). Always send Survivalists for blueprint runs.
- Buried buildings do NOT drop blueprints while buried, but if uncovered after hiding, the blueprint is obtained.

### Reading priority — critical
**Always read Explorable Ruins blueprints before normal blueprints.** Ruin blueprints pull from a small preset pool of buildings. If a normal blueprint randomly unlocks a building from that pool first, the ruin blueprint is wasted. Hold all normal uncommon/rare/VR blueprints until the explorable ruins stop yielding their own.

Exception: if a ruin blueprint's remaining pool only contains child buildings whose parent isn't in the pool and isn't unlocked yet, read normal blueprints until the parent is unlocked, then switch back to ruin blueprints.
