"""Knowledge base loader and search engine for the MyHordes wiki."""

import json

from ..utils.config import PROJECT_ROOT

# Built by kb_build/ (`make kb`).
_BASE_DIR = PROJECT_ROOT / "wiki" / "processed"

# Loaded once at import time — ~1 MB total, negligible.
_index: dict[str, dict] = {}
_entities: dict[str, dict] = {}

# Pre-built search corpus: list of (name_lower, category, has_entity, entity_keywords_lower)
_search_entries: list[tuple[str, str, str, bool, str]] = []


def _load():
    global _index, _entities, _search_entries

    index_path = _BASE_DIR / "index.json"
    entities_path = _BASE_DIR / "entities.json"

    if not index_path.exists():
        return

    with open(index_path) as f:
        _index = json.load(f)
    if entities_path.exists():
        with open(entities_path) as f:
            _entities = json.load(f)

    # Build search corpus
    for name, info in _index.items():
        # Gather searchable text from entity fields
        entity_keywords = ""
        ent = _entities.get(name)
        if ent:
            parts = [
                ent.get("blurb", ""),
                ent.get("subcategory", ""),
                ent.get("category", ""),
            ]
            # Include array field values (drops, resources, etc.)
            for v in ent.values():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and "value" in item:
                            parts.append(item["value"])
            entity_keywords = " ".join(parts)

        _search_entries.append((
            name,
            name.lower(),
            info["category"],
            info["has_entity"],
            entity_keywords.lower(),
        ))


_load()


def search(query: str, category: str | None = None, limit: int = 5) -> list[dict]:
    """Search the knowledge base. Returns list of {name, category, content}."""
    query_lower = query.lower()
    terms = query_lower.split()

    scored: list[tuple[float, str, str]] = []

    for name, name_lower, cat, has_entity, entity_kw in _search_entries:
        if category and cat != category:
            continue

        score = 0.0

        # Exact name match (highest priority)
        if query_lower == name_lower:
            score = 100.0
        # Name starts with query
        elif name_lower.startswith(query_lower):
            score = 80.0
        # Query is a substring of the name
        elif query_lower in name_lower:
            score = 60.0
        else:
            # Term-by-term matching
            name_hits = sum(1 for t in terms if t in name_lower)
            kw_hits = sum(1 for t in terms if t in entity_kw)

            if name_hits == 0 and kw_hits == 0:
                continue

            # Name matches are worth more than keyword matches
            score = (name_hits * 10.0) + (kw_hits * 2.0)

        # Boost pages with entity data (richer content)
        if has_entity:
            score += 1.0

        scored.append((score, name, cat))

    # Sort by score descending, then alphabetically
    scored.sort(key=lambda x: (-x[0], x[1]))

    results = []
    for _score, name, cat in scored[:limit]:
        page_path = _BASE_DIR / _index[name]["file"]
        content = ""
        if page_path.exists():
            content = page_path.read_text()
        results.append({"name": name, "category": cat, "content": content})

    return results


def get_categories() -> dict[str, int]:
    """Return {category: count} for all pages in the knowledge base."""
    cats: dict[str, int] = {}
    for _name, _name_lower, cat, _has_entity, _kw in _search_entries:
        cats[cat] = cats.get(cat, 0) + 1
    return dict(sorted(cats.items(), key=lambda x: -x[1]))


def get_page(name: str) -> str | None:
    """Get a specific page by exact name. Returns markdown content or None."""
    info = _index.get(name)
    if not info:
        return None
    page_path = _BASE_DIR / info["file"]
    if page_path.exists():
        return page_path.read_text()
    return None


def is_loaded() -> bool:
    """Check if the knowledge base was loaded successfully."""
    return len(_index) > 0


def format_search(query: str, category: str = "", limit: int = 5) -> str:
    """Search the wiki and format the hits as text for the LLM."""
    if not is_loaded():
        return "Error: Wiki not loaded. Run 'make process' to build it."

    limit = max(1, min(10, limit))
    cat = category.strip().lower() or None
    results = search(query, category=cat, limit=limit)

    if not results:
        return f"No results found for '{query}'" + (f" in category '{category}'" if category else "") + "."

    # The best hit in full; the others as one line each, so the model can tell
    # whether one is worth a second call (a full page costs ~1k tokens).
    best, rest = results[0], results[1:]
    parts = [f"## {best['name']} [{best['category']}]", "", _page_body(best["content"])]
    if rest:
        parts += ["", "---", "Other matches (search_wiki('<name>', limit=1) for the page):"]
        parts += [f"- {r['name']} [{r['category']}] — {_first_sentence(r['content'])}" for r in rest]
    return "\n".join(parts)


def _page_body(content: str) -> str:
    """The page without its repeated '# Name' title line."""
    lines = content.strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _first_sentence(content: str, limit: int = 160) -> str:
    """The page's italic description, else its first line of prose."""
    for line in content.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "|", "-", "*Category", "**")):
            continue
        s = s.strip("*").split(" / ")[0]
        return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "…"
    return "(no description)"


def format_categories() -> str:
    """List wiki categories with page counts."""
    if not is_loaded():
        return "Error: Wiki not loaded. Run 'make process' to build it."

    cats = get_categories()
    lines = ["MyHordes Wiki Categories:\n"]
    total = 0
    for cat, count in cats.items():
        lines.append(f"- {cat}: {count} pages")
        total += count
    lines.append(f"\nTotal: {total} pages")
    lines.append("\nUse search_wiki(query, category='...') to search within a category.")
    return "\n".join(lines)
