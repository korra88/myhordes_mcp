"""
update_pages.py — Apply a MediaWiki XML export to the local wiki cache.

Reads a Special:Export XML file, extracts pages, updates raw .txt files in
wiki/wiki/, then reprocesses only those pages into wiki/processed/.

Usage:
    python3 kb_build/update_pages.py <path/to/export.xml>
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from process_wiki import (
    load_all_data_files,
    is_redirect,
    strip_wikitext,
    categorize_page,
    format_entity_section,
)

BASE_DIR = Path(__file__).parent.parent
WIKI_DIR = BASE_DIR / "wiki" / "wiki"
OUT_DIR = BASE_DIR / "wiki" / "processed"
PAGES_DIR = OUT_DIR / "pages"

MW_NS = "http://www.mediawiki.org/xml/export-0.11/"
MIN_PROSE_LENGTH = 80


def sanitize_filename(title: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", title)


def parse_xml_export(xml_path: Path) -> dict[str, str]:
    """Return {title: wikitext} for all pages in the export XML."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    pages = {}
    for page in root.findall(f"{{{MW_NS}}}page"):
        title_el = page.find(f"{{{MW_NS}}}title")
        text_el = page.find(f".//{{{MW_NS}}}text")
        if title_el is None or text_el is None or text_el.text is None:
            continue
        pages[title_el.text] = text_el.text
    return pages


EXPORT_HELP = """
No XML file provided.

Export pages from the wiki:
  1. Go to https://en.mhwiki.org/wiki/Special:Export
  2. Enter the page titles (one per line)
  3. Check "Include only the current revision"
  4. Click "Export" — save the downloaded XML
  5. Run: python3 kb_build/update_pages.py <path/to/export.xml>
"""


def main():
    if len(sys.argv) < 2:
        sys.exit(EXPORT_HELP)

    xml_path = Path(sys.argv[1])
    if not xml_path.exists():
        sys.exit(f"File not found: {xml_path}")

    print(f"Parsing {xml_path.name} ...")
    fetched = parse_xml_export(xml_path)
    print(f"  Found {len(fetched)} pages in export")

    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Save raw .txt files
    for title, content in fetched.items():
        safe = sanitize_filename(title)
        raw_path = WIKI_DIR / f"{safe}.txt"
        raw_path.write_text(content, encoding="utf-8")
        print(f"  Raw saved: {raw_path.name}")

    # Load entities (needed for processing)
    print("Loading entity data ...")
    entities = load_all_data_files()

    # Load existing index
    index_path = OUT_DIR / "index.json"
    index = {}
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))

    # Reprocess each page
    print("Processing pages ...")
    updated = 0
    for title, content in fetched.items():
        if is_redirect(content):
            print(f"  SKIP redirect: {title}")
            continue

        cleaned = strip_wikitext(content, entities)
        if len(cleaned) < MIN_PROSE_LENGTH:
            print(f"  SKIP stub: {title}")
            continue

        category = categorize_page(title, entities)
        matched_entity = entities.get(title)
        if not matched_entity:
            for ename, edata in entities.items():
                if ename.lower() == title.lower():
                    matched_entity = edata
                    break

        entity_block = ""
        if matched_entity:
            entity_block = format_entity_section(title, matched_entity) + "\n\n---\n\n"

        page_md = f"# {title}\n\n{entity_block}{cleaned}\n"
        safe_name = sanitize_filename(title)
        out_path = PAGES_DIR / f"{safe_name}.md"
        out_path.write_text(page_md, encoding="utf-8")

        index[title] = {
            "file": f"pages/{safe_name}.md",
            "category": category,
            "has_entity": matched_entity is not None,
        }
        print(f"  Updated: {out_path.name}")
        updated += 1

    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone. {updated} page(s) updated. Index written: {index_path}")


if __name__ == "__main__":
    main()
