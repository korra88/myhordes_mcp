# Implementation Notes

Design decisions made during development, with rationale. Revisit these if requirements change.

---

## Agent Memory: Local Files via Claude Code (Option A)

**Decision:** The Desert Veteran agent maintains town memory as local markdown files in `towns/`, written by Claude Code's file tools during a session.

**Alternatives considered:**
- **Option B — MCP tools (`read_town_log` / `append_town_log`):** Would expose memory via the MCP protocol, making it client-agnostic. Rejected for now: adds code complexity, and bends the "read-only MCP" mental model even though local file I/O is not a game action.
- **Option C — Static files loaded via `--append-system-prompt-file`:** Zero token cost but only suitable for stable historical data. Not suitable for live per-session updates.

**Why Option A:**
- No new code required — Claude Code already has Read/Write tools
- Memory files are human-readable and directly editable by the user
- The read-only constraint applies to game actions only; local filesystem writes are fine
- Files live alongside `tips/` in the repo, same mental model

**Revisit if:**
- A non-Claude Code client needs access to town memory (→ upgrade to Option B)
- Memory files grow large enough to impact system prompt loading (→ Option C for historical, Option A for current town only)

**Structure:**
```
towns/
  s{season}-{town-slug}/
    daily-log.md    # day-by-day snapshots written by the agent
    notes.md        # strategic observations, player behavior, open questions
```

---

## MCP: Read-Only Only

**Decision:** The MCP server never implements write or action endpoints.

**Why:** MyHordes has a strict anti-botting policy. Any automated game action risks account bans. Read-only data fetching for advisory purposes is explicitly permitted. See `docs/game-rules-for-external-apps.md`.

**Revisit if:** The official API introduces a sanctioned write interface with explicit bot permissions.

---

## Data Source: Fata Morgana over Official API

**Decision:** All live data currently comes from the Fata Morgana spy page scraper (`sources/fatamorgana.py`), not the official JSON v1 API.

**Why:** The official API requires a registered `appkey` which has not yet been obtained. Fata Morgana provides a superset of the data we need (defense, citizens, buildings, scout map, bank) with no auth required beyond a town ID.

**Revisit if:** The official app key is obtained — at that point, prefer the official API for data the official API covers, and keep Fata Morgana only for data it uniquely provides (scout map, spy-page extras).
