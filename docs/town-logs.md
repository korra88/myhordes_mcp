# Town logs (`towns/`)

All town data lives in `towns/` at the repo root. The path is fixed (the server,
the skills and the Discord listener's write permissions all use it) and the folder
is gitignored, so your logs and other players' names never end up in this repo.

```
towns/
  _current_town               # default town ID (make town TOWN=...), re-read on every call
  s{season}-{town-slug}/      # created by the server on the first live fetch
    cache/                    # written by the server
      _meta.json              #   town ID → this folder; skills find the folder through it
      day-NN.towndata.json.gz       #   /towndata of a finished day (final, never refetched)
      day-NN.towndata.live.json.gz  #   /towndata of the current day (overwritten on each fetch)
      day-NN.html / .json     #   legacy spy pages archived before 2026-10-15 (still read)
      estimations.json        #   attack estimate per day, for the defense history
      snapshots/              #   intra-day snapshots for get_town_changes
    citizens-cp.json          # CP log per citizen (last / max), written by the server
    daily-log.md              # written by the skills (inspect-town, close-day),
    day-NN.md                 #   started from templates/town/
    notes.md
  _bot/                       # Discord bot (docs/discord.md, "Memory and feedback log")
    memory.md                 #   facts kept across threads, written by the bot
    feedback/                 #   one file per feedback entry, when the log is on
      reviewed/               #   moved here by /review-bot-feedback
```

Tools called without `town_id` use the default town: `towns/_current_town`, else
`FATAMORGANA_TOWN_ID` from `.env`. `make town` shows it, `make town TOWN=8212` switches
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
best value, since CP drops with status (drugs, drunk, thirsty, guardian without
shield); 0 is kept, since terrorised citizens have none. Limit: Fata does not say who
was on the zone at the update, so a citizen who left afterwards can inflate a reading.
The log only grows when tools fetch the town (no polling).

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
