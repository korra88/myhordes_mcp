Produce the town's day-by-day construction throughput report.

The table comes from `get_construction_history`: do not recompute AP sums,
budgets, alive counts or percentages. Your job is today's plan and the notes.

## Step 1 — Fetch data in parallel

- `get_construction_history()` — per day: paid builds with AP, AP spent, budget
  (18 AP × citizens alive at day start), share %, alive, the night's attack
  (actual, or `~min-max` estimate; `*` = tonight) and deaths. Free vote upgrades
  are listed below the table and excluded from AP.
- `get_attack_distribution()` — Gest'Hordes statistics, for the D+1 range only.

## Step 2 — Ask about today's build plan

Before finishing the current day's row, ask:

> "Do you have a build plan for today (Day N)? If so, list the buildings and I'll include them as 'planned' in the report."

If the user gives a plan, take each building's AP from `get_build_options()`
(do not guess costs), add them to today's row as `*(plan: A · B)*`, and recompute
only that row's AP and %. If no plan, show today as the tool returns it.

## Step 3 — Output

Reproduce the tool's table as a Markdown table:

| Day | New builds (paid) | AP | Budget | % | Zombie attack |
|-----|-------------------|----|--------|---|---------------|

- Today's attack cell: the estimate, marked `← tonight`.
- Add a D+1 line with the Gest'Hordes p25–p75 range and median from
  `get_attack_distribution`, e.g. `~458–586z (median 513) — GH stat`.

Then **Notes**:
- Free vote upgrades by day (copy from the tool).
- Days with unusually low or high share, and any deaths affecting the budget.
- The D+1 sample size from `get_attack_distribution`, for reliability.
- If the tool says alive is unknown (finished town), say the budget column is unavailable.
