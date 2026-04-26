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
- `get_buildings(mode='available')` → unbuilt buildings with AP/def

## Step 3 — Load phase knowledge

Determine current day N from `get_defense_status`. Load phase file(s) via `search_knowledge(section="buildings")`:
- Day 1–4: `"basic buildings day 1"`
- Day 5–8: `"intermediate"` (Day 5–6: also load basic)
- Day 9–14: `"defense focus"` (Day 9–11: also load intermediate)
- Day 15+: `"advanced dump"` (Day 15–16: also load defense-focus)

Call both files in parallel when on a boundary day.

## Step 4 — Assess situation

- **Defense buffer:** total defense − tonight's max estimate. Negative = urgent.
- **Water ratio:** water rations ÷ alive citizens. < 2.0 = urgent water build.
- **AP budget:** 20% of alive citizens × ~18 AP. Flag if plan exceeds 240 AP.
- **Multiplier gap:** Defensive Focus not built + ≥40 defense items in bank (boards, sheet metal, UCBs, old doors) = highest-leverage build regardless of phase.

## Step 5 — Build priority queue

Sort by: survival necessity → def÷AP efficiency → permanence (permanent > temporary).

- **Defensive Focus** jumps to #1 if multiplier gap condition met and resources available.
- **Water producers** (Drilling Rig, No Holes Barred, Eden Project, Divining Rocket, Mechanical Pump, Divining Rods) jump above efficiency-sort if water ratio < 1.0 AND resources are available to build them. Hydraulic Network and water-unlock buildings (Decon Shower, Sluice) do NOT trigger this — they don't produce water directly. Water Purifier/Filter only if 10+ Jerrycans in bank.
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
