"""Zone coordinates: parsing, formatting, distances, neighbours, the zone map."""

import re
from typing import NamedTuple

Cell = tuple[int, int]

_COORDS = re.compile(r"\[(-?\d+)\|(-?\d+)\]")

# The 8 zones around one (zombie spread) and the 4 a citizen can step to.
NEIGHBOURS8 = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)
NEIGHBOURS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Bounds(NamedTuple):
    """Edges of the map, inclusive (Fata `meta.map_bounds`)."""
    xmin: int
    xmax: int
    ymin: int
    ymax: int


def in_bounds(bounds: Bounds | tuple, cell: Cell) -> bool:
    return bounds[0] <= cell[0] <= bounds[1] and bounds[2] <= cell[1] <= bounds[3]


def xy(c: str | dict) -> Cell | None:
    """(rx, ry) from a '[rx|ry]' string or from a dict with a "coords" string."""
    s = c if isinstance(c, str) else c.get("coords", "")
    m = _COORDS.match(s)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def fmt_xy(cell: Cell) -> str:
    return f"[{cell[0]}|{cell[1]}]"


def moves(a: Cell, b: Cell = (0, 0)) -> int:
    """Manhattan distance: one AP per move."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def km(x: int, y: int) -> int:
    """The game's zone distance: Euclidean, rounded half up (Zone::getDistance).
    Decides EP use (>= 3 km) and the Observation Platform teleport range."""
    return int((x * x + y * y) ** 0.5 + 0.5)


def zone_map(data: dict, *, scout: bool = False) -> dict[Cell, dict]:
    """Zones by cell. scout=True: scout radar readings (`data["scout"]`) fill the cells the
    map data lacks, as bare zones (zombies and scouted_day only)."""
    zmap: dict[Cell, dict] = {}
    for z in data.get("zones", []):
        if c := xy(z):
            zmap[c] = z
    if scout:
        mapped = set(zmap)
        for z in data.get("scout", []):
            c = xy(z)
            if c and c not in mapped:
                zmap[c] = {"coords": z["coords"], "zombies": z["zombies"], "danger": 0,
                           "items": [], "ruin": None, "scouted_day": z.get("scouted_day")}
    return zmap
