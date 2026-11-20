"""Offline harness shared by the golden tests and the bot evaluation server.

`offline(...)` copies a fixture folder to a temporary towns/, serves every Fata and
Gest'Hordes request from the frozen files, freezes the clock and points the config at the
temporary copy, all BEFORE `main` is imported. No network, and the real towns/ is checked
to be untouched on exit. The patches are process-wide and not undone: use one run per process.

    with offline(FIXTURES, TOWNS, main_town=8299) as run:
        run.main            # the imported main module (tools, mcp)
        run.towns_dir       # temporary towns/, writable
        run.now["t"] = ...  # move the frozen clock (datetime)
        run.day0            # the initial frozen time (data time + 10 min)
"""

import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fixture_raw(towns_dir: Path, towns: list[tuple[str, int]], town: int, day: int | None) -> dict | None:
    """Raw /towndata JSON of (town, day) from the towns/ copy; day None = the current day.
    towns: [(folder under towns/, town id)]. None when there is no such fixture."""
    for folder, tid in towns:
        if tid != town:
            continue
        cache = towns_dir / folder / "cache"
        if day is None:
            day = json.loads((cache / "_meta.json").read_text())["current_day"]
        for name in (f"day-{day:02d}.towndata.json.gz", f"day-{day:02d}.towndata.live.json.gz"):
            if (cache / name).exists():
                return json.loads(gzip.decompress((cache / name).read_bytes()))
    return None


def install_fakes(towns_dir: Path, towns: list[tuple[str, int]], gesthordes: Path | None, gesthordes_town: int) -> None:
    """Serve every httpx GET from fixtures: Fata from the towns/ copy, Gest'Hordes from the
    `gesthordes` file (for gesthordes_town only, others get a 404), anything else fails."""
    import httpx

    class FakeResponse:
        def __init__(self, url: str, status: int, body: str):
            self.status_code, self.text = status, body
            self.request = httpx.Request("GET", url)

        def json(self):
            return json.loads(self.text)

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("fixture", request=self.request, response=self)

    async def fake_get(self, url, params=None, **kw):
        if "fatamorgana" in str(url):
            raw = fixture_raw(towns_dir, towns, int(params["town"]), params.get("day"))
            return FakeResponse(url, 200, json.dumps(raw)) if raw else FakeResponse(url, 404, "")
        if "gesthordes" in str(url):
            ok = str(url).rstrip("/").endswith(f"/{gesthordes_town}") and gesthordes and gesthordes.exists()
            return FakeResponse(url, 200, gesthordes.read_text()) if ok else FakeResponse(url, 404, "")
        raise httpx.ConnectError(f"offline test: {url}")

    httpx.AsyncClient.get = fake_get


def frozen_now(towns_dir: Path, towns: list[tuple[str, int]], main_town: int, after: timedelta) -> datetime:
    """The main town's current data time + `after`. Imports the fata package: call after the patches."""
    from myhordes_mcp.fata.towndata import _game_time
    from myhordes_mcp.utils.clock import data_datetime
    raw = fixture_raw(towns_dir, towns, main_town, None)
    dt = data_datetime({"data_time": _game_time(raw["town_info"].get("last_game_update"))})
    return dt + after


def tree(root: Path) -> dict[str, tuple[int, int]]:
    """{relative path: (size, mtime_ns)} of every file under root, except .git/ (an editor's
    git integration refreshes the index during a run: not a write by the server)."""
    return {str(f.relative_to(root)): (f.stat().st_size, f.stat().st_mtime_ns)
            for f in root.rglob("*") if f.is_file() and f.relative_to(root).parts[0] != ".git"}


def manifest(towns_dir: Path) -> str:
    """Every file the run left in the temporary towns/: path and a hash of its content
    (decompressed for .gz), so a refactoring of archive/cp/snapshot/townlog writes is checked."""
    lines = []
    for f in sorted(p for p in towns_dir.rglob("*") if p.is_file()):
        data = f.read_bytes()
        if f.suffix == ".gz":
            data = gzip.decompress(data)
        lines.append(f"{f.relative_to(towns_dir)}  {hashlib.sha1(data).hexdigest()[:12]}")
    return "\n".join(lines)


class Run:
    """State of one offline run (see the module docstring)."""
    tmp: Path
    towns_dir: Path
    main: object
    now: dict
    day0: datetime


@contextmanager
def offline(fixtures: Path, towns: list[tuple[str, int]], main_town: int, *,
            gesthordes_town: int | None = None, clock_after: timedelta = timedelta(minutes=10),
            prefix: str = "offline-"):
    """Set up the offline process (see the module docstring). fixtures: folder with `towns/`
    and optionally `gesthordes.json`; towns: [(folder, id)] in it; main_town: the one the
    clock follows; gesthordes_town defaults to main_town. Exits the process if a module
    still sees the real towns/ or clock, or if the real towns/ changed during the run."""
    if not (fixtures / "towns").is_dir():
        sys.exit(f"No fixtures in {fixtures} (golden: run with --freeze first).")
    real_towns = ROOT / "towns"
    before = tree(real_towns) if real_towns.is_dir() else {}
    run = Run()
    run.tmp = Path(tempfile.mkdtemp(prefix=prefix))
    run.towns_dir = towns_dir = run.tmp / "towns"
    shutil.copytree(fixtures / "towns", towns_dir)
    os.environ["TOWN_LOG_AUTO"] = "0"
    os.environ["FATA_CACHE_TTL"] = "0"
    os.environ.pop("LISTENER_USER_ID", None)
    os.environ["USAGE_STATS_DB"] = "off"   # the fake Fata calls must not write the real stats file
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    install_fakes(towns_dir, towns, fixtures / "gesthordes.json", gesthordes_town or main_town)

    # Patch config and the clock BEFORE anything else imports them, so every module (also
    # one added later with `from ..utils.config import TOWNS_DIR`) gets the temporary paths.
    from myhordes_mcp.utils import clock, config
    real_now = clock.now
    config.TOWNS_DIR = towns_dir
    config.CURRENT_TOWN_FILE = towns_dir / "_current_town"
    config.USER_TOWNS_DIR = towns_dir / "_user_towns"
    config.FATAMORGANA_TOWN_ID = None
    config.TOWN_LOG_AUTO = 0
    run.now = now = {}
    clock.now = lambda: now["t"]
    time.time = lambda: now["t"].timestamp()
    now["t"] = run.day0 = frozen_now(towns_dir, towns, main_town, clock_after)

    import main
    run.main = main
    mods = [m for m in list(sys.modules.values()) if getattr(m, "__name__", "").startswith(("myhordes_mcp", "main"))]
    leaked = [f"{m.__name__}.{k}" for m in mods for k, v in vars(m).items()
              if isinstance(v, Path) and v == real_towns]
    leaked += [f"{m.__name__}.{k}" for m in mods for k, v in vars(m).items() if v is real_now]
    if leaked:
        sys.exit(f"Not patched (real towns/ or real clock): {', '.join(leaked)}")
    try:
        yield run
    finally:
        # Checked also when the run failed: a write to the real towns/ outranks the error.
        shutil.rmtree(run.tmp, ignore_errors=True)
        after = tree(real_towns) if real_towns.is_dir() else {}
        if after != before:
            changed = sorted(set(after.items()) ^ set(before.items()))
            sys.exit(f"The run changed the real towns/ (must never happen): {changed[:5]}")
