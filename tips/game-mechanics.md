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
- The first water ration restores AP to max (6), gives "Refreshed" status, and resets the thirst counter. Further drinks don't restore AP but can improve thirst status.
- A Dehydrated citizen dies at midnight regardless of Refreshed status.
- Drinking when Dehydrated does NOT restore AP — it only improves status to Thirsty.

### Thirst counter (in-desert movement)
- Moving through zones increments a thirst counter. After walking **11 zones** since the last water ration, you become **Thirsty**.
- **Thirsty and Refreshed are independent statuses** — you can be both simultaneously. Drinking a water ration gives Refreshed and resets the counter; it does not clear an existing Thirsty status if already acquired.
- **Overnight progression depends on Refreshed, not Thirsty:**
  - Normal, not Refreshed → Thirsty at midnight
  - Thirsty, not Refreshed → Dehydrated at midnight
  - Thirsty + Refreshed → stays Thirsty next morning (no degradation, but not reset to Normal either)
  - Dehydrated → Death at midnight regardless of Refreshed status
- **Expedition goal:** return **Refreshed** — Thirsty + Refreshed on arrival is safe overnight. Returning without Refreshed risks overnight degradation.

## Alcohol
Restores AP to max (6), gives "Drunk" status. Drunk citizens suffer -20% scavenging penalty and scrambled forum/note messages. The next day they become "Hungover" and cannot drink alcohol. Exception: Ergot Homebrew can be consumed while Drunk or Hungover.

## Drugs
Taking a drug gives "Drugged" status and restores AP. Taking a second drug while already Drugged gives "Hooked!" status — permanent and irreversible. A Hooked citizen MUST take a drug every day or die from withdrawal overnight.

## Midnight Attack
Every night at 23:59 CET, a horde of zombies attacks. The town's total defense must exceed the zombie attack estimation or citizens will be slaughtered. The Town Gates MUST be closed before the attack.

**Unfilled towns:** If the town doesn't have 40 citizens by midnight, the attack is skipped entirely. No AP refresh, no status reset, no status progression (thirst, infection, etc.). The day effectively extends by 24 hours. This repeats until the town fills.

### Attack Scaling Curve (theoretical min/max)
The game uses a fixed formula to compute the theoretical zombie attack range for each day. Gest'Hordes publishes these as `atk_min_theo` and `atk_max_theo`. Use `get_attack_forecast` to retrieve the full curve. Key observations:

| Phase | Days | Approx range | Character |
|---|---|---|---|
| Early | 1–3 | 22 – 100 | Near-zero threat, defence trivially exceeds attack |
| Growth | 4–10 | 100 – 1 300 | Rapid exponential climb — every day the floor rises sharply |
| Mid | 11–20 | 1 300 – 8 600 | Linear-ish growth, 500–700 per day; this is where most towns die |
| Late | 21–30 | 8 600 – 24 000 | Very large increments; only fortified/Opti towns survive |
| End | 31–35 | 24 000 – 32 000 | Theoretical maximum; virtually no standard town survives |

These ranges come from the standard 40-citizen town formula. The actual attack drawn each night is a random value from within this window, which is why Gest'Hordes shows both a floor and a ceiling. When defence is between `atk_min_theo` and `atk_max_theo`, the town's fate is probabilistic — not guaranteed.

## Control Points (CP) and Trapped

**Formula:** Each zombie = 1 CP, each citizen = 2 CP. Humans control the zone if their combined CP ≥ zombie CP. If zombies have more CP, all humans in the zone are **Trapped**.

**Trapped effects:** Cannot move, cannot scavenge. Can still explore ruins in the zone (but lose oxygen instead of getting wounded). Fleeing while Trapped causes a **Wound**. A 30-minute grace period applies when control is lost (e.g. a teammate leaves) before the trap locks in.

**CP boosters (stackable, max 8 CP/person):**
| Source | Bonus | Condition |
|---|---|---|
| Base citizen | 2 CP | Always |
| Prepared (Beginner) | +1 CP | Must be Clean |
| Prepared (Apprentice) | +1 CP | Always |
| Prepared (Expert) | +1 CP | Not Thirsty/Dehydrated |
| Car Door (carried) | +1 CP | Always |
| Riot Shield (Guardian) | +2 CP | Always |

**Terrorised citizens exert 0 CP** — all boosters are wasted.

**Practical advisory:**
- A solo citizen with no boosts (2 CP) is blocked by **3+ zombies** (3 CP).
- With full Prepared stack (5 CP), a solo citizen is blocked by **6+ zombies**.
- A Guardian with Riot Shield + full Prepared (8 CP) can solo up to **8 zombies**.
- When advising on expeditions, always check the estimated zombie count against the party's available CP. If a zone's estimated zombie count exceeds the party's combined CP, entering alone means getting Trapped — coordinate with others or avoid the zone.
- The Guide to the World Beyond gains +1 CP per other citizen in the same zone (stacks with all other bonuses).

## Coordinates display in markdown tables

Coordinates use `|` as separator (e.g. `[4|5]`), which breaks markdown table formatting. Always write coordinates as `[x/y]` when inside a table cell (e.g. `[4/5]`). Outside tables (plain text, bullet points), either form is acceptable.

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
