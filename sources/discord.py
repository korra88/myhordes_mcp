"""Discord REST API client — read-only channel access via bot token.

Uses Discord HTTP API directly (no discord.py dependency).
Bot token loaded from DISCORD_BOT_TOKEN env var.
"""

import os
import re
from typing import Optional

import httpx

DISCORD_API = "https://discord.com/api/v10"
BOT_USER_ID = "BOT_USER_ID"  # Town Elder#9092


def _headers() -> dict:
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise ValueError("DISCORD_BOT_TOKEN not set in environment")
    return {"Authorization": f"Bot {token}"}


def _parse_message(msg: dict) -> dict:
    return {
        "id": msg["id"],
        "author_id": msg["author"]["id"],
        "author": msg["author"]["username"],
        "bot": msg["author"].get("bot", False),
        "content": msg["content"],
        "timestamp": msg["timestamp"],
    }


def get_messages(
    channel_id: str,
    after: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    params: dict = {"limit": min(limit, 100)}
    if after:
        params["after"] = after

    with httpx.Client() as client:
        r = client.get(
            f"{DISCORD_API}/channels/{channel_id}/messages",
            headers=_headers(),
            params=params,
        )
        r.raise_for_status()

    # Discord returns newest-first; reverse to chronological order
    messages = [_parse_message(m) for m in reversed(r.json())]
    return messages


def get_mentions(
    channel_id: str,
    after: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Return only messages that mention the Town Elder bot and were not sent by it."""
    messages = get_messages(channel_id, after=after, limit=limit)
    pattern = f"<@{BOT_USER_ID}>"
    return [
        m for m in messages
        if pattern in m["content"] and not m["bot"]
    ]


def filter_messages(
    messages: list[dict],
    regex_filter: Optional[str] = None,
) -> list[dict]:
    if not regex_filter:
        return messages
    compiled = re.compile(regex_filter, re.IGNORECASE)
    return [m for m in messages if compiled.search(m["content"])]


def send_message(channel_id: str, content: str) -> dict:
    with httpx.Client() as client:
        r = client.post(
            f"{DISCORD_API}/channels/{channel_id}/messages",
            headers=_headers(),
            json={"content": content},
        )
        r.raise_for_status()
    return r.json()
