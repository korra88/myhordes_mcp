"""Automatic town log: the deterministic part of /inspect-town and /close-day.

On every live fetch of the current day (client._load) the server keeps
towns/<folder>/daily-log.md and day-NN.md up to date:
  - closes past days (Night outcome block + daily-log row) from Fata data only,
  - opens the current day (day file + daily-log row),
  - appends a "Check" entry when the state changed, at most every TOWN_LOG_INTERVAL min
    (a change is logged by the first fetch after the interval, even if nothing changed since).
Formats follow .claude/commands/close-day.md and inspect-town.md. Off with TOWN_LOG_AUTO=0.
Every write checks first, so a second run (or a second server process) adds nothing.
"""

import fcntl
import logging
import re
import time
from datetime import timedelta
from pathlib import Path

from ..utils import clock
from ..utils.fmt import est_status, estimate, plural
from ..utils.config import PROJECT_ROOT, TOWN_LOG_AUTO, TOWN_LOG_INTERVAL
from . import archive
from .night import night_report

log = logging.getLogger(__name__)

TEMPLATES = PROJECT_ROOT / "templates" / "town"
TABLE_HEADER = "| Day | Alive | Defense | Attack est. | Outcome |\n|---|---|---|---|---|"
MARKER = "_townlog_marker.json"
NO_CHANGES = "No changes since the reference snapshot."


def update_town_log(town_id: int, result: dict, load_day) -> list[str]:
    """Update the town's log files; returns note fragments for the model (empty = nothing done).

    load_day(day) -> parsed result of a past day from disk only, or None."""
    if not TOWN_LOG_AUTO:
        return []
    tdir = archive.town_dir(town_id)
    day = result["meta"].get("day")
    if tdir is None or not day:
        return []
    cache = archive.cache_path(tdir)
    cache.mkdir(parents=True, exist_ok=True)
    with open(cache / ".townlog.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # other server processes may run at once
        try:
            _ensure_templates(tdir, town_id, result)
            notes = _close_past_days(tdir, day, result, load_day)
            notes += _open_day(tdir, day, result)
            notes += _check_entry(tdir, town_id, day, result)
            return notes
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# a. Templates and daily-log table
# ---------------------------------------------------------------------------

def _season(tdir: Path) -> str:
    season = (archive.read_meta(tdir) or {}).get("season")
    if season:
        return str(season)
    m = re.match(r"s(\d+)-", tdir.name)
    return m.group(1) if m else "?"


def _ensure_templates(tdir: Path, town_id: int, result: dict) -> None:
    name, season = result["meta"].get("town_name") or "Unknown", _season(tdir)
    for fname in ("daily-log.md", "notes.md"):
        target = tdir / fname
        if not target.exists():
            text = (TEMPLATES / fname).read_text(encoding="utf-8")
            text = text.replace("{Town Name}", name).replace("{season}", season).replace("{town_id}", str(town_id))
            target.write_text(text, encoding="utf-8")
    dl = tdir / "daily-log.md"
    text = dl.read_text(encoding="utf-8")
    if "| Day |" not in text:  # old free-form log: add the table below it
        dl.write_text(text.rstrip("\n") + "\n\n" + TABLE_HEADER + "\n", encoding="utf-8")


def _row_day(line: str) -> int | None:
    m = re.match(r"\|\s*(\d+)\s*\|", line)
    return int(m.group(1)) if m else None


def _set_row(tdir: Path, day: int, cells: list[str], *, overwrite_tbd: bool) -> None:
    """Insert the row of `day` in daily-log.md. If it exists, replace it only when
    overwrite_tbd and its outcome is still TBD (never touch a hand-written row)."""
    path = tdir / "daily-log.md"
    lines = path.read_text(encoding="utf-8").split("\n")
    new = f"| {day} | " + " | ".join(cells) + " |"
    for i, line in enumerate(lines):
        if _row_day(line) == day:
            if overwrite_tbd and line.rstrip().endswith("| TBD |"):
                lines[i] = new
                path.write_text("\n".join(lines), encoding="utf-8")
            return
    at = next((i for i, l in enumerate(lines) if l.startswith("|---")), None)
    if at is None:
        return
    pos = at + 1
    while pos < len(lines) and lines[pos].startswith("|"):
        if (_row_day(lines[pos]) or 0) > day:
            break
        pos += 1
    lines.insert(pos, new)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# b. Close past days
# ---------------------------------------------------------------------------

def _logged_days(tdir: Path) -> list[int]:
    days = [int(m.group(1)) for f in tdir.glob("day-*.md") if (m := re.fullmatch(r"day-(\d+)\.md", f.name))]
    days += [d for l in (tdir / "daily-log.md").read_text(encoding="utf-8").split("\n") if (d := _row_day(l))]
    return days


def _date_of(day: int, current: int):
    return (clock.now() - timedelta(days=current - day)).date()


def _fmt(v) -> str:
    return "?" if v is None else str(v)


def _close_past_days(tdir: Path, current: int, result: dict, load_day) -> list[str]:
    if current <= 1:
        return []
    known = _logged_days(tdir)
    first = max(1, min(known)) if known else current - 1
    notes = []
    for d in range(first, current):
        f = tdir / f"day-{d:02d}.md"
        if f.exists() and "### Night outcome" in f.read_text(encoding="utf-8"):
            continue
        notes.append(_close_day(tdir, f, d, current, result, load_day(d)))
    return notes


def _close_day(tdir: Path, f: Path, d: int, current: int, result: dict, day_data: dict | None) -> str:
    r = night_report(result, d, gh=None, day_data=day_data)
    after, before = r["alive_after"], r["alive_before"]
    deaths = r["deaths"]
    if after == 0:
        outcome, res = "FAILED", "FAILED"
    elif after is None:
        outcome, res = "?", "UNKNOWN"
    else:
        outcome = "Survived" + (" · " + ", ".join(f"{x['name']} †" for x in deaths) if deaths else "")
        res = "SURVIVED"

    if not f.exists():
        f.write_text(f"# Day {d} — {_date_of(d, current)}\n\n"
                     f"*No intra-day snapshots were taken on day {d}; this file holds the night outcome only.*\n",
                     encoding="utf-8")

    d0, d1 = _date_of(d, current), _date_of(d + 1, current)
    span = f"{d0:%b} {d0.day} → {d1.day if d1.month == d0.month else f'{d1:%b} {d1.day}'}"
    est = r["estimate"]
    est_txt = f" (estimate {est[0]}–{est[1]})" if est else ""
    after_txt = _fmt(after) + (f" ({_fmt(before)} − {plural(len(deaths), 'death')})"
                               if before is not None and after is not None else "")
    block = ["", "---", "", f"### Night outcome — {span}", f"**Result: {res}**",
             f"**Defense:** {_fmt(r['defense'])} vs **{_fmt(r['attack'])}** zombies{est_txt}",
             f"**Alive after:** {after_txt}", "", "#### Deaths"]
    if deaths:
        block += ["| Citizen | Last position | Cause |", "|---|---|---|"]
        for x in deaths:
            pos = "IN TOWN" if not x["outside"] else x["last_coords"].replace("|", "\\|")
            block.append(f"| **{x['name']}** | {pos} | {x['cause']} |")
    else:
        block.append("*(No deaths — all survived the night.)*")
    with open(f, "a", encoding="utf-8") as fh:
        fh.write("\n".join(block) + "\n")

    if est:
        att = (estimate(est[0], est[1], unit="") + f" (attack {r['attack']})" if r["attack"] is not None
               else estimate(est[0], est[1], est_status(est[2]), unit=""))
    else:
        att = f"? (attack {r['attack']})" if r["attack"] is not None else "?"
    _set_row(tdir, d, [f"{_fmt(before)} → {_fmt(after)}", _fmt(r["defense"]), att, outcome], overwrite_tbd=True)
    verdict = {"SURVIVED": f"survived, {plural(len(deaths), 'death')}",
               "FAILED": "FAILED", "UNKNOWN": "outcome unknown"}[res]
    return f"closed day {d} ({verdict})"


# ---------------------------------------------------------------------------
# c. Open the current day
# ---------------------------------------------------------------------------

def _open_day(tdir: Path, day: int, result: dict) -> list[str]:
    notes = []
    f = tdir / f"day-{day:02d}.md"
    if not f.exists():
        f.write_text(f"# Day {day} — {clock.now().date()}\n", encoding="utf-8")
        notes.append(f"opened {f.name}")
    citizens = result["citizens"]
    inside = sum(1 for c in citizens if c["inside_town"])
    est = result["estimations"].get("today", {})
    est_txt = ("?" if est.get("min") is None
               else estimate(est["min"], est["max"], est_status(est.get("maxed")), unit=""))
    _set_row(tdir, day, [f"{len(citizens)} ({inside} in / {len(citizens) - inside} out)",
                         _fmt(result["defense"].get("total")), est_txt, "TBD"], overwrite_tbd=False)
    return notes


# ---------------------------------------------------------------------------
# d. Check entry
# ---------------------------------------------------------------------------

def _has_warnings(lines: list[str]) -> bool:
    """Anything in a changes body that is not header, section title or AP list."""
    in_ap = False
    for l in lines:
        if not l.strip():
            in_ap = False
        elif l.startswith("### AP spent"):
            in_ap = True
        elif in_ap or l.startswith(("State:", "Compared", "No changes", "### ")):
            continue
        else:
            return True
    return False


def _check_entry(tdir: Path, town_id: int, day: int, result: dict) -> list[str]:
    from .changes import format_town_changes  # lazy: changes imports client

    snaps = archive.load_snapshots(town_id, day)
    if not snaps:
        return []
    latest = snaps[-1]
    marker = archive.get_marker(tdir, MARKER)
    if marker and marker.get("day") == day:
        # Checked on every fetch, not only when a snapshot is saved: the last changes
        # before a quiet spell are logged by the next fetch once the interval is over.
        if latest["taken_at"] <= marker["taken_at"] or time.time() - marker["taken_at"] < TOWN_LOG_INTERVAL * 60:
            return []
        ref = next((s for s in reversed(snaps) if s["taken_at"] <= marker["taken_at"]), snaps[0])
        label = "previous log check"
    else:
        ref, label = snaps[0], "first snapshot of the day"

    body = format_town_changes(result, snaps, ref, label).split("\n")[2:]  # drop title + data updated
    if NO_CHANGES in body and not _has_warnings(body):
        return []
    body = [("#### " + l[4:]) if l.startswith("### ") else l for l in body]
    hhmm = clock.fmt_epoch(latest["taken_at"])
    title = f"Check ({hhmm} CET)"
    f = tdir / f"day-{day:02d}.md"
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(f"\n### {title}\n" + "\n".join(body).strip("\n") + "\n")
    archive.set_marker(tdir, MARKER, day, latest["taken_at"])
    try:
        rel = f.relative_to(PROJECT_ROOT)
    except ValueError:
        rel = f
    return [f'check {hhmm} logged → {rel} § "{title}"']
