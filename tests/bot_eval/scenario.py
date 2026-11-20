"""Scenario files (towns/_eval/scenarios/<ID>.json): loader and validation, plain Python.
Format and fields: docs/bot-eval-plan.md sections 3, 5.4, 8; a synthetic example in
scenario.example.json.

    .venv/bin/python tests/bot_eval/scenario.py [FILE ...]     validate (default: all private ones)
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS = ROOT / "towns" / "_eval" / "scenarios"
FIXTURES = ROOT / "towns" / "_eval" / "fixtures"

TIERS = ("public", "trusted")
SUITES = ("core", "extended")
CONTEXTS = ("thread", "dm")
# field -> (type, default); a field without a default is required
FIELDS = {
    "id": (str, None), "fixture": (str, None), "turns": (list, None),
    "suite": (str, "core"), "clock": (str, ""), "tier": (str, "public"), "context": (str, "thread"),
    "memory": (str, ""), "user_town": (int, 0),
    "tools_any": (list, []), "tools_forbidden": (list, []),
    "args_required": (list, []), "args_forbidden": (list, []),
    "facts_from": (list, []), "invariants": (list, []),
    "max_calls": (int, 0), "must": (list, []), "hard_fail": (list, []),
}


class ScenarioError(ValueError):
    pass


def validate(data: dict, where: str = "scenario", check_fixture: bool = True) -> dict:
    """The scenario with defaults filled in; ScenarioError listing every problem."""
    errors = []
    if not isinstance(data, dict):
        raise ScenarioError(f"{where}: not a JSON object")
    for k in data:
        if k not in FIELDS and not k.startswith("_"):
            errors.append(f"unknown field '{k}'")
    out = {}
    for k, (typ, default) in FIELDS.items():
        if k not in data:
            if default is None:
                errors.append(f"missing field '{k}'")
            else:
                out[k] = default
            continue
        v = data[k]
        if not isinstance(v, typ) or (typ is int and isinstance(v, bool)):
            errors.append(f"'{k}' must be {typ.__name__}")
        out[k] = v
    if not errors:
        if out["tier"] not in TIERS:
            errors.append(f"tier must be one of {TIERS}")
        if out["suite"] not in SUITES:
            errors.append(f"suite must be one of {SUITES}")
        if out["context"] not in CONTEXTS:
            errors.append(f"context must be one of {CONTEXTS}")
        if out["memory"] and out["context"] != "dm":
            errors.append("memory needs context 'dm' (the bot reads memory only in a DM)")
        if not out["turns"]:
            errors.append("turns is empty")
        for i, t in enumerate(out["turns"]):
            if not (isinstance(t, dict) and isinstance(t.get("text"), str) and t["text"]
                    and isinstance(t.get("lang", ""), str)):
                errors.append(f"turns[{i}] must be {{lang, text}}")
        for key in ("tools_any", "tools_forbidden", "must", "hard_fail"):
            if not all(isinstance(x, str) for x in out[key]):
                errors.append(f"'{key}' must be a list of strings")
        for key in ("args_required", "args_forbidden"):
            if not all(isinstance(x, dict) and isinstance(x.get("tool"), str) and isinstance(x.get("args", {}), dict)
                       for x in out[key]):
                errors.append(f"'{key}' entries must be {{tool, args}}")
        for i, f in enumerate(out["facts_from"]):
            if not (isinstance(f, dict) and isinstance(f.get("tool"), str)
                    and isinstance(f.get("args", {}), dict)
                    and isinstance(f.get("extract", []), list) and all(isinstance(r, str) for r in f.get("extract", []))):
                errors.append(f"facts_from[{i}] must be {{tool, args, extract: [regex]}}")
            else:
                import re
                for r in f.get("extract", []):
                    try:
                        re.compile(r)
                    except re.error as exc:
                        errors.append(f"facts_from[{i}] bad regex {r!r}: {exc}")
        if out["clock"] and not _clock_ok(out["clock"]):
            errors.append("clock must be empty, HH:MM or +Nh / +Nm")
        if check_fixture and out["fixture"] and not (FIXTURES / out["fixture"]).is_dir():
            errors.append(f"fixture '{out['fixture']}' not found in {FIXTURES}")
    if errors:
        raise ScenarioError(f"{where}: " + "; ".join(errors))
    return out


def _clock_ok(spec: str) -> bool:
    import re
    return bool(re.fullmatch(r"\+\d+[hm]|\d{1,2}:\d{2}", spec))


def load(path: Path, check_fixture: bool = True) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScenarioError(f"{path}: {exc}") from exc
    return validate(data, str(path), check_fixture)


def load_all(directory: Path = SCENARIOS) -> list[dict]:
    return [load(p) for p in sorted(directory.glob("*.json"))]


if __name__ == "__main__":
    paths = [Path(a) for a in sys.argv[1:]] or sorted(SCENARIOS.glob("*.json"))
    bad = 0
    for p in paths:
        try:
            s = load(p, check_fixture=not p.name.endswith(".example.json"))
            print(f"ok   {p.name}: {s['id']} ({s['fixture']}, {len(s['turns'])} turn(s))")
        except ScenarioError as exc:
            bad += 1
            print(f"FAIL {exc}")
    sys.exit(1 if bad else 0)
