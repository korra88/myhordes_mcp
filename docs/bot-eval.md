# Bot evaluation suite

A small, offline, reproducible set of scenarios that scores the Discord advisor's answers, so a change
to `prompts/`, `knowledge/` or a tool output can be measured before and after. Design, decisions and
the full scenario catalogue: [bot-eval-plan.md](bot-eval-plan.md). This page is the practical how-to.

How it works in one paragraph: a scenario names a **fixture** (a frozen Fata `/towndata` snapshot of
one town and day), a clock, a tier (public = small model, trusted = large model), a context (thread or
DM) and one or more user messages. The runner starts the real listener code path (`claude -p`, the
listener's system prompt) but its MCP server is an **offline wrapper** of `main.py` on the fixture: no
Fata request is ever made at eval time. A deterministic grader (checks D1-D13) reads the tool trace and
the answer; an LLM judge (J1-J6) reads what code cannot decide. A hard fail zeroes the scenario.

The real data (fixtures, scenarios, run files) lives in the **private** `towns/` repository under
`towns/_eval/`, because a town snapshot holds real player names. This repository only carries the
harness (`tests/bot_eval/`) and a synthetic example (`tests/bot_eval/scenario.example.json`).

## Prerequisites

- `make install` done (`.venv`), `claude` CLI logged in.
- The Discord listener checked out next to this repo (`../discord_mcp`) with its own venv: the runner
  imports the listener's argv / prompt code instead of copying it. Override the interpreter with
  `DISCORD_PYTHON=...`. The listener's `discord-listener.toml` must allow every tool a scenario expects
  (a missing one is printed as a WARNING; `EXTRA_TOOLS=a,b` adds tools for one run).
- A `towns/_eval/` tree: `fixtures/`, `scenarios/`, `runs/`. For your own town, build one as below.

Nothing here is ever run from cron, a timer or CI. A person starts it, because it calls models (cost)
and because the game forbids automated polling.

## Run it

| Step | Command | Calls a model? |
|---|---|---|
| Freeze a fixture (once per town + day; reuses the local archive first, asks Fata only when missing) | `make bot-eval-freeze ID=7365-d22 ARGS="--town 7365 --day 22 [--with-day 21]"` | no (0-1 Fata request per missing day) |
| Materialise the expected facts of every scenario | `make bot-eval-expect`, review the diff of `towns/_eval/fixtures/*/expected.json` | no |
| Check them after a tool change | `make bot-eval-expect-check` (exit 1 and a diff when a tool output moved) | no |
| Look at the setup without calling anything | `make bot-eval DRY=1 SUITE=core` | no |
| Run | `make bot-eval SUITE=core LABEL=baseline` (Haiku 5.5 on the public tier, Sonnet on trusted, per scenario) | **yes** |
| One model for everything | `make bot-eval MODEL=claude-haiku-5-5 TIER=public LABEL=x`; `ONLY=E1,K1 REPEAT=3` for a targeted repeat | yes |
| Grade deterministically | `make bot-eval-grade RUN=towns/_eval/runs/<run>.json` writes `<run>.graded.json` | no |
| Judge | `make bot-eval-judge RUN=towns/_eval/runs/<run>.json [ONLY=I1,C4] [FORCE=1] [DRY=1]` | **yes** (Opus, no tools) |
| Calibrate the judge against hand grades | `make bot-eval-calibrate` (reads `towns/_eval/calibration/sheet.md`) | no |
| Unit tests of the grader | `make bot-eval-grade-checks` | no |
| Compare two runs per scenario (regressions first, acceptance verdict) | `make bot-eval-compare A=towns/_eval/runs/<a>.json B=towns/_eval/runs/<b>.json [ONLY=E1,K1] [TARGET=E1,E2]` | no |
| Unit tests of the compare script | `make bot-eval-compare-checks` | no |
| Offline server by hand / its `--mcp-config` | `make bot-eval-server ID=<fixture>` / `make bot-eval-mcp-config ID=<fixture>` | no |

`SUITE=core` is the default; `SUITE=extended` or `all` select the others, `ONLY=` ignores the suite.
`REPEAT>1` needs `ONLY=`. The run refuses to finish cleanly if the real `towns/` tree changed (the
trusted tier is run without `Write` / `Edit`).

## Add a scenario

Create `towns/_eval/scenarios/<ID>.json` (private repo). Validate with
`.venv/bin/python tests/bot_eval/scenario.py` (it also runs inside every `make bot-eval`). The fields
(schema in `tests/bot_eval/scenario.py`, a synthetic full example in `scenario.example.json`):

| Field | Meaning |
|---|---|
| `id`, `fixture` | Scenario id; fixture folder under `towns/_eval/fixtures/` |
| `suite` | `core` (default) or `extended` |
| `clock` | Frozen game time: empty = data time + 10 min, `HH:MM`, or `+5h` |
| `tier`, `context` | `public` / `trusted`; `thread` / `dm` (memory needs `dm`) |
| `memory`, `user_town` | Synthetic bot memory text (DM only) / the asker's default town |
| `turns` | `[{lang, text}]`: one fresh session per scenario, later turns resume it |
| `tools_any` | D1: a list of tool names (any one) or a list of lists (every group needs a hit) |
| `tools_forbidden` | D2, on top of the built-in ones (`remember` / `forget` in a thread, skills, writes) |
| `args_required`, `args_forbidden` | D4 / D3: `{tool, args}`; an argument is a literal or one predicate `{ge, le, gt, lt, in, contains, present, absent, available_ge}` |
| `facts_from` | D5: reference calls `{tool, args, extract: [regex]}`, run offline to materialise the numbers an answer must contain |
| `invariants` | D11: named rule checks (`no_tool_names`, `start_ap_6`, `camping_one_call_until_day`, `upgrades_before_hiding_order`, `water_rations_ceil_half_days`, `heavy_items_max`, `drugs_max_one`) |
| `names_max`, `names_expected` | D9: citizen names allowed in the answers / names that must appear |
| `max_calls` | D12: game-tool call cap (default 6) |
| `writes_allowed` | D13: extra paths under `towns/` a run may write (fnmatch) |
| `hard_checks` | Which checks zero the scenario when they fail: `"D3"`, or one part `"D12:calls"`, `"D8:tool_names"` |
| `must`, `hard_fail` | Prose items for the judge (J1 / J2); write them as observable statements |

Rules of thumb:

- **Never type an expected number.** Declare a reference call in `facts_from` and run
  `make bot-eval-expect`: the tool's own output on the fixture is the gold answer, and a later tool
  change shows up as a reviewable diff (`bot-eval-expect-check`). Hand-written expectations are only for
  rule invariants and for `must` prose. A fact in the language of the question must be a number, a
  coordinate or a proper name, not an English word.
- **A real player's route or past answer is a scenario source, not a gold answer.**
- A scenario with several turns is one conversation. `context` is per scenario, so a DM turn and a
  thread turn are two scenarios.
- Keep `must` / `hard_fail` about what the tools return now; re-read them when a tool changes.

### Privacy

`towns/_eval/` is private, so real names are allowed in scenario files there. Everything in this
repository (docs, tests, Makefile, the example scenario) must hold **no** real player name, town-specific
citizen name or Discord id: use invented names or placeholders. Before pushing this repository, grep the
diff for the citizen names of every fixture. Do not paste scenario prompts into public issues.

## Read the result

`make bot-eval` prints, per scenario: language, `HF` (a hard check failed), `det` (deterministic checks
passed / applicable), tool calls, seconds, answer length and a note (the first failing check). The run
file `towns/_eval/runs/<date>-<label>-<model>.json` holds every prompt, answer, full tool trace, token
usage and the run metadata (git SHA, prompt hashes, fixture hashes). `<run>.graded.json` adds, per
scenario, each check as `pass` / `fail` / `n.a.` with its evidence, and after the judge `j1`-`j6`.

- **Score** per scenario: 0 on a hard fail (a failed `hard_checks` entry, or any J2 hit), otherwise
  `0.5 x det passed/applicable + 0.5 x J1 mean`. J3-J6 (leads with the blocker, assumptions stated,
  uncertainty, Discord fit) are reported, not scored.
- No single aggregate accepts a change: compare the **per scenario** table old against new, regressions
  first. One run per scenario is a direction, not a rate; use `ONLY=... REPEAT=3` on what a change targets.
- A hard fail is read by a person and classed as a bot defect, a scenario defect or a grader defect
  before anything is changed.

## Compare two runs

`make bot-eval-compare A=<before> B=<after>` reads two graded files (a run file stands for its sibling
`.graded.json`; grade and judge both runs first) and never calls a model. It prints a header (model, git SHA, system
prompt SHA per tier, rubric hash: what differs between the runs is marked), then the scenarios with regressions first,
improvements, unchanged, and the ones present on one side only. With `REPEAT=3` runs it reports, per scenario, hard fails
over repeats (1/3), mean score, mean tool calls, mean answer length and mean CLI cost. The last lines are the acceptance
rules of `bot-eval-plan.md` 6.3 step 5, each PASS or FAIL with the scenarios that broke it: no new hard fail anywhere;
every scenario named in `TARGET=E1,E2` free of hard fails in at least 2/3 of its repeats; no score drop above 0.2. A
change is measured like this: baseline run on `main`, the change, `ONLY=<targets> REPEAT=3` plus the core set once, judge
both, compare. With n = 1 a result is a direction, not a rate.

## Cost

Measured values and the estimate for a core run: section 6.2 of [bot-eval-plan.md](bot-eval-plan.md).
Judge calls cost about $0.06 each on average. A trusted-tier expedition or camping turn is the expensive
kind; `make bot-eval DRY=1` shows what would run before paying for it.
