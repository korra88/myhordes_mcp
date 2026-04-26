Recommend today's construction queue based on live town state, bank inventory, and phase-appropriate building priorities.

## Step 1 — Load context

Read in parallel:
- `tips/buildings-cheatsheet.md` — efficiency reference, flags, resource abbreviations
- `towns/{folder}/_baseline.md` — current resource snapshot

Resolve town folder: list `towns/` subdirs, match current town from `.env` or `get_town_overview`.

## Step 2 — Fetch live state

Call in parallel:
- `get_defense_status` → total defense, tonight's estimate, item multiplier
- `get_bank_inventory(detail='summary')` → water count, defense items, key resources
- `get_buildings(mode='available', include_resources=True)` → unbuilt buildings with AP/def/resources

## Step 3 — Load phase knowledge

Determine current day N from `get_defense_status`. Load phase file(s) via `search_knowledge(section="buildings")`:
- Day 1–4: query `"Day 1–5"`
- Day 5–8: query `"Day 6–10"` (Day 5–6: also query `"Day 1–5"`)
- Day 9–14: query `"Day 9–15"` (Day 9–11: also query `"Day 6–10"`)
- Day 15+: query `"Day 15+"` (Day 15–16: also query `"Day 9–15"`)

Call both queries in parallel when on a boundary day.

## Step 4 — Assess situation

- **Defense buffer:** total defense − tonight's max estimate. Negative = urgent.
- **Water ratio:** water rations ÷ alive citizens. < 2.0 = critical — water builds jump above efficiency-sort.
- **AP budget:** 20% of alive citizens × ~18 AP. Flag if plan exceeds 240 AP.
- **Multiplier gap:** Defensive Focus not built + ≥40 defense items in bank (boards, sheet metal, UCBs, old doors) = highest-leverage build regardless of phase.

## Step 5 — Build priority queue

**CRITICAL — before building the queue, extract your buildable set first:**

From the `get_buildings` output, collect buildings from exactly these two sections:
- `Unlocked — no blueprint needed`
- `Unlocked — blueprint found`

This is your **buildable set**. Only recommend buildings from this set. Never recommend anything outside it, regardless of water urgency or defense need.

**Prerequisite exception:** buildings in `Locked — prerequisite not built` MAY be added to the queue only if you also add their unlocked prerequisite earlier in the queue. Chain upward until you reach a building in the buildable set. The chained buildings must themselves be in the buildable set.

Sort by: survival necessity → def÷AP efficiency → permanence (permanent > temporary).

- **Defensive Focus** jumps to #1 if multiplier gap condition met and resources available. If it's Locked, include its prerequisite first in the queue.
- **Water producers** (Drilling Rig, No Holes Barred, Eden Project, Divining Rocket, Mechanical Pump, Divining Rods) jump above efficiency-sort if water ratio < 2.0 AND resources are available to build them AND building appears in an Unlocked or prerequisite-locked section. Skip any water producer in "Locked — blueprint not found". If prerequisite-locked, include prerequisite first. Hydraulic Network and water-unlock buildings (Decon Shower, Sluice) do NOT trigger this — they don't produce water directly. Water Purifier/Filter only if 10+ Jerrycans in bank.
- Flag any build with missing or borderline resources.
- Skip temporaries unless defense buffer is negative or AP budget has slack after permanents.
- Soft cap 240 AP; hard cut at 300 AP — drop lowest-priority items and note.

## Step 6 — Output

```
## Build Plan — Day N

Situation: {defense} def vs {max_estimate}z (+{buffer}) · {water}/{alive} WR · ×{mult} multiplier

Queue ({total_ap} AP, +{total_def} def):
1. Building name — AP / +def — resources — ✓ ok / ⚠ short: X missing
2. …

Water: safe / marginal / urgent — [one-line recommendation if not safe]
Why: [2 sentences on key priority calls and tradeoffs]
```
