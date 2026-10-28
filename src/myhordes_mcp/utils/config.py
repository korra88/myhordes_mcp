"""Environment-driven settings shared by all data sources.

`.env` is loaded once here, so any module that imports this sees the values.
"""

import os
import secrets
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


def _install_id() -> str:
    """Random per-installation ID, created on first run and kept in .install_id.

    Lets site owners tell installs apart in their logs. Random on purpose: nothing
    about the machine or the user is derived from it. Delete the file to reset.
    """
    path = PROJECT_ROOT / ".install_id"
    try:
        existing = path.read_text().strip()
        if existing:
            return existing
    except OSError:
        pass
    new_id = secrets.token_hex(4)
    try:
        path.write_text(new_id + "\n")
    except OSError:
        pass  # read-only checkout: the ID just changes on every restart
    return new_id


# Sent on every request to Fata Morgana and Gest'Hordes, so their admins can see
# who is behind the traffic. MCP_CONTACT (e.g. your MyHordes name) is optional.
USER_AGENT = (
    "myhordes-mcp/1.0 (+https://github.com/korra88/myhordes_mcp; "
    f"install={_install_id()}"
    + (f"; contact={os.getenv('MCP_CONTACT')}" if os.getenv("MCP_CONTACT") else "")
    + ")"
)


def env_int(name: str, default: int) -> int:
    """Read an int env var, falling back to default when unset or malformed."""
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default


# Automatic town log (fata/townlog.py): 0 = off. Interval = minutes between two auto "Check" entries.
TOWN_LOG_AUTO = env_int("TOWN_LOG_AUTO", 1)
TOWN_LOG_INTERVAL = env_int("TOWN_LOG_INTERVAL", 60)

# Default town, switchable without restarting the server: one town ID, read on every call.
CURRENT_TOWN_FILE = TOWNS_DIR / "_current_town"

# One file per Discord user, named by their id: that person's default town. The
# Discord listener sets LISTENER_USER_ID (the person who opened the conversation)
# in the server's environment; a terminal session has none and never reads these.
USER_TOWNS_DIR = TOWNS_DIR / "_user_towns"


def _listener_user_id() -> str | None:
    """The Discord id the listener passed down, or None.

    Digits only: the value becomes a file name, and anything else (`../x`) must
    never reach the path. ASCII, because `str.isdigit()` also accepts characters
    like `²`.
    """
    user = os.getenv("LISTENER_USER_ID", "")
    return user if user.isascii() and user.isdigit() and len(user) <= 25 else None


def resolve_town_id(town_id: int = 0) -> int | str:
    """Return a valid town ID (int) or an error message (str).

    Order: explicit non-zero town_id, then the requester's own
    towns/_user_towns/<LISTENER_USER_ID> (Discord only), then towns/_current_town,
    then the FATAMORGANA_TOWN_ID env var.
    """
    if town_id:
        return int(town_id)
    user = _listener_user_id()
    if user:
        try:
            mine = (USER_TOWNS_DIR / user).read_text().strip()
        except OSError:
            mine = ""
        if mine:
            if mine.isascii() and mine.isdigit():
                return int(mine)
            return f"Error: {USER_TOWNS_DIR.name}/{user} must contain only a town ID, found {mine!r}."
    try:
        current = CURRENT_TOWN_FILE.read_text().strip()
    except OSError:
        current = ""
    if current:
        if current.isascii() and current.isdigit():
            return int(current)
        return f"Error: {CURRENT_TOWN_FILE.name} must contain only a town ID, found {current!r}."
    if FATAMORGANA_TOWN_ID:
        return int(FATAMORGANA_TOWN_ID)
    return ("Error: No town ID provided, no towns/_user_towns/<your id> or towns/_current_town "
            "file, and FATAMORGANA_TOWN_ID not configured in .env.")
