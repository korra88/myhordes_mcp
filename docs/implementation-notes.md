# Implementation Notes

Design decisions made during development, with rationale. Revisit these if requirements change.

---

## Agent Memory: Local Files via Claude Code (Option A)

**Decision:** The advisor agent maintains town memory as local markdown files in `towns/`, written by Claude Code's file tools during a session.

**Alternatives considered:**
- **Option B — MCP tools (`read_town_log` / `append_town_log`):** Would expose memory via the MCP protocol, making it client-agnostic. Rejected for now: adds code complexity, and bends the "read-only MCP" mental model even though local file I/O is not a game action.
- **Option C — Static files loaded via `--append-system-prompt-file`:** Zero token cost but only suitable for stable historical data. Not suitable for live per-session updates.

**Why Option A:**
- No new code required — Claude Code already has Read/Write tools
- Memory files are human-readable and directly editable by the user
- The read-only constraint applies to game actions only; local filesystem writes are fine
- Files live in the repo checkout (`towns/`, gitignored), next to `knowledge/`

**Revisit if:**
- A non-Claude Code client needs access to town memory (→ upgrade to Option B)
- Memory files grow large enough to impact system prompt loading (→ Option C for historical, Option A for current town only)

**Structure:**
```
towns/                  # fixed path, gitignored; optionally its own private repo
  s{season}-{town-slug}/  # created by the server on the first live fetch
    cache/              # server-written: _meta.json (town ID → folder), day pages, snapshots
    daily-log.md        # one summary row per day, written by the skills
    day-NN.md           # per-day report
    notes.md            # strategic observations, player behavior, open questions
```

Skills locate the folder through `cache/_meta.json` (town ID), never by deriving
the slug from the town name, so code and skills always agree on the folder. The
path is not configurable: the Discord listener's write permissions and the skills
hardcode `towns/`. Use a symlink to store it elsewhere.

---

## MCP: Read-Only Only

**Decision:** The MCP server never implements write or action endpoints.

**Why:** MyHordes has a strict anti-botting policy. Any automated game action risks account bans. Read-only data fetching for advisory purposes is explicitly permitted. See `docs/game-rules-for-external-apps.md`.

**Revisit if:** The official API introduces a sanctioned write interface with explicit bot permissions.

---

## Data Source: Fata Morgana over Official API

**Decision:** All live data currently comes from Fata Morgana (`src/myhordes_mcp/fata/`), not the official JSON v1 API. Since 2026-10-15 through the public `/towndata` JSON endpoint of the beta site, which the Fata developer confirmed is fine for this MCP; before that, by scraping the legacy spy page.

**Why:** The official API requires a registered `appkey` which has not yet been obtained. Fata Morgana provides a superset of the data we need (defense, citizens, buildings, scout map, bank) with no auth required beyond a town ID.

**Revisit if:** The official app key is obtained — at that point, prefer the official API for data the official API covers, and keep Fata Morgana only for data it uniquely provides (scout map, zone CP, scavenging state).
