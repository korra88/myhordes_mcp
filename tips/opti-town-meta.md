---
topic: Opti-town meta strategy
description: How coordinated "Opti" towns work — the pillars, execution, and mechanics behind season-winning runs
---

## What is an Opti town

An **Opti town** (Optimized town) is a coordinated run organized by 3–4 experienced players who act as directors. Every other citizen receives precise daily instructions and executes them without deviation. The goal is not merely survival but maximizing the **final score/ranking** — which means zero unplanned deaths, optimized soul purification at the end, and perfect execution of every mechanic.

A single unaccounted death during the run **fails the ranking**, because dead citizens leave the team's AP pool and lose ranking points. Every citizen is kept alive for as long as mathematically optimal.

---

## The five pillars of an Opti town

### 1. Tamer-heavy roster
Tamers are the premier class for item accumulation:
- Their pets can **send items directly from the desert back to town** — more item-per-AP than any other class
- The **Tamer Center** building produces animals (Guard Dogs, Mangy Dachshunds) used as defense items or food
- In an Opti town, the majority of the roster is Tamers specifically for this pipeline

### 2. The Flag mechanic (Season 18 specific)
The **Flag** item: each citizen waving it absorbs 2.5% of zombies exceeding town defense.
- 40 citizens waving = 100% of excess zombies redistributed personally
- ~49 personal defense × 40 citizens = ~1,960 zombie offset for free
- This allows the town to target a **lower total defense floor**, freeing AP for construction and scavenging
- Early days showing "defense below estimate" in Fata Morgana are not near-misses — they are **calculated and covered by Flag**

### 3. The shunning / All or Nothing nuke
AoN is a **one-shot last-stand move** — it wipes the entire bank when built. The preparation:

1. Use **Revolution** + **Altar** to shun most of the town twice, then remove shun status
2. Each shun gives the victim 3 items — with 35+ citizens shunned twice, this generates 200+ items
3. That item stockpile accumulates in the bank as AoN fuel (Vials of Poison, Toxin, etc.)

**Before AoN night — the Dump vault strategy:**
- Move defense objects (DOs) into the **Dump** to protect them from the bank wipe
- The Dump gives 2 DP per item stored as a building bonus — this keeps some defense active while items are vaulted
- The bank has a **15-minute cooldown / 5-item limit** on withdrawals, making it impossible to rescue hundreds of DOs conventionally — the Dump bypasses this (costs AP to recover, no withdrawal limit)
- Stash food, drugs, and other needed items outside town walls or in the Dump

**AoN night:**
- Build All or Nothing — defense = number of consumable items remaining in bank
- Bank is wiped. Massive one-night defense spike from hundreds of accumulated junk items.

**After AoN:**
- Recover DOs from the Dump (costs AP, no item limit) — they return to bank where Defensive Focus multiplies them at full value (3 DP each at max)
- Recovering loses the Dump's 2 DP bonus but gains the bank's 3 DP — net positive, no defense compromise, just AP-intensive
- This is typically the last or second-to-last defensible night before the mass exodus

Never interpret a large poison/toxin stockpile as a "deploy poison" strategy — it's **AoN fuel being accumulated**. And never suggest building AoN early — it's a one-shot that must be timed to the final stand.

### 4. The Ghoul sacrifice and Dump endgame
- Late game (typically when the Survivalist exhausts all camping days), a citizen is **intentionally fed to a Ghoul**
- The Ghoul kill drops a **Meaty Bone** → craft into **Bone** → craft into **Engine** → build **Faucets**
- Faucets enable free water weapon refills
- The **Dump** building (upgraded) makes water weapons give **6 defense each**
- The accumulated item stockpile becomes a "temporary defense arsenal" for the final defense push
This is a scheduled event, not a failure. If you see a Survivalist die mid-game in an Opti town, it was intentional.

### 5. Reclusive R4 — the go-to skill build
Every citizen in an Opti town runs **Reclusive at Master level (R4)**:
- **Pro Camper R2** (from Reclusive Apprentice): 8 protected camping nights with gentle penalty curve (-10% → -130% cumulative by night 8)
- **Pro Camper R4** (from Reclusive Master): survival cap raised to 99% (vs 90% default)
- Night 9 hits **-480% penalty** — an unsurvivable cliff
- This means the town's exodus timing is dictated by camping math: abandon town such that protected nights carry citizens as far as possible, knowing night 9+ is a coin flip with near-certain death
- The mass death waves in endgame (e.g. 8 dead one night, 24 the next) are not failures — they're the camping cliff hitting everyone simultaneously

### 6. The mass exodus endgame
When the town becomes indefensible, citizens exit together:
- **No one dies inside the walls** — dying in town wastes the citizen's contribution
- Citizens in the desert earn **soul points**: formula is `days × (days + 1) / 2` (triangular number)
  - Day 40 = 820 SP, Day 45 = 1035 SP, Day 46 = 1081 SP — every extra day matters more than the last
- The final days involve **soul purification**: surviving citizens collect souls of the dead and purify them for bonus points to the town
- The last survivors spread out to maximize personal desert survival scores

---

## The two defense multipliers

Never confuse these — they do opposite things to what their names might suggest:

- **Defensive Focus** (Foundations building, no blueprint): Multiplies the DP value of **defensive objects** in the bank. Base 1.5×, upgrades via vote to 2.0× → 2.5× → 3.0×. This is the item multiplier.
- **Defensive Adjustment** (Workshop building, uncommon blueprint): Multiplies **total town defense** by a percentage. Base +10%, upgrades via vote to +11% → +12% → +13% (S18 had +11% → +13% → +15%). Applies to everything including temporary defense and watchmen.

Both upgrade through nightly citizen votes, 3 levels each. In an Opti town, both are rushed to max ASAP — Defensive Focus especially, since tripling every defense item in bank is massive.

---

## Coordination tools

Opti towns are coordinated through:
- **Discord** — real-time communication between directors and citizens
- **Gest'Hordes** — external tool that collects stats (desert cell positions, bank status, etc.) and provides a suite for organizing:
  - **Jumps**: coordinated entries into town
  - **Expeditions**: desert routes with per-zone instructions (items to take/drop, actions to perform, supply drops for citizens in need)
- **Fata Morgana** — spy page with defense, buildings, scout data (what the MCP reads from). Less powerful than Gest'Hordes but no auth needed.

Directors (typically 3-4 experienced players) issue daily orders through these channels. Every other citizen executes without deviation.

---

## The Dump as a strategic vault

The Dump serves dual purpose beyond its building defense bonus:
- Items stored in the Dump give **2 DP per item** as a building bonus
- Items can be **recovered by spending AP** — no withdrawal cooldown or item limit (unlike the bank's 15-min / 5-item restriction)
- Before All or Nothing, DOs are moved to the Dump to survive the bank wipe; food, drugs, and essentials are stashed outside town or in the Dump
- After AoN fires, DOs are recovered from the Dump back to the bank at full Defensive Focus value (3 DP each at max)
- The Dump is the only way to protect hundreds of items from AoN's bank wipe in a timely manner

---

## Season 19 nerfs and meta shifts

Key changes from S18 → S19:
- **Flag removed** — devs considered it "trivialized survival." No replacement mechanic added. There was significant community pushback when devs attempted a mid-S18 removal, as it would have invalidated rankings.
- **Defensive Adjustment nerfed** — max bonus now +13% (was +15% in S18) when fully upgraded
- **Reclusive skill nerfed** — no longer includes Lucky Find, only camping bonus (Pro Camper)
- **Lucky Find nerfed** — max level no longer includes Worn-out Sports Shoes in the selection pool (item that grants 1 EP every AP refresh — was a massive free-movement boost for desert expeditions)
- **Current S19 meta (evolving)**: Dump + Watchmen for attack spikes. The community is still discovering this season's tricks.

---

## The Zombie Zoo (advanced tactic)

The Zombie Zoo is an advanced coordinated tactic that confines all map zombies to a designated area, keeping the rest of the desert clean for safe scavenging. It requires dedicated "zookeeper" players and careful coordination — a misplay triggers a catastrophic global respawn.

### Critical concept: map zombies ≠ midnight attack

These are **two completely independent systems**:
- **Midnight attack**: a predetermined horde number set by the game's attack schedule. Grows night by night in a pattern with ~4-day spikes. Killing map zombies does NOT reduce the midnight horde. The attack estimate tools track this number.
- **Map zombies (World Beyond)**: spawn and spread by their own rules each night. These are what the zoo manages. Scout data shows these.

Never conflate the two. A town with 25,000 attack estimate and 50 visible map zombies is normal — those are separate populations.

### Map zombie spawn rules (nightly, after midnight attack)

- **Empty zone, no infected neighbors**: stays empty. Clean breeds clean.
- **Empty zone, some infected neighbors**: spawns 0–4 zombies. More infected adjacent zones = higher spawn count.
- **Already infected zone**: spawns 1–2 additional (1 if fully surrounded by infected zones).

Zombies spread like a contagion. An infected zone infects adjacent empty zones. Left unchecked, the entire map becomes overrun.

### Global Respawn — the trap

If total map zombie population drops below **25 × day number** (formula as of S18), the game triggers a **global respawn**: zombies randomly appear across the entire map until the threshold is reached, plus the day-1 amount added on top.

| Day | Threshold |
|-----|-----------|
| 10 | 250 |
| 25 | 625 |
| 35 | 875 |

**This is the #1 danger of the zoo tactic.** If zookeepers or citizens accidentally kill too many zombies and the total drops below threshold, zombies explode randomly across every zone. All clean corridors are ruined. The town's scavenging efficiency collapses.

### How the zoo works

1. **Designate a zoo area** — typically a corner of the map, away from scavenging routes. A corner is ideal because the map edge acts as a natural wall on two sides, reducing the boundary to patrol. In S18 Interventionist Asylum, the zoo was in the west-southwest quadrant (roughly x=-8 to x=-11, y=-4 to y=-11).

2. **Never kill zombies inside the zoo** — infected zones keep spawning 1–2 more nightly, and spread to adjacent empty zones. The zoo self-sustains and grows, acting as a zombie reservoir.

3. **Clean zones stay clean** — empty zone + all-empty neighbors = no spawning. As long as the infection boundary doesn't advance, everything outside the zoo stays clear.

4. **Zookeepers patrol the boundary** — dedicated players (typically Tamers or Scouts with good AP efficiency) walk the zoo perimeter daily and **kill any zombies that leak outward** before they can infect clean zones. In S18 this was 2–3 players running the x=-7 column and y=-3 row.

5. **Zombie Despair helps cleanup** — for roughly every 2 zombies killed in a zone during the day, 1 more dies from despair overnight. Zookeepers don't need to kill every leaker — kill 2/3 of zombies in a boundary zone and despair finishes the rest by morning.

6. **Keep total above global respawn threshold** — the zoo's population sustains the threshold naturally. The danger is over-killing at the boundary. Zookeepers must kill only what leaks, never push into the zoo itself.

### Why it requires heavy coordination

- **Zookeeper assignment**: 2–3 dedicated players must patrol the boundary daily, consuming AP that could go to scavenging or construction. This only pays off in large, long-lived towns.
- **All citizens must avoid the zoo**: anyone entering the zoo area and killing zombies risks triggering global respawn. Every citizen needs to know the zoo boundaries.
- **Threshold monitoring**: someone must track approximate total map zombie count vs the 25×day threshold to ensure the zoo isn't being depleted.
- **Area sizing**: too small a zoo risks over-killing → global respawn. Too large wastes scavengable territory. Must be adjusted as the threshold rises.
- **Communication**: zookeeper reports ("boundary clean", "3 leakers killed at [-7|-5]") need to flow to directors daily.

This is **not a casual tactic**. It's an Opti-tier coordination requirement. In a loosely organized town, the risk of someone wandering into the zoo and triggering global respawn outweighs the benefit.

### Scout data patterns that indicate a zoo

- **Large unscouted quadrant** with static "dangerous" estimates that never change day-to-day — that's the zoo interior, deliberately left alone.
- **Inner zones (within ~6 km) almost always clean** — zero zombies in scouted operational area.
- **Occasional 1–3 zombies at a consistent boundary line** (e.g., always at x=-7) — that's zookeepers intercepting leakers.
- **Days with 0 zombies spotted** across 150+ scouted zones — zoo is contained, no leakers today.

---

## General heuristics for Opti towns

- Zero deaths before the planned Ghoul sacrifice = the run is on track
- Massive Tamer majority + animal-filled bank = this is an Opti setup
- Large poison/toxin stockpile = fuel for All or Nothing, not a poison deployment strategy
- Flag in bank throughout = flag strategy active, apparent defense deficit is acceptable (S18 only)
- Citizens all exiting simultaneously = planned endgame, town will fall, this is correct
- "All or Nothing" + large item bank = a single building covering hundreds of defense
- One quadrant permanently unscouted + clean inner zones = zombie zoo active
- 2–3 citizens making daily runs along the same map line = zookeepers patrolling the boundary
- Zero map zombies in 150+ scouted zones ≠ "no zombies on map" — they're penned in the zoo
