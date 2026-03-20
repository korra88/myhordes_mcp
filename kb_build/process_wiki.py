"""
process_wiki.py — Transform raw wiki dumps into a structured knowledge base.

Reads raw MediaWiki text files from knowledge_base/wiki/ and produces:
  - knowledge_base/processed/entities.json   (structured data from Data_ files)
  - knowledge_base/processed/pages/          (cleaned prose, one .md per page)
  - knowledge_base/processed/index.json      (master index: entity→page mapping)

Usage:
    python3 process_wiki.py
"""

import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
WIKI_DIR = BASE_DIR / "knowledge_base" / "wiki"
OUT_DIR = BASE_DIR / "knowledge_base" / "processed"
PAGES_DIR = OUT_DIR / "pages"

# ---------------------------------------------------------------------------
# 1. Parse Data_ files into structured dicts
# ---------------------------------------------------------------------------

# Fields that use numbered suffixes and should be collapsed into lists.
# Maps prefix → (value_prefix, qty_prefix | None)
ARRAY_FIELD_SPECS = {
    "res":        ("res", "resQ"),
    "hardres":    ("hardres", "hardresQ"),
    "easyres":    ("easyres", "easyresQ"),
    "planres":    ("planres", "planresQ"),
    "item":       ("item", None),
    "drop":       ("drop", None),
    "prob":       ("prob", None),
    "givestatus": ("givestatus", None),
    "givestatuschance": ("givestatuschance", None),
    "removestatus":     ("removestatus", None),
    "removestatuschance": ("removestatuschance", None),
    "rest":       ("rest", None),
    "guardrest":  ("guardrest", None),
    "quantity":   ("quantity", None),
    "title":      ("title", None),
    "points":     ("points", None),
    "picto":      ("picto", None),
    "eruin":      ("eruin", None),
}

# Numeric-suffix pattern: field name ending in 1-99
_NUM_SUFFIX_RE = re.compile(r"^(.+?)(\d+)$")


def parse_data_file(text: str) -> dict | None:
    """Parse a Data_ wiki template into a flat dict, then normalize arrays."""
    # Strip the <includeonly>{{{{{format}}}| ... {{{1|}}}}}</includeonly> wrapper
    m = re.search(
        r"<includeonly>\{\{\{\{\{format\}\}\}\|(.+?)\{\{\{1\|\}\}\}\}\}</includeonly>",
        text,
        re.DOTALL,
    )
    if not m:
        return None
    body = m.group(1)

    # Strip HTML comments before parsing (they can contain | and break splitting)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)

    # Strip wiki markup from values before splitting, since [[file:...|link=...]]
    # contains | that looks like a field separator.
    body = re.sub(r"\[\[[^\]]*\]\]", "", body)       # [[...]] links/images
    body = re.sub(r"\{\{[^}]*\}\}", "", body)         # {{...}} templates

    # Extract key=value pairs separated by |
    raw: dict[str, str] = {}
    for line in body.split("\n"):
        line = line.strip().strip("|").strip()
        if not line or "=" not in line:
            continue
        # Each line may have multiple key=val pairs separated by |
        parts = re.split(r"\|(?=\s*\w+=)", line)
        for part in parts:
            part = part.strip()
            if "=" not in part:
                continue
            key, _, val = part.partition("=")
            key = key.strip()
            val = val.strip()
            if key and val:
                raw[key] = val

    if not raw:
        return None

    # Normalize numbered fields into arrays
    result: dict = {}
    consumed: set[str] = set()

    for prefix, (val_pfx, qty_pfx) in ARRAY_FIELD_SPECS.items():
        entries = []
        i = 1
        while True:
            vk = f"{val_pfx}{i}"
            if vk not in raw:
                break
            entry: dict = {"value": raw[vk]}
            consumed.add(vk)
            if qty_pfx:
                qk = f"{qty_pfx}{i}"
                if qk in raw:
                    entry["qty"] = raw[qk]
                    consumed.add(qk)
            entries.append(entry)
            i += 1
        if entries:
            result[prefix] = entries

    # Copy non-consumed scalar fields
    for k, v in raw.items():
        if k in consumed:
            continue
        # Skip count-only fields that just state the array length
        if k in ("resources", "hardresources", "easyresources", "planresources",
                 "items", "drops", "probs", "quantities", "titles", "points"):
            continue
        # Clean wiki markup from values (images, links, templates)
        v = re.sub(r"\[\[(?:file|File):[^\]]*\]\]", "", v, flags=re.IGNORECASE)
        v = re.sub(r"\[\[[^\]]*\|([^\]]+)\]\]", r"\1", v)
        v = re.sub(r"\[\[([^\]]+)\]\]", r"\1", v)
        v = re.sub(r"\{\{([^}|]+)\}\}", r"\1", v)
        v = v.strip()
        if v:
            result[k] = v

    return result


def load_all_data_files() -> dict[str, dict]:
    """Load every Data_*.txt file → {entity_name: parsed_dict}."""
    entities: dict[str, dict] = {}
    for path in sorted(WIKI_DIR.glob("Data_*.txt")):
        name = path.stem.removeprefix("Data_")
        text = path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_data_file(text)
        if parsed:
            entities[name] = parsed
    return entities


# ---------------------------------------------------------------------------
# 2. Clean prose pages — strip wikitext markup
# ---------------------------------------------------------------------------

def is_redirect(text: str) -> bool:
    return text.strip().upper().startswith("#REDIRECT")


def strip_wikitext(text: str, entities: dict[str, dict]) -> str:
    """Convert wikitext to clean Markdown-ish prose."""
    out = text

    # Remove full-line templates that are purely layout/navigation
    layout_templates = (
        "MetaInfobox", "NoMetaInfobox", "Clear", "Help", "Editing", "Mask",
        "Main", "Wiki", "Official help",
        # Navigation footers
        "Items", "Buildings", "Ruins", "Jobs", "Distinctions", "Status",
        "Deaths", "Homes", "Skills", "Town",
        # Season banners
        "Season \\d+ revised page",
        # Skill group templates
        "Strategist", "University", "Prepared", "Enduring", "Reclusive",
    )
    for t in layout_templates:
        pattern = r"^\s*\{\{" + t + r"(?:\|[^}]*)?\}\}\s*$"
        out = re.sub(pattern, "", out, flags=re.MULTILINE)

    # Resolve {{MetaInline|Target|displayname=Label}} → Label (or Target)
    def _resolve_metainline(m):
        parts = m.group(1).split("|")
        target = parts[0].strip()
        display = target
        for p in parts[1:]:
            if p.strip().startswith("displayname="):
                display = p.strip().removeprefix("displayname=")
        return display

    out = re.sub(r"\{\{MetaInline\|([^}]+)\}\}", _resolve_metainline, out)

    # Resolve {{Data|EntityName|field|default}} → looked-up value or default
    def _resolve_data(m):
        parts = m.group(1).split("|")
        if len(parts) >= 2:
            ename = parts[0].strip()
            field = parts[1].strip()
            default = parts[2].strip() if len(parts) > 2 else ""
            ent = entities.get(ename, {})
            return str(ent.get(field, default))
        return m.group(0)

    out = re.sub(r"\{\{Data\|([^}]+)\}\}", _resolve_data, out)

    # Strip remaining unknown templates — {{Foo|...}} → ""
    # But keep {{AP}}, {{DP}} etc. as plain text markers
    def _strip_template(m):
        name = m.group(1).split("|")[0].strip()
        if name in ("AP", "DP", "temp"):
            return name
        return ""

    out = re.sub(r"\{\{([^}]+)\}\}", _strip_template, out)

    # Wiki links: [[Target|Display]] → Display, [[Target]] → Target
    out = re.sub(r"\[\[[^\]]*\|([^\]]+)\]\]", r"\1", out)
    out = re.sub(r"\[\[([^\]]+)\]\]", r"\1", out)

    # Images: [[file:...]] or [[File:...]] — strip entirely
    out = re.sub(r"\[\[(?:file|File):[^\]]*\]\]", "", out, flags=re.IGNORECASE)

    # External links: [url text] → text
    out = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", out)

    # HTML tags
    out = re.sub(r"<ref[^>]*>.*?</ref>", "", out, flags=re.DOTALL)
    out = re.sub(r"</?(?:includeonly|noinclude|nowiki|br|hr|small|big|u|s|sup|sub|gallery|div|span|center|poem|source|syntaxhighlight|code|pre|blockquote|table|tr|td|th|caption|thead|tbody|tfoot)[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<!--.*?-->", "", out, flags=re.DOTALL)

    # Bold/italic wiki markup
    out = re.sub(r"'{2,5}", "", out)

    # Category tags
    out = re.sub(r"\[\[Category:[^\]]*\]\]", "", out, flags=re.IGNORECASE)

    # Wiki headings → Markdown headings
    for level in range(6, 1, -1):
        eq = "=" * level
        out = re.sub(
            rf"^{eq}\s*(.+?)\s*{eq}\s*$",
            "#" * level + r" \1",
            out,
            flags=re.MULTILINE,
        )

    # Wiki tables — convert to simple text rows (best-effort)
    out = re.sub(r"^\{\|.*$", "", out, flags=re.MULTILINE)  # {| ...
    out = re.sub(r"^\|\}.*$", "", out, flags=re.MULTILINE)  # |}
    out = re.sub(r"^\|-.*$", "", out, flags=re.MULTILINE)   # |-
    out = re.sub(r"^!\s*", "| ", out, flags=re.MULTILINE)   # ! header → | header
    out = re.sub(r'style="[^"]*"\|?\s*', "", out)            # style attrs

    # Collapse excessive blank lines
    out = re.sub(r"\n{3,}", "\n\n", out)

    return out.strip()


# ---------------------------------------------------------------------------
# 3. Categorize & filter pages
# ---------------------------------------------------------------------------

# Pages matching these patterns are excluded (meta/admin/useless)
EXCLUDE_PATTERNS = [
    re.compile(r"^Data_", re.IGNORECASE),          # raw data (already parsed)
    re.compile(r"^Template:", re.IGNORECASE),
    re.compile(r"^Category:", re.IGNORECASE),
    re.compile(r"^MediaWiki:", re.IGNORECASE),
    re.compile(r"^User:", re.IGNORECASE),
    re.compile(r"^File:", re.IGNORECASE),
    re.compile(r"^Minutes of the Meeting", re.IGNORECASE),
    re.compile(r"^Accueil$", re.IGNORECASE),        # French homepage
]

MIN_PROSE_LENGTH = 80  # characters after cleanup — skip stubs


def should_exclude(filename: str) -> bool:
    stem = Path(filename).stem
    return any(p.search(stem) for p in EXCLUDE_PATTERNS)


def categorize_page(name: str, entities: dict) -> str:
    """Guess a page category based on its matching entity or name heuristics."""
    if name in entities:
        return entities[name].get("category", "General").lower()
    # Try case-insensitive match
    for ename, edata in entities.items():
        if ename.lower() == name.lower():
            return edata.get("category", "General").lower()
    return "guide"


# ---------------------------------------------------------------------------
# 4. Merge & emit
# ---------------------------------------------------------------------------

def format_entity_section(name: str, data: dict) -> str:
    """Render a Data_ entity as a readable Markdown block for embedding."""
    lines = [f"## {data.get('name', name)}"]

    if data.get("blurb"):
        lines.append(f"*{data['blurb']}*")
        lines.append("")

    cat = data.get("category", "")
    subcat = data.get("subcategory", "")
    if cat:
        tag = f"**Category:** {cat}"
        if subcat:
            tag += f" — {subcat}"
        lines.append(tag)

    # Key scalar fields, skip the ones already shown
    skip = {"name", "id", "refid", "image", "largeimage", "blurb",
            "category", "subcategory", "french", "german", "spanish"}
    scalars = {k: v for k, v in data.items() if k not in skip and not isinstance(v, list)}
    if scalars:
        lines.append("")
        for k, v in scalars.items():
            lines.append(f"- **{k}:** {v}")

    # Array fields — resources, drops, etc.
    array_labels = {
        "res": "Resources", "hardres": "Resources (Hardcore)",
        "easyres": "Resources (Easy)", "planres": "Plan Resources",
        "drop": "Drops", "item": "Crafting Results",
        "givestatus": "Gives Status", "removestatus": "Removes Status",
        "quantity": "Thresholds", "title": "Titles",
    }
    for key, label in array_labels.items():
        arr = data.get(key)
        if not arr or not isinstance(arr, list):
            continue
        lines.append(f"\n**{label}:**")
        for entry in arr:
            val = entry.get("value", entry) if isinstance(entry, dict) else entry
            qty = entry.get("qty") if isinstance(entry, dict) else None
            if qty:
                lines.append(f"  - {val} ×{qty}")
            else:
                lines.append(f"  - {val}")

    # Drop table with probabilities (pair drop + prob arrays)
    drops = data.get("drop")
    probs = data.get("prob")
    if drops and probs and isinstance(drops, list) and isinstance(probs, list):
        lines.append("\n**Drop Table:**")
        for i, d in enumerate(drops):
            dval = d.get("value", d) if isinstance(d, dict) else d
            pval = probs[i].get("value", probs[i]) if i < len(probs) and isinstance(probs[i], dict) else (probs[i] if i < len(probs) else "?")
            lines.append(f"  - {dval} (weight: {pval})")

    return "\n".join(lines)


def process():
    print(f"Reading wiki files from {WIKI_DIR} ...")
    if not WIKI_DIR.is_dir():
        sys.exit(f"Error: {WIKI_DIR} does not exist. Run fetch_wiki.py first.")

    # Step 1: Parse Data_ files
    print("Parsing Data_ files ...")
    entities = load_all_data_files()
    print(f"  Parsed {len(entities)} entities")

    # Step 2-4: Clean, filter, merge prose pages
    print("Processing content pages ...")
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    index: dict[str, dict] = {}
    stats = {"total": 0, "redirects": 0, "excluded": 0, "stubs": 0, "kept": 0}

    for path in sorted(WIKI_DIR.glob("*.txt")):
        stats["total"] += 1
        name = path.stem

        if should_exclude(name):
            stats["excluded"] += 1
            continue

        text = path.read_text(encoding="utf-8", errors="replace")

        if is_redirect(text):
            stats["redirects"] += 1
            continue

        cleaned = strip_wikitext(text, entities)

        if len(cleaned) < MIN_PROSE_LENGTH:
            stats["stubs"] += 1
            continue

        # If there's a matching entity, prepend structured data
        category = categorize_page(name, entities)
        entity_block = ""
        matched_entity = entities.get(name)
        if not matched_entity:
            # case-insensitive fallback
            for ename, edata in entities.items():
                if ename.lower() == name.lower():
                    matched_entity = edata
                    break

        if matched_entity:
            entity_block = format_entity_section(name, matched_entity) + "\n\n---\n\n"

        # Compose final page
        page_md = f"# {name}\n\n{entity_block}{cleaned}\n"

        safe_name = re.sub(r'[\\/*?:"<>|]', "_", name)
        out_path = PAGES_DIR / f"{safe_name}.md"
        out_path.write_text(page_md, encoding="utf-8")

        index[name] = {
            "file": f"pages/{safe_name}.md",
            "category": category,
            "has_entity": matched_entity is not None,
        }
        stats["kept"] += 1

    # Write entities.json
    entities_path = OUT_DIR / "entities.json"
    entities_path.write_text(
        json.dumps(entities, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Write index.json
    index_path = OUT_DIR / "index.json"
    index_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nDone!")
    print(f"  Total files:    {stats['total']}")
    print(f"  Excluded:       {stats['excluded']} (Data_, Template:, etc.)")
    print(f"  Redirects:      {stats['redirects']}")
    print(f"  Stubs (<{MIN_PROSE_LENGTH} chars): {stats['stubs']}")
    print(f"  Pages written:  {stats['kept']}")
    print(f"  Entities:       {len(entities)}")
    print(f"\nOutput:")
    print(f"  {entities_path}")
    print(f"  {index_path}")
    print(f"  {PAGES_DIR}/")


if __name__ == "__main__":
    process()
