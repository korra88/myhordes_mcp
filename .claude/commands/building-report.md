Produce the town's day-by-day construction throughput report.

## Step 1 — Fetch data in parallel

Call all of these simultaneously:
- `get_buildings` — construction history grouped by day (paid builds + free vote upgrades)
- `get_attack_forecast` — actual attack values per day, defense per day, deaths per day
- `get_attack_distribution` — Gest'Hordes statistical distribution for D+1 estimate
- `get_town_overview(detail='compact')` — current day N and alive citizen count

Also resolve the town folder (slug-match under `towns/`) and read `towns/{folder}/daily-log.md` for the per-day alive counts logged there.

## Step 2 — Reconstruct alive count per day

Use the `Deaths` column from `get_attack_forecast` to walk backwards from today's alive count:
- `alive[N]` = current alive (from get_town_overview)
- `alive[N-1]` = alive[N] + deaths on night N (attack_forecast Deaths column for day N)
- `alive[N-2]` = alive[N-1] + deaths on night N-1
- etc.

Cross-check against the daily-log.md alive counts. Prefer the log values when they exist.

## Step 3 — Parse the construction history

`get_buildings` now returns buildings **grouped by the day they were built** (after the fix to use `dailyConstructions`). For each day:

**Paid builds** = buildings listed under that day (not marked as free vote upgrades).
For each paid build, look up its AP cost from the "Available to build" list in the same tool output (or use the known costs below).

**Free vote upgrades** = entries marked `(free vote)` in the tool output. Exclude these from AP totals. Collect them to note below the table.

Known AP costs for reference (use tool output values when available):
Butcher 40 · Defensive Wall 25 · Portal Lock 15 · Pump 25 · Watchtower 15 · Architect's Study 50 · Observation platform 30 · Vegetable Plot 60 · Armour Plating 30 · Eden Project 50 · Factory 40 · Plywood 30 · Armour Plating v2 30 · Slip 'n' Slide 35 · Drilling Rig 55 · Grapeboom 40 · Great Pit 70 · Concrete Reinforcement 40 · Armour Plating v3 30 · Divining Rocket 80

## Step 4 — Ask about today's build plan

Before completing the table for the current day, **ask the user**:

> "Do you have a build plan for today (Day N)? If so, list the buildings and I'll include them as 'planned' in the report."

Wait for the response. If the user provides a plan, include those buildings in the Day N row as `*(plan: Building A · Building B · ...)*` with their AP costs added to the total. If no plan is given, show only the builds already confirmed by `get_buildings` for today.

## Step 5 — Build the table

Produce the following table (one row per game day, starting from Day 1 or the first day with construction data):

| Day | New builds (paid) | AP | Budget (18×pop) | % | Zombie attack |
|-----|-------------------|----|-----------------|---|---------------|

Column rules:
- **Day**: game day number
- **New builds (paid)**: list each building with its AP cost in parentheses. For the current day, append the plan if provided (prefixed with `*(plan:)*`). Do not list free upgrades here.
- **AP**: sum of all paid build AP costs for that day (confirmed + planned for today)
- **Budget**: `18 × alive_count` where alive_count is the number of citizens alive at the **start** of that day
- **%**: AP / Budget × 100, rounded to nearest integer
- **Zombie attack**: use actual attack value if known (from attack_forecast), otherwise the Gest'Hordes confirmed estimate for that day. For today: show the confirmed estimate and mark `← tonight`. For D+1: show the Gest'Hordes p25–p75 range with median in parentheses, e.g. `~458–586z (median 513) — GH stat`.

After the table, add a **Notes** section:
- List all free vote upgrades, grouped by day: `Free upgrades — Day N: BuildingName Lv.X→Y · ...`
- Flag if today's defense is below the attack floor (deficit in AP-equivalent terms)
- Note the D+1 sample size from `get_attack_distribution` for reliability context
