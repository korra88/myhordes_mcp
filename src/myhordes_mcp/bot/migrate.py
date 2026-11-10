"""One-off, idempotent: towns/_bot/memory.md (shared) -> towns/_bot/memory/<user>.md (per user).

Run on the Pi at deploy: `make bot-memory-migrate`. The old file is kept (renamed
memory.md.migrated) so a second run finds nothing to do. Lines of the form
`- DATE · USER · FACT` move to that user's file as `- DATE · FACT`; a line whose
fact contains a DROP phrase is dropped.
"""

import sys
from pathlib import Path

from myhordes_mcp.bot import store

DROP = ("also run inspect-town",)  # contradicts prompts/discord.md (user decision 2026-11-10)


def migrate(bot_dir: Path) -> str:
    old = bot_dir / "memory.md"
    if not old.exists():
        return "nothing to migrate (no memory.md)."
    by_user: dict[str, list[str]] = {}
    dropped = 0
    for ln in old.read_text(encoding="utf-8").splitlines():
        if not ln.startswith("- "):
            continue
        parts = [p.strip() for p in ln[2:].split(" · ", 2)]
        if len(parts) != 3 or not store._digits(parts[1]):
            raise SystemExit(f"unrecognised line, aborting without changes: {ln!r}")
        date, user, fact = parts
        if any(d in fact for d in DROP):
            dropped += 1
            continue
        by_user.setdefault(user, []).append(f"- {date} · {fact}")
    for user, lines in by_user.items():
        target = bot_dir / "memory" / f"{user}.md"
        existing = store._read_lines(target)
        store._save(target, existing + [ln for ln in lines if ln not in existing])
    old.rename(old.with_name("memory.md.migrated"))
    return f"migrated {sum(map(len, by_user.values()))} line(s) for {len(by_user)} user(s), dropped {dropped}."


if __name__ == "__main__":
    print(migrate(Path(sys.argv[1]) if len(sys.argv) > 1 else store.BOT_DIR))
