"""Compact intraday snapshot of a parsed Fata result, stored by the client on
every live fetch that changed something (archive.save_snapshot)."""

import hashlib
import json
import time

from .bank import totals
from .risk import platform_level


def snapshot(data: dict) -> dict:
    """Compact, comparable state of a parsed Fata result."""
    bank = totals(data["bank"])
    content = {
        "day": data["meta"].get("day"),
        "data_time": data["meta"].get("data_time"),
        "citizens": {
            str(c["id"]): {"name": c["name"], "job": c["job"], "coords": c["coords"], "inside": c["inside_town"]}
            for c in data["citizens"]
        },
        "bank": bank,
        "defense": data["defense"].get("total"),
        "gate": data["gate"],
        "deaths": len(data["deaths"]),
        "platform_level": platform_level(data),
        "built": {b["name"]: b.get("level") for b in data["buildings"] if b["built"]},
    }
    hashed = {k: v for k, v in content.items() if k != "data_time"}
    content["hash"] = hashlib.sha1(json.dumps(hashed, sort_keys=True).encode()).hexdigest()
    content["taken_at"] = int(time.time())
    return content
