# Town logs (`towns/`)

All town data lives in `towns/` at the repo root. The path is fixed (the server,
the skills and the Discord listener's write permissions all use it) and the folder
is gitignored, so your logs and other players' names never end up in this repo.

```
towns/
  _current_town               # default town ID (make town TOWN=...), re-read on every call
  _user_towns/<discord id>    # one person's default (Discord bot), make town TOWN=... FOR=<id>
  s{season}-{town-slug}/      # created by the server on the first live fetch
    cache/                    # written by the server
      _meta.json              #   town ID → this folder; skills find the folder through it
      day-NN.towndata.json.gz       #   /towndata of a finished day (final, never refetched)
      day-NN.towndata.live.json.gz  #   /towndata of the current day (overwritten on each fetch)
      day-NN.html / .json     #   legacy spy pages archived before 2026-10-15 (still read)
      estimations.json        #   attack estimate per day, for the defense history
      snapshots/              #   intra-day snapshots for get_town_changes
    citizens-cp.json          # CP log per citizen (last / max), written by the server
    camping-log.json          # who spent which night outside (sure / probable / planned / died), fata/camplog.py
    camp-zones.json           # last camp bonus (%) known per zone, written by plan_camping (one camper, tonight)
    daily-log.md              # kept by the server (townlog.py), started from templates/town/;
    day-NN.md                 #   the skills (inspect-town, close-day) add judgment on top
    notes.md
  _bot/                       # Discord bot (docs/discord.md, "Memory and feedback log")
    memory/<discord id>.md    #   one person's facts, DM only (remember/forget tools)
    memory.md.migrated        #   the old shared memory, after make bot-memory-migrate
    feedback/                 #   one file per feedback entry, when the log is on
      reviewed/               #   moved here by /review-bot-feedback
```

Tools called without `town_id` use the default town: `towns/_user_towns/<LISTENER_USER_ID>`
when the Discord listener started the server for a person (docs/discord.md), else
`towns/_current_town`, else `FATAMORGANA_TOWN_ID` from `.env`. `make town` shows it, `make town TOWN=8212` switches
it; the server picks the change up on its next call. If `towns/` is a git repo (below),
the file is tracked, so the switch reaches your other machines with the next commit.

To keep the data somewhere else (another disk, a synced folder), make `towns` a
symlink: `ln -s /path/to/your/town-data towns`.

## What the server writes

Fata data comes from the public `/towndata` JSON endpoint and is cached in memory for
`FATA_CACHE_TTL` seconds (default 180); concurrent calls share one request. A past day
is stored once and then served from disk; the current day is refetched. Every live
fetch of the current day also stores a small snapshot under `cache/snapshots/`, which
`get_town_changes` compares, and adds the zone CP readings to `citizens-cp.json`.

**CP log.** Fata reports CP per zone (game data, items and status included), not per
citizen. A citizen's CP is recorded when they stand alone on a zone, or derived from a
group when the others were read alone the same day. The log keeps the last and the
best value, since CP drops with status (drugs, drunk, thirsty with the Expert skill, guardian
without shield); 0 is kept, since terrorised citizens have none. Limit: Fata does not say who
was on the zone at the update, so a citizen who left afterwards can inflate a reading.
The log only grows when tools fetch the town (no polling).

**Camping log.** `camping-log.json` (`fata/camplog.py`): a citizen outside at the end of
day N and alive on day N+1 camped night N. Judged from the day N and day N+1 archives:
*sure* when the next day's position update is still on the same zone, *probable* when
the last day-N update is from 19:00 on and Fata shows nothing newer or the citizen back in
town (earlier updates without confirmation are day trips, not counted),
plus *planned*: citizens listed in a Fata camp plan for that night (archives from towndata v1.3 on),
alive next day, not back in town at 19:00 or later (night 25 of town 8299: 19 in plans, 2 died,
the older rule logged 5 survivors); plus citizens that vanished outside (death type 5). Probable
and planned nights are never reported as confirmed; `plan_camping` counts sure + probable +
planned (pessimistic) and says so. Each stored night carries a rules version (`rules`): after a
rule change the next update recomputes it once. Updated on
live fetches, only where `TOWN_LOG_AUTO` is on (the Pi: one writer for the shared towns/ repo), a night is recomputed only when its two archive files changed. Backfill missing
past days (one Fata request each, user-run): `make camp-log-backfill TOWN=8299 [FROM=1]`.
`camp-zones.json`: per zone the camp bonus a player reported or the tool's own plan
reached (`reported` / `planned`), decayed 15% a night when used; written by `plan_camping` (one camper, tonight)
(`record=False` skips it).

**Town log.** Every live fetch of the current day also updates `daily-log.md` and
`day-NN.md` (`fata/townlog.py`): it opens the current day, closes past days from Fata
data (Night outcome block and table row, without Gest'Hordes), and appends a "Check"
entry when something changed, at most every `TOWN_LOG_INTERVAL` minutes (default 60).
The first tool header after an update carries a one-line note saying what was written.
Switch it off with `TOWN_LOG_AUTO=0`; with two machines sharing `towns/` via git, enable
it on one only, or both will write the same entries and conflict.

## Tracking your logs in a private git repo

Useful to keep history, back the logs up, or share them between machines (e.g. a
Raspberry Pi running the Discord listener and your PC).

```bash
cd towns                                  # exists after the first live fetch; else mkdir towns
git init -b main
printf '**/cache/\n**/citizens-cp.json\n' > .gitignore   # see the notes below
git add -A && git commit -m "Initial town logs"
gh repo create <you>/myhordes-town-data --private --source=. --push
# without gh: create an empty private repo, then
#   git remote add origin <url> && git push -u origin main
```

On another machine, clone it into place before the first run:

```bash
cd myhordes_mcp
git clone <url-of-your-town-data-repo> towns
```

Notes:

- **Keep it private.** Logs contain other players' names and your town's plans.
- **`cache/` stays out of git.** It grows to tens of MB per long town and changes on
  every fetch. It is also the only copy of old Fata data, so back it up separately
  if you care about it (e.g. `rsync -a towns/ backup-host:myhordes-towns/`).
  Snapshots live there too, so `get_town_changes` only compares fetches made on the
  same machine. `citizens-cp.json` changes on every fetch as well: each machine keeps
  its own.
- **Committing.** `make towns-commit` commits whatever changed, pulls with rebase
  (another machine may have pushed) and pushes. `make towns-commit-install` runs it
  every night at 04:00 through a systemd user timer (`towns-commit-disable` /
  `towns-commit-uninstall` undo it; logs in `journalctl --user-unit towns-commit`).
  It only touches your files, never the game or Fata, so it does not conflict with
  the no-automated-polling rule.
- **One writer at a time.** If the listener and you both write the same day file on
  two machines, pull before writing or expect merge conflicts.
