# Future Improvements

Ideas that aren't actionable yet but worth revisiting.

## Gest'Hordes historical snapshots via authenticated session cookie

**Problem:** Gest'Hordes has a `/rest/v2/snapshot/{mapId}/{jour}/{type}` API that serves past-day town data (citizen positions, bank, map zones). The `/carte/{mapId}` page uses it for its snapshot viewer. It requires a valid `gh_session_id` session cookie — the public `rest/v1/stats` endpoint we already use is the only unauthenticated one.

**Idea:** Add a `get_historical_snapshot(day, type)` MCP tool backed by this API. The cookie would live in `.env` as `GESTHORDES_SESSION`. When missing or expired, the tool returns a clear message explaining how to extract it from browser DevTools.

**Known snapshot types** (from JS bundle, unconfirmed): `citoyen`, `banque`, `carte`. Needs probing with a real session to verify the response shapes.

**Complication:** The `cf_clearance` Cloudflare token is IP-bound and short-lived (hours). The `gh_session_id` is longer-lived. Need to handle expiry gracefully — either prompt for refresh or detect the HTML-instead-of-JSON response and return a helpful error.

**Fallback:** Fata Morgana already serves historical days via `/towndata?town={id}&day={day}` (all existing tools accept a `day` param). GH snapshots are only needed for days Fata doesn't have cached, or for data Fata doesn't expose (e.g. exact bank state at EOD).

**Status:** Idea only. Blocked on confirming snapshot type names and response shapes with a real session.
