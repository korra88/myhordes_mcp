"""Gest'Hordes formatters: attack forecast/distribution, defence and season-point extraction."""


def extract_season_points(data: dict) -> int | None:
    """Extract the current season point total from Gest'Hordes stats."""
    try:
        return data["data"]["general"]["ville"]["nombre_point_saison"]
    except (KeyError, TypeError):
        return None


def extract_current_defense(data: dict) -> dict | None:
    """Extract current-day Gest'Hordes defence breakdown as a flat dict.

    Returns keys: watchers, temporary, dead_bonus (all int), or None on failure.
    These are sources that Fata Morgana doesn't break out individually.
    """
    if "error" in data:
        return None
    stats = data.get("data", {}).get("stats", {})
    current_day = stats.get("current_ville_jour")
    if current_day is None:
        return None

    def_block = stats.get("def", {})
    days = def_block.get("day", [])
    if current_day not in days:
        return None
    i = days.index(current_day)

    def _get(lst):
        v = lst[i] if i < len(lst) else None
        return v if v is not None else 0

    return {
        "watchers": _get(def_block.get("veilleurs", [])),
        "temporary": _get(def_block.get("tempos", [])),
        "dead_bonus": _get(def_block.get("morts", [])),
    }


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
        died = _val(deaths, d - 1)  # morts_reels is 0-based (day 1 at index 0)

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


def format_attack_distribution(data: dict) -> str:
    """Format per-day attack distribution statistics from historical town data.

    Uses atk.atk — a list-of-lists of real attack values sampled across all towns
    per day — to compute median, 25th/75th percentiles, min, max, and sample count.
    """
    if "error" in data:
        return f"Error fetching Gest'Hordes stats: {data['error']}"

    stats = data.get("data", {}).get("stats", {})
    general = data.get("data", {}).get("general", {})
    ville = general.get("ville", {})

    current_day = stats.get("current_ville_jour", 0)
    town_name = ville.get("nom", "Unknown town")
    season = ville.get("saison", "?")

    atk_samples = stats.get("atk", {}).get("atk", [])
    atk_min_theo = stats.get("atk", {}).get("atk_min_theo", [])
    atk_max_theo = stats.get("atk", {}).get("atk_max_theo", [])

    def _percentile(sorted_vals, pct):
        if not sorted_vals:
            return None
        idx = (len(sorted_vals) - 1) * pct / 100
        lo, hi = int(idx), min(int(idx) + 1, len(sorted_vals) - 1)
        return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo))

    lines = [
        f"## Attack Distribution — {town_name} (Season {season}, Day {current_day})",
        "",
        "Historical attack values sampled across all towns at each day level.",
        "Percentiles show where most towns actually land within the theoretical range.",
        "",
        f"{'Day':<5} {'n':>5}  {'Min':>6}  {'p25':>6}  {'Median':>7}  {'p75':>6}  {'Max':>6}  {'Theo Min':>9}  {'Theo Max':>9}",
        "-" * 72,
    ]

    # Show all days with data, up to current_day + 3 lookahead (theo only)
    max_day = max(len(atk_samples) - 1, len(atk_min_theo) - 1)
    show_to = min(max_day, current_day + 3)
    show_from = max(1, current_day - 5)

    for d in range(show_from, show_to + 1):
        t_min = atk_min_theo[d] if d < len(atk_min_theo) else None
        t_max = atk_max_theo[d] if d < len(atk_max_theo) else None

        samples = atk_samples[d] if d < len(atk_samples) else []
        samples = [v for v in samples if v is not None]

        if samples:
            s = sorted(samples)
            n = len(s)
            p25 = _percentile(s, 25)
            med = _percentile(s, 50)
            p75 = _percentile(s, 75)
            marker = " ◄" if d == current_day else ""
            lines.append(
                f"D{d:<4} {n:>5}  "
                f"{s[0]:>6}  {p25:>6}  {med:>7}  {p75:>6}  {s[-1]:>6}  "
                f"{(str(t_min) if t_min is not None else '—'):>9}  "
                f"{(str(t_max) if t_max is not None else '—'):>9}"
                f"{marker}"
            )
        elif t_min is not None:
            # Future days — theo range only, no samples yet
            lines.append(
                f"D{d:<4} {'—':>5}  {'—':>6}  {'—':>6}  {'—':>7}  {'—':>6}  {'—':>6}  "
                f"{t_min:>9}  {t_max:>9}"
            )

    lines += [
        "",
        "### How to read this",
        "- **n**: number of real-game attack values at this day level (larger = more reliable)",
        "- **p25/p75**: 25th and 75th percentile — the middle 50% of towns fall in this band",
        "- **Median**: half of all towns faced more than this, half faced less",
        "- **Theo Min/Max**: the game formula's theoretical floor and ceiling",
        "",
        "_Source: Gest'Hordes aggregated town data. Sample size grows as the season progresses._",
    ]

    return "\n".join(lines)
