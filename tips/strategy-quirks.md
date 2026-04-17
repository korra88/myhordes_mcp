# Strategy Quirks & Community Meta

Non-obvious strategies and quirks from experience. Not on wiki.

## Blueprints

### Read explorable ruin blueprints before normal construction blueprints
Both ruin blueprints (Bunker/Hospital/Hotel variants) and normal blueprints unlock construction projects. Difference:
- **Normal blueprints** draw from entire building pool — always find something unlockable.
- **Ruin blueprints** draw from **preset, limited pool** specific to ruin type.

On read, blueprint unlocks first unread project in pool. If normal blueprint unlocks building from ruin blueprint's preset pool first, ruin blueprint loses option — may be **wasted** (pool exhausted).

Distinct items — ruin blueprints named `Bunker/Hospital/Hotel Construction Blueprint (rarity)`, normal named `Construction Blueprint (rarity)`. Easy to tell apart in bank.

**Rule:** Hold all normal blueprints, read ruin blueprints first to exhaust preset pool, then read normal blueprints for remainder.

**Exception:** If ruin blueprint's remaining targets are child buildings whose parent not in preset pool, read normal blueprints first to unlock parent, then resume ruin blueprints.

## General

### The Flag (Season 18 mechanic)
Citizen waving Flag: **2.5% of zombies exceeding town defense** attack that citizen directly. 40 citizens all waving flags = 100% excess redistributed. ~49 personal defense per citizen offsets ~1,960 zombies. Town can run below attack estimate without wiping — deficit covered personally. Fata Morgana showing defense < attack estimate NOT necessarily crisis if Flag strategy active.

### All or Nothing — item-to-defense converter
"All or Nothing" building gives **defense equal to consumable items in bank at build time**. In Opti towns, primary source of "Other" defense. Large stockpile of Vials of Poison/Toxin/Plastic Bag & Semtex = All or Nothing fuel, not manual deployment. Never advise "use these poisons for defense" if town runs All or Nothing.

### Mass shunning to generate items
Revolution + Altar together: town shuns most citizens twice, then removes shun. Each shun gives victim 3 items. 35 citizens × 2 shuns × 3 items = 210 items — all deposited into bank as All or Nothing fuel. Planned mechanic in coordinated towns, not punishment.

### The Ghoul sacrifice
Survivalist exhausting camping days can't survive outside overnight without death risk. In Opti towns, player **deliberately fed to Ghoul** to produce Meaty Bone → Bone → Engine → Faucets chain. Faucets allow free water weapon refills. Dump (upgraded) makes water weapons give 6 defense each — temporary defense arsenal from item stockpile. Planned Survivalist death mid-game in organized town = scheduled Ghoul sacrifice.

### Two defense multipliers are different things
- **Defensive Adjustment**: multiplies defense from defense items in bank
- **Defensive Focus**: increases total town defense 10–15% when fully upgraded
Both unlocked/upgraded by nightly vote. NOT same multiplier. Always check `get_defense_status` to see each independently before advising on defense planning.

### Tamer class dominance in item-heavy towns
Tamer pets can **send found items directly back to town** from desert, bypassing carry limits. Towns running All or Nothing or heavy animal-defense use deliberate Tamer-majority roster. Tamer Center building generates animals for defense or food. 20+ Tamers in roster = town built around this pipeline.

### Opti town death discipline
Coordinated Opti town: **single unplanned death fails ranking**. Citizens kept alive until mathematically useful, then exit via mass expedition — not dying inside walls. Surviving citizens at end hunt and purify souls of dead for bonus season points. Unexpected death mid-run = flag immediately — ranking consequence, not just survival.