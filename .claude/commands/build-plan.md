Recommend today's construction queue based on live town state, bank inventory, and phase-appropriate building priorities.

The numbers come from `get_build_options`: do not recompute ratios, buffers or
resource availability. Your job is the order and the reasoning.

`knowledge/buildings/*.md` holds generic efficiency tables by game phase. Use them
for questions not about the live town ("what is usually built on day 5?"). For the
live town, the tool's numbers win: they reflect the real bank and unlocks.

## Step 1 — Fetch live options

Call `get_build_options()` once. It returns:
- **Situation**: defense vs tonight's estimate with buffer, clean water per citizen
  (⚠ below 2.0), town AP budget and caps, Defensive Focus status and the
  defense-item count behind the multiplier gap.
- **Buildable buildings** grouped as water producers / permanent defense (sorted by
  def/AP) / temporary defense / utility, each with AP, def, ratios and
  `✓ ready` or `⚠ short: item have/need`.
- **Next step**: locked defense/water buildings whose prerequisite is buildable,
  with chain AP and defense.

Each group shows its best 8 (plus Defensive Focus/Adjustment, water filters and the
Garbage Dump always) and names the rest on one `+N more` line. Call again with
`include_all=True` only if one of those named-only buildings belongs in the queue.

Do not call `get_buildings`, `get_bank_inventory` or `get_defense_status` for this.

## Step 2 — Load phase knowledge

Current day N is in the tool header. Load phase guidance via `search_knowledge(section="buildings")`:
- Day 1–5: query `"basic"`
- Day 6–8: query `"intermediate"` (Day 6: also `"basic"`)
- Day 9–14: query `"defense-focus"` (Day 9–10: also `"intermediate"`)
- Day 15+: query `"advanced"` (Day 15: also `"defense-focus"`)

## Step 3 — Order the queue

Only recommend buildings listed by the tool. A "Next step" building may enter the
queue only with its prerequisite placed before it.

Priority:
1. **Multiplier gap** — the Situation line says when Defensive Focus is the
   highest-leverage build. If it needs a prerequisite, queue that first.
2. **Water** — water ratio flagged below 2.0: ready water producers go above
   everything except the multiplier. Water Purifier/Filter only when the tool
   reports 10+ Jerrycans.
3. **Negative buffer** — defense first, best def/AP among `✓ ready`; temporaries
   become acceptable.
4. Otherwise permanent defense by def/AP, then utilities the phase guide calls
   essential. Skip temporaries unless the buffer is negative or AP is left over.

Prefer `✓ ready` builds. A `⚠ short` build goes in only if the missing amount is
small and you say what must be brought back. A ready build that uses ≥50% of a
resource ("uses X/Y") competes with others for that stock: say so when two picks
need the same item.

Keep the total near the construction-share AP from the Situation line; never over
the hard cap. Drop the lowest-priority items and say so.

## Step 4 — Output

```
## Build Plan — Day N

Situation: {defense} def vs {estimate}z ({buffer}) · {water}/citizen · Defensive Focus {status}

Queue ({total_ap} AP, +{total_def} def):
1. Building — AP / +def — ✓ ready | ⚠ short: X have/need
2. …

Water: safe / marginal / urgent — [one line if not safe]
Why: [2 sentences on the key priority calls and trade-offs]
```
