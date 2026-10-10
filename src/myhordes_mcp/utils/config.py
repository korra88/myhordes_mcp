"""Environment-driven settings shared by all data sources.

`.env` is loaded once here, so any module that imports this sees the values.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root: src/myhordes_mcp/utils/config.py -> three levels up.
PROJECT_ROOT = Path(__file__).resolve().parents[3]

load_dotenv(PROJECT_ROOT / ".env")

FATAMORGANA_TOWN_ID = os.getenv("FATAMORGANA_TOWN_ID")

# Your in-game name: some reports single you out (e.g. "you are on a depleted zone").
PLAYER_NAME = os.getenv("PLAYER_NAME")

# Town logs and the Fata page archive. Override to keep them outside the repo
# (e.g. a private checkout on another machine).
TOWNS_DIR = Path(os.getenv("MYHORDES_TOWNS_DIR") or PROJECT_ROOT / "towns")


def env_int(name: str, default: int) -> int:
    """Read an int env var, falling back to default when unset or malformed."""
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default


def resolve_town_id(town_id: int = 0) -> int | str:
    """Return a valid town ID (int) or an error message (str).

    If town_id is provided and non-zero, use it directly.
    Otherwise fall back to the FATAMORGANA_TOWN_ID env var.
    """
    if town_id:
        return int(town_id)
    if FATAMORGANA_TOWN_ID:
        return int(FATAMORGANA_TOWN_ID)
    return "Error: No town ID provided and FATAMORGANA_TOWN_ID not configured in .env."
