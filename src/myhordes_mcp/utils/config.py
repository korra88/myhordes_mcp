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

# Town logs and the Fata page archive. Fixed path: skills and the Discord listener's
# write permissions use `towns/` too. To keep the data elsewhere, make it a symlink.
TOWNS_DIR = PROJECT_ROOT / "towns"


def env_int(name: str, default: int) -> int:
    """Read an int env var, falling back to default when unset or malformed."""
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default


# Default town, switchable without restarting the server: one town ID, read on every call.
CURRENT_TOWN_FILE = TOWNS_DIR / "_current_town"


def resolve_town_id(town_id: int = 0) -> int | str:
    """Return a valid town ID (int) or an error message (str).

    Order: explicit non-zero town_id, then towns/_current_town, then the
    FATAMORGANA_TOWN_ID env var.
    """
    if town_id:
        return int(town_id)
    try:
        current = CURRENT_TOWN_FILE.read_text().strip()
    except OSError:
        current = ""
    if current:
        if current.isdigit():
            return int(current)
        return f"Error: {CURRENT_TOWN_FILE.name} must contain only a town ID, found {current!r}."
    if FATAMORGANA_TOWN_ID:
        return int(FATAMORGANA_TOWN_ID)
    return ("Error: No town ID provided, no towns/_current_town file, "
            "and FATAMORGANA_TOWN_ID not configured in .env.")
