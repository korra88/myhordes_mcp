# Strategy Quirks & Community Meta

Non-obvious strategies and game quirks learned from experience, not documented on the wiki.

## Blueprints

### Read explorable ruin blueprints before normal construction blueprints
Both ruin blueprints (Bunker/Hospital/Hotel variants) and normal blueprints unlock construction projects. The difference:
- **Normal blueprints** draw from the entire building pool — they will always find something unlockable.
- **Ruin blueprints** only draw from a **preset, limited pool** of buildings specific to that ruin type.

When a blueprint is read, it unlocks the first project in its pool that hasn't been unlocked yet. If a normal blueprint gets there first and unlocks a building that was in the ruin blueprint's preset pool, the ruin blueprint has one fewer option and may eventually be **wasted** (nothing left in its pool to unlock).

They are distinct items — ruin blueprints are named `Bunker/Hospital/Hotel Construction Blueprint (rarity)`, normal blueprints are named `Construction Blueprint (rarity)`. Easy to tell apart in the bank.

**Rule:** Hold all normal blueprints, read ruin blueprints first to exhaust their preset pool, then read normal blueprints for whatever remains.

**Exception:** If the ruin blueprint's remaining targets are child buildings whose parent is not in the preset pool, read normal blueprints first to unlock the parent, then resume ruin blueprints.

## General

### The Flag (Season 18 mechanic)
When a citizen waves a Flag in town, **2.5% of zombies that exceed the town's defense** attack that citizen directly. With 40 citizens all waving flags, 100% of the excess is redistributed. At ~49 personal defense per citizen, this offsets ~1,960 zombies. This allows a town to deliberately run below the attack estimate without wiping — the deficit is covered personally. A Fata Morgana snapshot showing defense < attack estimate is NOT necessarily a crisis if a Flag strategy is active.

### All or Nothing — the item-to-defense converter
The "All or Nothing" building provides **defense equal to the number of consumable items in the bank when built**. In Opti towns, this is the primary source of "Other" defense. A large stockpile of Vials of Poison/Toxin/Plastic Bag & Semtex in the bank is fuel for All or Nothing — not items being deployed manually. Never advise "use these poisons for defense" if the town is running All or Nothing.

### Mass shunning to generate items
Using Revolution + Altar together, a town can shun most of its citizens twice and then remove the shun status. Each shun gives the victim 3 items. 35 citizens × 2 shuns × 3 items = 210 items — all deposited into the bank as All or Nothing fuel. This is a planned mechanic in coordinated towns, not a punishment event.

### The Ghoul sacrifice
When a Survivalist exhausts all camping days, they cannot survive outside overnight without death risk. In Opti towns, this player is **deliberately fed to a Ghoul** to produce a Meaty Bone → Bone → Engine → Faucets chain. Faucets allow free water weapon refills. The Dump (when upgraded) makes water weapons give 6 defense each, creating a temporary defense arsenal from the item stockpile. If you see a planned Survivalist death mid-game in an organized town, assume this is the scheduled Ghoul sacrifice.

### The two defense multipliers are different things
- **Defensive Adjustment**: multiplies the defense from defense items placed in bank
- **Defensive Focus**: increases total town defense by 10–15% when fully upgraded
Both are unlocked/upgraded by nightly vote. They are NOT the same multiplier. Always check `get_defense_status` to see each independently before advising on defense planning.

### Tamer class dominance in item-heavy towns
Tamers' pets can **send found items directly back to town** from the desert, bypassing carry limits. In towns running All or Nothing or heavy animal-defense strategies, a Tamer-majority roster is deliberate. The Tamer Center building also generates animals for defense or food. If you see 20+ Tamers in a roster, the town is built around this pipeline.

### Opti town death discipline
In a coordinated Opti town, **a single unplanned death fails the ranking**. Citizens are kept alive until mathematically useful, then exit via mass expedition rather than dying inside walls. At the end, surviving citizens hunt and purify the souls of the dead for bonus season points. If someone dies unexpectedly in an Opti town mid-run, flag it immediately — it has ranking consequences, not just survival consequences.

