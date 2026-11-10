"""log_feedback / remember / forget: the bot's only writable paths, with fixed names.

The author id comes from the environment the Discord listener sets
(LISTENER_USER_ID, LISTENER_CONTEXT), never from a tool argument. Every function
returns the text the tool hands back to the model (errors included).
"""

import datetime as dt
import os
from pathlib import Path

from myhordes_mcp.utils.config import TOWNS_DIR, _listener_user_id

BOT_DIR = TOWNS_DIR / "_bot"

KINDS = ("complaint", "praise", "correction", "missing-tool", "permission", "missing-data", "tool-issue")
SAID_MAX = 300
LONG_MAX = 1000
FACT_MAX = 300
MEMORY_MAX_LINES = 40
MEMORY_HEADER = "# Bot memory"

NOT_LISTENER = "Error: only from the Discord listener (no LISTENER_USER_ID)."
NOT_DM = "Error: memory exists only in private messages."


def _digits(value: str) -> bool:
    return bool(value) and value.isascii() and value.isdigit() and len(value) <= 25


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _write_atomic(path: Path, text: str) -> None:
    """tmp with a name unique per writer + replace (same pattern as fata/archive.py)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def log_feedback(kind: str, message_id: str, channel: str, said: str, context: str, idea: str) -> str:
    user = _listener_user_id()
    if not user:
        return NOT_LISTENER
    if kind not in KINDS:
        return f"Error: kind must be one of: {', '.join(KINDS)}."
    message_id = str(message_id).strip()
    if not _digits(message_id):
        return "Error: message_id must be digits only (the id of the message you are answering)."
    said, context, idea = _one_line(said), _one_line(context), _one_line(idea)
    channel = _one_line(channel).lstrip("#")
    if not said or not context or not idea or not channel:
        return "Error: channel, said, context and idea must not be empty."
    if len(said) > SAID_MAX:
        return f"Error: said is {len(said)} characters, the limit is {SAID_MAX}."
    if len(context) > LONG_MAX or len(idea) > LONG_MAX:
        return f"Error: context and idea are limited to {LONG_MAX} characters."
    if len(channel) > 100:
        return "Error: channel is too long."
    now = dt.datetime.now(dt.timezone.utc)
    path = BOT_DIR / "feedback" / f"{now:%Y-%m-%d}-{message_id}.md"
    if path.exists():
        return "already logged (one entry per message)."
    said = said.replace('"', "'")
    body = (
        f"# {kind} — #{channel} [{message_id}] {now.isoformat()}\n\n"
        f'- said: "{said}" (author id {user})\n'
        f"- context: {context}\n"
        f"- idea: {idea}\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive create: two writers on the same message cannot overwrite each other.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return "already logged (one entry per message)."
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    return f"logged: {path.name}"


def _memory_access() -> tuple[Path | None, str]:
    """(memory file, "") or (None, refusal text)."""
    user = _listener_user_id()
    if not user:
        return None, NOT_LISTENER
    if os.getenv("LISTENER_CONTEXT", "") != "dm":
        return None, NOT_DM
    return BOT_DIR / "memory" / f"{user}.md", ""


def _read_lines(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [ln for ln in text.splitlines() if ln.startswith("- ")]


def _save(path: Path, lines: list[str]) -> None:
    _write_atomic(path, "\n".join([MEMORY_HEADER, *lines]) + "\n")


def remember(fact: str) -> str:
    path, refusal = _memory_access()
    if path is None:
        return refusal
    fact = _one_line(fact)
    if not fact:
        return "Error: fact is empty."
    if len(fact) > FACT_MAX:
        return f"Error: fact is {len(fact)} characters, the limit is {FACT_MAX}. Shorten it."
    lines = _read_lines(path)
    if len(lines) >= MEMORY_MAX_LINES:
        return f"Memory is full ({MEMORY_MAX_LINES} lines). Ask the reader which line to forget, then call forget."
    today = dt.date.today().isoformat()
    lines.append(f"- {today} · {fact}")
    _save(path, lines)
    return f"remembered ({len(lines)}/{MEMORY_MAX_LINES} lines)."


def forget(text: str) -> str:
    path, refusal = _memory_access()
    if path is None:
        return refusal
    needle = _one_line(text).lower()
    if not needle:
        return "Error: text is empty."
    lines = _read_lines(path)
    keep = [ln for ln in lines if needle not in ln.lower()]
    removed = len(lines) - len(keep)
    if not removed:
        return "nothing matched, nothing removed."
    _save(path, keep)
    return f"forgot {removed} line(s)."
