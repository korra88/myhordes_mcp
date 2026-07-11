import os
import sys
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
import knowledge
from sources import fatamorgana, gesthordes, discord as discord_source

# IMPORTANT: MyHordes rules prohibit automated/scheduled API polling.
# All API calls must be triggered by explicit user queries via MCP tools.
# Never add cron jobs, background refresh, or periodic data fetching.
# See: docs/game-rules-for-external-apps.md

# Load environment variables from .env file
load_dotenv()

# Initialize the MCP Server
mcp = FastMCP("MyHordes Advisor")

# Fetch API credentials from the environment
# userkey: the player's External ID (identifies whose data to fetch)
# appkey: the registered app secret (identifies this application)
MYHORDES_USER_KEY = os.getenv("MYHORDES_USER_KEY")
MYHORDES_APP_KEY = os.getenv("MYHORDES_APP_KEY")

FATAMORGANA_TOWN_ID = os.getenv("FATAMORGANA_TOWN_ID")
FATAMORGANA_TOKEN = os.getenv("FATAMORGANA_TOKEN")

if not MYHORDES_USER_KEY:
    print("Warning: MYHORDES_USER_KEY not found in environment variables.", file=sys.stderr, flush=True)
if not MYHORDES_APP_KEY:
    print("Warning: MYHORDES_APP_KEY not found in environment variables.", file=sys.stderr, flush=True)
if not FATAMORGANA_TOWN_ID:
    print("Warning: FATAMORGANA_TOWN_ID not found in environment variables.", file=sys.stderr, flush=True)


def _check_auth() -> str | None:
    """Return an error message if official API credentials are missing, None if OK."""
    missing = []
    if not MYHORDES_USER_KEY:
        missing.append("MYHORDES_USER_KEY")
    if not MYHORDES_APP_KEY:
        missing.append("MYHORDES_APP_KEY")
    if missing:
        return f"Authentication Error: {', '.join(missing)} not configured. See .env.example."
    return None


def _resolve_town_id(town_id: int = 0) -> int | str:
    """Return a valid town ID (int) or an error message (str).

    If town_id is provided and non-zero, use it directly.
    Otherwise fall back to the FATAMORGANA_TOWN_ID env var.
    """
    if town_id:
        return int(town_id)
    if FATAMORGANA_TOWN_ID:
        return int(FATAMORGANA_TOWN_ID)
    return "Error: No town ID provided and FATAMORGANA_TOWN_ID not configured in .env."


@mcp.tool()
async def get_bank_inventory(day: int = 0, town_id: int = 0, detail: str = "summary") -> str:
    """
    Fetches the current bank inventory of the MyHordes town.
    The default 'summary' is the right choice for almost every question —
    "do we have water/food/weapons?", "what's in the bank?", build planning.
    It groups items by strategic priority (water, food by AP, drugs, defense
    items, key resources, weapons) with totals per group.
    Use detail='full' ONLY when the user explicitly asks for the complete
    raw item list — it is very long and rarely needed.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
        detail: 'summary' (default, almost always correct) or 'full'
                (complete item list — only on explicit user request).
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)
    if detail == "full":
        return fatamorgana.format_bank(data)
    return fatamorgana.format_bank_summary(data)


# ---------------------------------------------------------------------------
# Fata Morgana tools — live town data from community-maintained spy service
# ---------------------------------------------------------------------------

@mcp.tool()
async def refresh_fata_data(token: str = "") -> str:
    """
    Triggers a live data refresh in Fata Morgana by calling the game API on your behalf.
    Refreshes: bank inventory, building status, citizen positions, zombie attack estimate.
    After this call, re-fetch any tool (get_bank_inventory, get_buildings, etc.) to see
    updated data.

    Requires a Fata Morgana auth token — a JWT from fatamorgana.md26.eu encoding your
    player key and town ID. Get it from browser DevTools (Application → Cookies →
    fatamorgana.md26.eu → auth_token) while logged in. Store it as FATAMORGANA_TOKEN
    in .env to avoid passing it each time.

    Can only be called while in-town (game enforces this).

    Args:
        token: Fata Morgana JWT auth token. Leave empty to use FATAMORGANA_TOKEN from .env.
    """
    t = token.strip() or FATAMORGANA_TOKEN
    if not t:
        return (
            "Error: No token provided. Pass token= or set FATAMORGANA_TOKEN in .env.\n"
            "Get it from browser DevTools: Application → Cookies → fatamorgana.md26.eu → auth_token."
        )
    result = await fatamorgana.trigger_update(t)
    if result["ok"]:
        return result["message"]
    return f"Refresh failed: {result['message']}"


@mcp.tool()
async def get_town_overview(day: int = 0, town_id: int = 0, detail: str = "compact") -> str:
    """
    One-call town status snapshot: day, gate, defense total, attack estimate,
    water supply, citizen positions, deaths count, bank size.
    Use this single tool for "how is the town", "status", "overview" questions —
    the default 'compact' answer is complete for those. Do NOT also call
    get_bank_inventory, get_defense_status or get_citizen_positions unless the
    user asks specifically about bank contents, defense breakdown or deaths.
    Data is crowd-sourced by players and may lag behind real-time game state.

    Args:
        day: Specific day number to inspect (e.g. 5 for day 5). Use 0 or omit for
             the current/latest day. Useful for comparing town progress over time.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
        detail: 'compact' (default, almost always correct) — condensed citizen
                roster, deaths count and bank size only.
                'full' — every citizen on its own line plus the complete bank
                item list and death log; only on explicit user request.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)
    # Enrich with season points from Gest'Hordes (current day only)
    season_points = None
    if not (day and day != data.get("meta", {}).get("day")):
        gh_data = await gesthordes.fetch_stats(tid)
        season_points = gesthordes.extract_season_points(gh_data)
    return fatamorgana.format_town_overview(data, season_points=season_points, detail=detail)


@mcp.tool()
async def get_citizen_positions(day: int = 0, town_id: int = 0) -> str:
    """
    Fetches citizen positions from Fata Morgana — who is inside the town,
    who is outside (and where), and the list of dead citizens with cause of death.
    Use this when the user asks who is outside, who is camping, or about deaths.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)
    return fatamorgana.format_citizens(data)


@mcp.tool()
async def get_defense_status(day: int = 0, town_id: int = 0) -> str:
    """
    Fetches the town defense breakdown and attack estimations from Fata Morgana,
    enriched with Gest'Hordes per-source detail for the current day.
    Includes: total defense, per-source breakdown (wall, buildings, items, guardians,
    homes, watchmen, temporary bonuses, dead-citizen bonus), item multiplier,
    tonight's and tomorrow's zombie estimates, and a survival assessment.
    Use this when the user asks about defense, attack survival, or zombie estimates.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)
    # Enrich current-day defense with Gest'Hordes breakdown (watchmen, temps, dead bonus)
    gh_defense = None
    if not (day and day != data.get("meta", {}).get("day")):
        gh_data = await gesthordes.fetch_stats(tid)
        gh_defense = gesthordes.extract_current_defense(gh_data)
    return fatamorgana.format_defense(data, gh_defense=gh_defense)


@mcp.tool()
async def get_buildings(
    day: int = 0,
    town_id: int = 0,
    mode: str = "summary",
    include_private_town_buildings: bool = False,
    include_resources: bool = False,
) -> str:
    """
    Fetches the town's building list from Fata Morgana.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
        mode: Output mode — one of:
            "summary"   (default) Buildings constructed today only, plus running defense total.
                        Use when asked what was built today or current defense from buildings.
            "history"   All built buildings grouped by construction day.
                        Use when asked what was built on past days or full construction history.
            "available" Buildable unbuilt buildings (unlocked or prereq-only locked).
                        Blueprint-locked buildings are excluded — not actionable without the blueprint.
                        Use when asked what to build next, what's available, or build planning.
        include_private_town_buildings: Include buildings only available in private/custom towns
            (Holy Raincloud, Spirit Mirage, Sword of Bokor, XXL Voodoo Doll). Default False.
        include_resources: Include resource requirements for each building. Only useful with
            mode='available'. Use True for build planning when you need to check bank stock.
            Default False to keep output compact.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)
    return fatamorgana.format_buildings(data, mode=mode, include_private=include_private_town_buildings, include_resources=include_resources)


@mcp.tool()
async def get_scout_map(
    day: int = 0,
    town_id: int = 0,
) -> str:
    """
    Fetches zombie counts per zone from scout data (Fata Morgana).
    Shows which zones have been scouted, how many zombies were spotted,
    and who scouted them. Zones are grouped by threat level.
    Use this when the user asks about zombie positions, safe scavenging routes,
    or where the horde is concentrated.

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)
    return fatamorgana.format_scout(data)


@mcp.tool()
async def find_expedition_path(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    group_cp: int = 2,
    escape_items: int = 0,
    scout_mode: bool = False,
    day: int = 0,
    town_id: int = 0,
) -> str:
    """
    Runs CP-aware Dijkstra pathfinding between two map coordinates.
    Returns up to two paths:
    - Safest path: minimises zombie exposure, avoids traps entirely.
    - Shortest path: minimises AP, using escape items to pass through traps.
    Hard cap: 40 AP.
    Use this when planning an expedition route between two points.

    Args:
        x1: X coordinate of the starting point (town-relative).
        y1: Y coordinate of the starting point.
        x2: X coordinate of the destination.
        y2: Y coordinate of the destination.
        group_cp: Total Control Points of the expedition party. Default 2
                  (solo citizen, no bonuses). Each citizen = 2 CP base; add
                  bonuses for Prepared skill, Car Door, Riot Shield, etc.
                  Zones with zombies >= group_cp are flagged as trap risk.
        escape_items: Number of flash-grenade-equivalent escape items carried.
                      Default 0. Each can neutralize one trapped zone on the
                      shortest path.
        scout_mode: Set True when a Scout with Camouflage Vest is leading.
                    Trapped zones become passable at a detection risk cost
                    instead of being impassable.
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)
    return fatamorgana.find_safe_path(
        data, x1, y1, x2, y2,
        group_cp=group_cp,
        escape_items=escape_items,
        scout_mode=scout_mode,
    )


@mcp.tool()
async def get_zone_details(
    day: int = 0,
    town_id: int = 0,
    x1: int | None = None,
    y1: int | None = None,
    x2: int | None = None,
    y2: int | None = None,
    max_ap: int | None = None,
) -> str:
    """
    Fetches detailed map zone data from Fata Morgana — ruins (with names, dig
    counts, blueprint status), ground items per zone, and zombie counts.
    Use this when the user asks about ruins, what items are on the ground outside,
    or what's available at specific map coordinates.

    Without coordinates: returns only zones that have a ruin or ground items
    (empty zones are omitted, count noted).
    When x1/y1/x2/y2 are provided, restricts output to the bounding box between
    those two coordinates, sorted by AP cost (Manhattan distance from town).
    Zones with nothing to report (no ruin, no items, no threat) are collapsed
    into one-line coordinate lists — the output stays compact for large areas,
    so prefer one call with a generous box over many small calls.
    Use this for expedition planning: "what's between [2|3] and [5|6] within 8 AP?"

    Args:
        day: Specific day number to inspect. Use 0 or omit for the current day.
        town_id: Fata Morgana town/game ID. Omit to use the default from .env.
        x1: X coordinate of the first corner of the area to inspect (town-relative).
        y1: Y coordinate of the first corner of the area to inspect (town-relative).
        x2: X coordinate of the second corner. Required if x1/y1 are set.
        y2: Y coordinate of the second corner. Required if x1/y1 are set.
        max_ap: Optional AP budget to filter results (e.g. 8). Cells beyond this cost
                are shown separately. Typical range: 4–15.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await fatamorgana.fetch_town_data(tid, day=day or None)

    coords_provided = all(v is not None for v in (x1, y1, x2, y2))
    if coords_provided:
        return fatamorgana.format_zone_path(data, x1, y1, x2, y2, max_ap=max_ap)
    return fatamorgana.format_zones(data)


@mcp.tool()
async def get_attack_distribution(town_id: int = 0) -> str:
    """
    Fetches historical attack distribution statistics from Gest'Hordes — real attack
    values sampled across all towns per day, showing median, percentiles (p25/p75),
    min/max, and sample count alongside the theoretical floor and ceiling.
    Use this when the user wants to understand how bad the attack typically gets at
    a given day level, or whether tonight's estimate is unusually high or normal.

    Args:
        town_id: Gest'Hordes map ID. Omit to use the default from .env.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await gesthordes.fetch_stats(tid)
    return gesthordes.format_attack_distribution(data)


@mcp.tool()
async def get_attack_forecast(town_id: int = 0) -> str:
    """
    Fetches the theoretical attack curve and defence history from Gest'Hordes.
    Shows the theoretical min/max zombie attack range for each day of the game,
    actual attack counts from previous nights, Gest'Hordes community estimates,
    and defence totals with per-source breakdown (buildings, items, homes, guardians).
    Use this when the user asks about tonight's expected attack, how the attack
    scales over the game, or wants to compare defence vs. projected zombie counts.

    Args:
        town_id: Gest'Hordes map ID. Omit to use the default from .env.
    """
    tid = _resolve_town_id(town_id)
    if isinstance(tid, str):
        return tid
    data = await gesthordes.fetch_stats(tid)
    return gesthordes.format_attack_forecast(data)


# ---------------------------------------------------------------------------
# Official API tools — requires MYHORDES_APP_KEY (not yet available)
# ---------------------------------------------------------------------------

# TODO: Uncomment once official API app key is obtained and sources/official_api.py
# is implemented. These tools need the official API because Fata Morgana doesn't
# provide construction progress details or last night's attack report.

# @mcp.tool()
# async def get_construction_progress() -> str:
#     """
#     Fetches construction site progress from the official API.
#     Shows buildings currently under construction: AP invested vs. AP needed,
#     resources deposited vs. required, and estimated completion.
#     Use this when the user asks what's closest to being finished,
#     where to spend AP, or what resources are still needed for a build.
#     """
#     if err := _check_auth():
#         return err
#     # return await official_api.get_construction_progress(MYHORDES_USER_KEY, MYHORDES_APP_KEY)

# @mcp.tool()
# async def get_last_night_report() -> str:
#     """
#     Fetches last night's attack gazette from the official API.
#     Includes: zombies killed, defense used, water lost overnight,
#     wind direction (if Search Tower built), and citizen casualties.
#     Use this for post-attack analysis — was defense tight or comfortable,
#     and how should the town adjust today?
#     """
#     if err := _check_auth():
#         return err
#     # return await official_api.get_last_night_report(MYHORDES_USER_KEY, MYHORDES_APP_KEY)


# ---------------------------------------------------------------------------
# Wiki tools (scraped from en.mhwiki.org)
# ---------------------------------------------------------------------------

@mcp.tool()
def search_wiki(query: str, category: str = "", limit: int = 5) -> str:
    """
    Search the MyHordes wiki for game information.
    Use for items, buildings, ruins, skills, statuses, distinctions, jobs, deaths,
    mechanics, and strategy guides sourced from en.mhwiki.org.

    Args:
        query: Search terms (e.g. "Twisted Plank", "camping", "water ration poisoned")
        category: Optional filter — one of: items, buildings, ruins, skills, status,
                  distinctions, deaths, homes, jobs, guide, general, town, events, tutorials.
                  Leave empty to search all categories.
        limit: Max results to return (1-10, default 5). Use 1-2 for specific lookups,
               higher for broad searches.
    """
    if not knowledge.is_loaded():
        return "Error: Wiki not loaded. Run 'make process' to build it."

    limit = max(1, min(10, limit))
    cat = category.strip().lower() or None
    results = knowledge.search(query, category=cat, limit=limit)

    if not results:
        return f"No results found for '{query}'" + (f" in category '{category}'" if category else "") + "."

    parts = [f"Found {len(results)} result(s) for '{query}':\n"]
    for r in results:
        parts.append(f"## {r['name']} [{r['category']}]\n")
        parts.append(r["content"])
        parts.append("\n---\n")

    return "\n".join(parts)


@mcp.tool()
def list_wiki_categories() -> str:
    """
    List all categories in the MyHordes wiki with page counts.
    Use this to discover what wiki information is available before searching.
    """
    if not knowledge.is_loaded():
        return "Error: Wiki not loaded. Run 'make process' to build it."

    cats = knowledge.get_categories()
    lines = ["MyHordes Wiki Categories:\n"]
    total = 0
    for cat, count in cats.items():
        lines.append(f"- {cat}: {count} pages")
        total += count
    lines.append(f"\nTotal: {total} pages")
    lines.append("\nUse search_wiki(query, category='...') to search within a category.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Knowledge tools (curated advisor knowledge base)
# ---------------------------------------------------------------------------

@mcp.tool()
def search_knowledge(query: str, section: str = "") -> str:
    """
    Search the advisor's curated knowledge base for strategy, building guides,
    and tactical notes not found in the wiki. Content lives in knowledge/ dir.

    Use for: building priority by game phase, opti-town tactics, zoo strategy,
    expedition planning, post-mortem analysis.

    Args:
        query: Search terms (e.g. "day 5 buildings", "water defense", "wonders")
        section: Optional subfolder filter. Valid sections:
            "buildings" — AP costs, defense values, build priority by game phase, wonders.
            Leave empty to search all sections.
    """
    import os
    from pathlib import Path

    kb_dir = Path(__file__).parent / "knowledge"
    if section:
        kb_dir = kb_dir / section

    if not kb_dir.exists():
        return f"Knowledge section '{section}' not found." if section else "Knowledge base not found."

    results = []
    query_lower = query.lower()

    for md_file in sorted(kb_dir.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        if query_lower in content.lower():
            rel = md_file.relative_to(Path(__file__).parent / "knowledge")
            results.append((str(rel), content))

    if not results:
        return f"No knowledge entries found for '{query}'" + (f" in section '{section}'" if section else "") + "."

    parts = [f"Found {len(results)} file(s) matching '{query}':\n"]
    for name, content in results:
        parts.append(f"## {name}\n")
        parts.append(content)
        parts.append("\n---\n")
    return "\n".join(parts)


DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "CHANNEL_ID")


@mcp.tool()
def get_mentions(after_id: str = "") -> str:
    """Get unread Discord messages that mention the Town Elder bot.

    Returns only messages containing the bot mention, newest-last.
    Filters out messages sent by the bot itself.

    Args:
        after_id: Discord snowflake ID. Only return messages after this ID.
                  Leave empty to fetch the most recent 100 messages.
    """
    try:
        messages = discord_source.get_mentions(
            channel_id=DISCORD_CHANNEL_ID,
            after=after_id or None,
        )
    except ValueError as e:
        return f"Configuration error: {e}"
    except Exception as e:
        return f"Discord API error: {e}"

    if not messages:
        return "No unread mentions."

    lines = [f"Found {len(messages)} mention(s):\n"]
    for m in messages:
        lines.append(f"[{m['id']}] @{m['author']} ({m['author_id']}): {m['content']}")
    return "\n".join(lines)


@mcp.tool()
def get_discord_messages(
    after_id: str = "",
    limit: int = 50,
    regex_filter: str = "",
) -> str:
    """Browse Discord channel messages with optional regex filtering.

    Args:
        after_id: Discord snowflake ID. Only return messages after this ID.
                  Leave empty to fetch recent messages.
        limit: Number of messages to fetch (max 100).
        regex_filter: Optional regex pattern to filter message content.
                      Case-insensitive. Leave empty to return all messages.
    """
    try:
        messages = discord_source.get_messages(
            channel_id=DISCORD_CHANNEL_ID,
            after=after_id or None,
            limit=min(limit, 100),
        )
    except ValueError as e:
        return f"Configuration error: {e}"
    except Exception as e:
        return f"Discord API error: {e}"

    if regex_filter:
        messages = discord_source.filter_messages(messages, regex_filter)

    if not messages:
        return "No messages found."

    lines = [f"Found {len(messages)} message(s):\n"]
    for m in messages:
        bot_tag = " [bot]" if m["bot"] else ""
        lines.append(f"[{m['id']}] @{m['author']}{bot_tag}: {m['content']}")
    return "\n".join(lines)


@mcp.tool()
def send_discord_message(message: str) -> str:
    """Send a message to the Discord channel as the Town Elder bot.

    Args:
        message: Message content to send. Use <@USER_ID> to mention users.
    """
    try:
        result = discord_source.send_message(DISCORD_CHANNEL_ID, message)
        return f"Message sent (id: {result['id']})."
    except ValueError as e:
        return f"Configuration error: {e}"
    except Exception as e:
        return f"Discord API error: {e}"


if __name__ == "__main__":
    # Run the MCP server using standard input/output
    mcp.run()
