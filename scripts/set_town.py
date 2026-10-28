"""
set_town.py — Show or set the default town (towns/_current_town), or one
Discord user's own default (towns/_user_towns/<discord id>).

The MCP server re-reads these files on every call, so switching town needs no
restart. With no town ID, prints the current default. With `--user` the output is written for
the Discord user (no file paths, no ids). Standard library only, so
it runs without the project's venv (e.g. from a bot command).

Usage:
    python3 scripts/set_town.py                       # show the shared default town
    python3 scripts/set_town.py 8212                  # set it (Fata Morgana town ID)
    python3 scripts/set_town.py --user 1234567890     # show that user's default
    python3 scripts/set_town.py --user 1234567890 8212  # set that user's default
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

TOWNS_DIR = Path(__file__).resolve().parent.parent / "towns"
CURRENT_TOWN_FILE = TOWNS_DIR / "_current_town"
USER_TOWNS_DIR = TOWNS_DIR / "_user_towns"
TOWN_ID = re.compile(r"^\d{1,7}$")
# `re.ASCII` and a length cap: the id becomes a file name, so nothing else may pass.
DISCORD_ID = re.compile(r"^\d{1,25}$", re.ASCII)


def find_town(town_id: int) -> tuple[str, dict] | None:
    """The towns/ folder archived for this town ID and its cache/_meta.json, if any."""
    for meta in TOWNS_DIR.glob("*/cache/_meta.json"):
        try:
            data = json.loads(meta.read_text())
            if data.get("town_id") == town_id:
                return meta.parent.parent.name, data
        except (OSError, ValueError, AttributeError):
            continue
    return None


def town_folder(town_id: int) -> str | None:
    """Name of the towns/ folder archived for this town ID, if any."""
    found = find_town(town_id)
    return found[0] if found else None


def user_message(town_id: int, previous: str | None) -> str:
    """What a Discord user is told after setting their town: no paths, no ids
    but the town's own."""
    found = find_town(town_id)
    meta = found[1] if found else {}
    if meta.get("town_name"):
        text = (f"Your default town is now {town_id}: {meta['town_name']} "
                f"(season {meta.get('season')}, day {meta.get('current_day')}).")
    else:
        text = (f"Your default town is now {town_id}. I have no data on it yet; "
                "it is read on your first question.")
    if previous and TOWN_ID.match(previous) and int(previous) != town_id:
        text += f" It was {int(previous)}."
    return text


def describe(town_id: int) -> str:
    folder = town_folder(town_id)
    where = f"towns/{folder}/" if folder else "no folder yet, created on the first live fetch"
    return f"{town_id} ({where})"


def show(path: Path = CURRENT_TOWN_FILE, who: str = "") -> int:
    label = str(path.relative_to(TOWNS_DIR.parent))
    try:
        current = path.read_text().strip()
    except OSError:
        if who:
            print(f"No default town for user {who} in {label}; the server uses the shared "
                  "default (towns/_current_town).")
        else:
            print("No default town in towns/_current_town; the server falls back to "
                  "FATAMORGANA_TOWN_ID in .env.")
        return 0
    if not TOWN_ID.match(current):
        print(f"{label} is invalid: {current!r}. Set it again.")
        return 1
    print(f"Default town{f' for user {who}' if who else ''}: {describe(int(current))}")
    return 0


def set_town(arg: str, path: Path = CURRENT_TOWN_FILE, who: str = "") -> int:
    if not TOWN_ID.match(arg):
        if who:
            print(f"Not a town ID: {arg!r} (expected the Fata Morgana town ID, digits only).")
        else:
            print(f"Not a town ID: {arg!r} (expected 1-7 digits, the Fata Morgana town ID).")
        return 2
    town_id = int(arg)
    try:
        previous = path.read_text().strip()
    except OSError:
        previous = None
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic: the server may read the file while it is being replaced.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f"._{path.name}.")
    with os.fdopen(fd, "w") as f:
        f.write(f"{town_id}\n")
    os.replace(tmp, path)
    if who:
        print(user_message(town_id, previous))
    else:
        print(f"Default town set to {describe(town_id)}")
    return 0


def user_file(user: str) -> Path | None:
    return USER_TOWNS_DIR / user if DISCORD_ID.match(user) else None


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--user":
        if len(argv) not in (2, 3):
            print(__doc__.strip().split("\n\n")[-1])
            return 2
        path = user_file(argv[1].strip())
        if path is None:
            print(f"Not a Discord user id: {argv[1]!r} (expected digits only).")
            return 2
        who = path.name
        return set_town(argv[2].strip(), path, who) if len(argv) == 3 else show(path, who)
    if len(argv) > 1:
        print(__doc__.strip().split("\n\n")[-1])
        return 2
    return set_town(argv[0].strip()) if argv else show()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
