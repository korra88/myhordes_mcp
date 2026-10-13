"""
set_town.py — Show or set the default town (towns/_current_town).

The MCP server re-reads towns/_current_town on every call, so switching town
needs no restart. With no argument, prints the current default. Standard
library only, so it runs without the project's venv (e.g. from a bot command).

Usage:
    python3 scripts/set_town.py           # show the default town
    python3 scripts/set_town.py 8212      # set it (Fata Morgana town ID)
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

TOWNS_DIR = Path(__file__).resolve().parent.parent / "towns"
CURRENT_TOWN_FILE = TOWNS_DIR / "_current_town"
TOWN_ID = re.compile(r"^\d{1,7}$")


def town_folder(town_id: int) -> str | None:
    """Name of the towns/ folder archived for this town ID, if any."""
    for meta in TOWNS_DIR.glob("*/cache/_meta.json"):
        try:
            if json.loads(meta.read_text()).get("town_id") == town_id:
                return meta.parent.parent.name
        except (OSError, ValueError):
            continue
    return None


def describe(town_id: int) -> str:
    folder = town_folder(town_id)
    where = f"towns/{folder}/" if folder else "no folder yet, created on the first live fetch"
    return f"{town_id} ({where})"


def show() -> int:
    try:
        current = CURRENT_TOWN_FILE.read_text().strip()
    except OSError:
        print("No default town in towns/_current_town; the server falls back to "
              "FATAMORGANA_TOWN_ID in .env.")
        return 0
    if not TOWN_ID.match(current):
        print(f"towns/_current_town is invalid: {current!r}. Set it again.")
        return 1
    print(f"Default town: {describe(int(current))}")
    return 0


def set_town(arg: str) -> int:
    if not TOWN_ID.match(arg):
        print(f"Not a town ID: {arg!r} (expected 1-7 digits, the Fata Morgana town ID).")
        return 2
    town_id = int(arg)
    TOWNS_DIR.mkdir(exist_ok=True)
    # Atomic: the server may read the file while it is being replaced.
    fd, tmp = tempfile.mkstemp(dir=TOWNS_DIR, prefix="._current_town.")
    with os.fdopen(fd, "w") as f:
        f.write(f"{town_id}\n")
    os.replace(tmp, CURRENT_TOWN_FILE)
    print(f"Default town set to {describe(town_id)}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        print(__doc__.strip().split("\n\n")[-1])
        return 2
    return set_town(argv[0].strip()) if argv else show()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
