"""Gest'Hordes REST API client — town statistics endpoint.

Fetches per-day attack/defense statistics for a town, including:
- Theoretical min/max attack curve (atk_min_theo / atk_max_theo)
- Per-day actual attack and Gest'Hordes estimates
- Defense totals and per-source breakdown
- Actual deaths per night (morts_reels)

No authentication required. The stats endpoint is public.
URL: https://gesthordes.fr/rest/v1/stats/{map_id}
"""

import time

import httpx

GESTHORDES_STATS_URL = "https://gesthordes.fr/rest/v1/stats/{map_id}"

_cache: dict[int, tuple[float, dict]] = {}
CACHE_TTL = 120  # seconds — stats change infrequently during the day


async def fetch_stats(map_id: int) -> dict:
    """Fetch town statistics from Gest'Hordes.

    Returns the raw parsed JSON response dict, or a dict with an 'error' key.
    Results are cached for 2 minutes.
    """
    now = time.monotonic()
    if map_id in _cache:
        cached_at, data = _cache[map_id]
        if now - cached_at < CACHE_TTL:
            return data

    url = GESTHORDES_STATS_URL.format(map_id=map_id)
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                url,
                headers={
                    "accept": "application/json",
                    "gh-mapid": str(map_id),
                    "user-agent": "MyHordes-MCP-Advisor/1.0",
                },
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return {"error": f"Gest'Hordes returned HTTP {e.response.status_code}"}
    except httpx.RequestError as e:
        return {"error": f"Could not reach Gest'Hordes: {e}"}

    try:
        data = resp.json()
    except Exception:
        return {"error": "Could not parse Gest'Hordes response as JSON"}

    if not data.get("success"):
        return {"error": "Gest'Hordes API returned success=false"}

    _cache[map_id] = (now, data)
    return data


def format_attack_forecast(data: dict) -> str:
    """Format attack forecast and defence history from Gest'Hordes stats."""
    if "error" in data:
        return f"Error fetching Gest'Hordes stats: {data['error']}"

    stats = data.get("data", {}).get("stats", {})
    general = data.get("data", {}).get("general", {})
    ville = general.get("ville", {})

    current_day = stats.get("current_ville_jour", 0)
    max_day = stats.get("max_jour", 35)
    town_name = ville.get("nom", "Unknown town")
    season = ville.get("saison", "?")

    atk_min = stats.get("atk", {}).get("atk_min_theo", [])
    atk_max = stats.get("atk", {}).get("atk_max_theo", [])
    atk_actual = stats.get("atk", {}).get("attaque_jour", [])
    def_actual = stats.get("atk", {}).get("def", [])
    est_min = stats.get("atk", {}).get("min_estim", [])
    est_max = stats.get("atk", {}).get("max_estim", [])
    deaths = stats.get("atk", {}).get("morts_reels", [])

    def _val(lst, idx):
        """Safe list access — returns None if out of bounds or None element."""
        if idx < len(lst) and lst[idx] is not None:
            return lst[idx]
        return None

    lines = [
        f"## Attack Forecast — {town_name} (Season {season}, Day {current_day})",
        "",
        f"Data source: Gest'Hordes  |  Map ID: {ville.get('map_id', '?')}  |  Max day: {max_day}",
        "",
    ]

    # --- Tonight and next few days ---
    lines.append("### Theoretical Attack Range (Gest'Hordes model)")
    lines.append("")
    lines.append(f"{'Day':<5} {'Min':>7} {'Max':>7}  {'Actual':>8}  {'GH Est Min':>10}  {'GH Est Max':>10}  {'Def':>7}  Deaths")
    lines.append("-" * 70)

    # Show history + lookahead (up to day+5 or max_day)
    show_from = max(1, current_day - 3)
    show_to = min(max_day, current_day + 5)

    for d in range(show_from, show_to + 1):
        t_min = _val(atk_min, d)
        t_max = _val(atk_max, d)
        actual = _val(atk_actual, d)
        gh_min = _val(est_min, d)
        gh_max = _val(est_max, d)
        defence = _val(def_actual, d)
        died = _val(deaths, d)

        marker = " ◄ tonight" if d == current_day else ""

        lines.append(
            f"D{d:<4} "
            f"{(str(t_min) if t_min is not None else '—'):>7} "
            f"{(str(t_max) if t_max is not None else '—'):>7}  "
            f"{(str(actual) if actual is not None else '—'):>8}  "
            f"{(str(gh_min) if gh_min is not None else '—'):>10}  "
            f"{(str(gh_max) if gh_max is not None else '—'):>10}  "
            f"{(str(defence) if defence is not None else '—'):>7}  "
            f"{(str(died) if died is not None else '—')}"
            f"{marker}"
        )

    lines.append("")

    # --- Tonight's key numbers highlighted ---
    t_min_now = _val(atk_min, current_day)
    t_max_now = _val(atk_max, current_day)
    gh_min_now = _val(est_min, current_day)
    gh_max_now = _val(est_max, current_day)

    lines.append("### Tonight's numbers")
    if t_min_now is not None and t_max_now is not None:
        lines.append(f"- Theoretical range: **{t_min_now}** – **{t_max_now}** zombies")
    else:
        lines.append("- Theoretical range: not available")

    if gh_min_now is not None and gh_max_now is not None:
        lines.append(f"- Gest'Hordes estimate: {gh_min_now} – {gh_max_now} zombies")
    else:
        lines.append("- Gest'Hordes estimate: not yet available (players haven't reported)")

    lines.append("")

    # --- Defence history summary ---
    def_total = stats.get("def", {})
    def_days = def_total.get("day", [])
    def_totals = def_total.get("total", [])
    def_buildings = def_total.get("chantiers_up_chantier_ame", [])
    def_items = def_total.get("objet_def", [])
    def_homes = def_total.get("maison_citizen", [])
    def_guardians = def_total.get("gardiens", [])
    def_watchers = def_total.get("veilleurs", [])

    if def_days and any(v is not None for v in def_totals):
        lines.append("### Defence Breakdown History")
        lines.append("")
        lines.append(f"{'Day':<5} {'Total':>7}  {'Buildings':>10}  {'Items':>6}  {'Homes':>6}  {'Guards':>7}  {'Watch':>6}")
        lines.append("-" * 60)
        for i, d in enumerate(def_days):
            if i >= len(def_totals) or def_totals[i] is None:
                continue
            lines.append(
                f"D{d:<4} "
                f"{str(def_totals[i]):>7}  "
                f"{str(def_buildings[i] if i < len(def_buildings) and def_buildings[i] is not None else '—'):>10}  "
                f"{str(def_items[i] if i < len(def_items) and def_items[i] is not None else '—'):>6}  "
                f"{str(def_homes[i] if i < len(def_homes) and def_homes[i] is not None else '—'):>6}  "
                f"{str(def_guardians[i] if i < len(def_guardians) and def_guardians[i] is not None else '—'):>7}  "
                f"{str(def_watchers[i] if i < len(def_watchers) and def_watchers[i] is not None else '—'):>6}"
            )
        lines.append("")

    lines.append("_Source: Gest'Hordes community stats. Theoretical ranges use the standard MyHordes attack formula. Actual counts are crowd-reported._")

    return "\n".join(lines)
