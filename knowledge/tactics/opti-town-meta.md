---
topic: Opti-town meta strategy
description: How coordinated "Opti" towns work — pillars, execution, mechanics behind season-winning runs
---

## What is Opti town

Coordinated run by 3–4 experienced directors. Every citizen gets precise daily instructions, executes without deviation. Goal: maximize final score/ranking — zero unplanned deaths, optimized soul purification.

Single unaccounted death fails ranking — dead citizens drain AP pool, lose ranking points.

---

## Pillars

### 1. Tamer-heavy roster
Pets send items directly from desert to town — best item-per-AP ratio. Tamer Center produces Guard Dogs, Mangy Dachshunds (defense items or food). Opti roster = Tamer majority.

### 2. AoN nuke (All or Nothing)
AoN = one-shot last-stand — wipes entire bank when built. Prep:
1. **Revolution** + **Altar**: shun most of town twice, remove shun. Each shun gives victim 3 items — 35+ citizens shunned twice = 200+ items.
2. Stockpile (Vials of Poison, Toxin, etc.) accumulates in bank as AoN fuel.

**Before AoN night — Dump vault:**
- Move defense objects (DOs) into Dump to survive bank wipe.
- Dump = 2 DP/stored item as building bonus — keeps defense active while vaulted.
- Bank has 15-min cooldown / 5-item withdrawal limit — impossible to rescue hundreds of DOs. Dump bypasses this.
- Stash food, drugs, essentials outside walls or in Dump.

**AoN night:** Build All or Nothing — defense = consumable items in bank. Bank wiped → massive one-night defense spike.

**After AoN:** Recover DOs from Dump (no item limit) → return to bank where Defensive Focus multiplies at full value (3 DP each at max). Net positive, AP-intensive. Typically last or second-to-last defensible night.

Never interpret large poison/toxin stockpile as "deploy poison" — it's AoN fuel. Never suggest building AoN early — one-shot, time to final stand.

### 3. Ghoul sacrifice + Dump endgame
Late game: citizen intentionally fed to Ghoul. Ghoul kill → Meaty Bone → craft Bone → craft Engine → build Faucets. Faucets = free water weapon refills. Dump upgraded = water weapons give 6 defense each.

Scheduled event, not failure. Survivalist dying mid-game in Opti town = intentional.

### 4. Reclusive R4
- **Pro Camper R2**: 8 protected camping nights, -10% → -130% cumulative penalty by night 8.
- **Pro Camper R4**: survival cap 99% (vs 90% default).
- Night 9 = -480% penalty — unsurvivable cliff.
- Exodus timing dictated by camping math. Mass death waves in endgame (8 dead one night, 24 the next) = camping cliff hitting everyone simultaneously, not failures.

### 5. Mass exodus endgame
When town indefensible, citizens exit together:
- No one dies inside walls — dying in town wastes contribution.
- Desert soul points: `days × (days + 1) / 2` (triangular, community formula, not checked in code). Day 40 = 820 SP, Day 45 = 1035 SP — every extra day worth more. Score only: no tool computes it (by choice, 2026-10-16).
- Final days = soul purification: surviving citizens collect dead souls, purify for bonus town points.

---

## Defense multipliers

Never confuse — opposite functions:

- **Defensive Focus** (Foundations, no blueprint): multiplies DP value of defensive objects in bank. Base 1.5×, upgrades via vote: 2.0× → 2.5× → 3.0×. Item multiplier.
- **Defensive Adjustment** (Workshop, uncommon BP): multiplies total town defense by %. Base +10%, upgrades: +11% → +12% → +13%. Applies to everything incl. temp defense + watchmen.

Both upgrade via nightly vote, 3 levels. Rush both to max — Defensive Focus especially; tripling every bank defense item = massive.

---

## Coordination tools

- **Discord** — real-time directors ↔ citizens.
- **Gest'Hordes** — positions, bank, Jumps (coordinated entries), Expeditions (per-zone instructions).
- **Fata Morgana** — town map: defense, buildings, scout data, zone CP (MCP source, via its `/towndata` JSON). No auth, less powerful than Gest'Hordes.

---

## Dump as strategic vault

- 2 DP/item as building bonus.
- No withdrawal cooldown or item limit (unlike bank 15-min / 5-item).
- Before AoN: DOs moved here to survive bank wipe.
- After AoN: DOs recovered to bank at full Defensive Focus value.
- Only way to protect hundreds of items from AoN wipe in time.

---

## Zombie Zoo

Advanced tactic: confines all map zombies to designated area, keeps rest of desert clean. Requires dedicated zookeepers + careful coordination — misplay triggers catastrophic global respawn.

### Map zombies ≠ midnight attack

Two independent systems:
- **Midnight attack**: predetermined horde, grows nightly. Killing map zombies does NOT reduce it.
- **Map zombies (World Beyond)**: spawn/spread by own rules. Zoo manages these. Scout data shows these.

Town with 25,000 attack estimate + 50 visible map zombies = normal.

### Spawn rules (nightly, after attack)

- Empty zone, no infected neighbors → stays empty.
- Empty zone, some infected neighbors → spawns 0–4 zombies (more infected adj. = higher count).
- Already infected zone → spawns 1–2 additional.

### Global Respawn trap

Checked in the game code (`MapMaker::aboveMinNumberOfZombies`, rules.yml): each night, after the attack and before zombies spread, if the **whole map** holds fewer than **25 × day** zombies (15 × day in small towns) → global respawn. The day is the **new** one: the night ending day 8 checks 25 × 9 = 225. The respawn regrows the map from its **day-1 layout** until the threshold is reached, then adds the zombies already there on top: clean corridors fill up again.

| Night ending day | Threshold |
|-----|-----------|
| 9 | 250 |
| 24 | 625 |
| 34 | 875 |

`get_scout_map` prints tonight's threshold against the zombies Fata counts (Fata never sees the whole map: never-visited zones and older counts are listed as such).

Zookeepers or citizens accidentally kill too many → threshold breach → all clean corridors ruined.

### How zoo works

1. Designate corner area — map edge = natural wall on two sides.
2. Never kill inside zoo — infected zones self-sustain, grow, act as reservoir.
3. Empty zones with empty neighbors don't spawn — clean zones stay clean.
4. Zookeepers patrol boundary daily — kill only leakers before they infect clean zones.
5. Zombie Despair: ~2 killed in zone → 1 more dies overnight. Kill 2/3 of boundary leakers, despair finishes rest.
6. Keep total above respawn threshold — zoo sustains naturally. Danger = over-killing at boundary.

Not casual tactic. Opti-tier coordination required.

### Scout patterns indicating zoo

- Large unscouted quadrant with static "dangerous" estimates day-to-day — zoo interior, untouched.
- Inner zones (~6 km) almost always clean.
- 1–3 zombies at consistent boundary line (e.g. always x=-7) — zookeepers intercepting leakers.
- 0 zombies across 150+ scouted zones = zoo contained, no leakers.

---

## Heuristics

- Zero deaths before planned Ghoul sacrifice = run on track.
- Massive Tamer majority + animal-filled bank = Opti setup.
- Large poison/toxin stockpile = AoN fuel, not poison deployment.
- Citizens all exiting simultaneously = planned endgame.
- "All or Nothing" + large item bank = hundreds of defense in one build.
- One quadrant permanently unscouted + clean inner zones = zombie zoo active.
- 2–3 citizens running same map line daily = zookeepers on patrol.
- Zero map zombies in 150+ scouted zones ≠ "no zombies on map" — penned in zoo.
