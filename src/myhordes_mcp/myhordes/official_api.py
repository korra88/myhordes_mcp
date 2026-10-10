"""Official MyHordes JSON v1 API client — DISABLED, not registered as MCP tools.

Endpoint: https://myhordes.eu/api/x/json/{type} (reference:
docs/external-api-reference.md). Needs two keys from .env:
- MYHORDES_USER_KEY: the player's External ID (whose data to fetch)
- MYHORDES_APP_KEY:  the registered app secret (identifies this application)

Constraints if this is ever enabled (docs/game-rules-for-external-apps.md):
- Read-only. No action endpoints.
- No automated polling: every call must come from a user query.
- The API is blocked around 23:59 CET during the nightly attack
  (`nightly_attack` error) — handle it gracefully.

Planned tools, because Fata Morgana lacks this data:
- get_construction_progress: AP invested vs. needed and resources deposited
  per construction site — "what's closest to being finished?"
- get_last_night_report: attack gazette — zombies, defense used, water lost,
  wind direction (Search Tower), casualties.
"""

import os

from ..utils import config  # noqa: F401  (loads .env)


def check_auth() -> str | None:
    """Return an error message if official API credentials are missing, None if OK."""
    missing = [k for k in ("MYHORDES_USER_KEY", "MYHORDES_APP_KEY") if not os.getenv(k)]
    if missing:
        return f"Authentication Error: {', '.join(missing)} not configured. See .env.example."
    return None
