"""Curated advisor knowledge base: markdown files under knowledge/."""

import re

from ..utils.config import PROJECT_ROOT

KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
SECTIONS = 3  # sections returned in full


def search(query: str, section: str = "") -> str:
    """Score knowledge/*.md by query terms and return the matching sections."""
    root = KNOWLEDGE_DIR
    kb_dir = root / section if section else root

    if not kb_dir.exists():
        avail = ", ".join(sorted(d.name for d in root.iterdir() if d.is_dir()))
        return f"Knowledge section '{section}' not found. Available: {avail}."

    # Score per term, not by exact-substring of the whole query: a query like
    # "thirst step counter" matched nothing before, even though the file explains
    # exactly that -- the phrase simply never appears verbatim. Terms are matched
    # on a word-prefix boundary so "counter"/"counters" and "zone"/"zones" hit.
    terms = [t for t in re.split(r"[^\w]+", query.lower()) if len(t) > 2]
    if not terms:
        return "Query too short — give at least one word of 3+ characters."

    # A query naming a file ("basic", "defense-focus") returns that whole file. The
    # phase guides say "basic" only in their title, so section matching below sent
    # back the title alone and dropped the tables the build-plan skill asks for.
    # Files over the 6000-char cap still go through section matching.
    for md in sorted(kb_dir.rglob("*.md")):
        if re.split(r"[^\w]+", md.stem.lower()) == terms:
            body = md.read_text(encoding="utf-8").strip()
            if len(body) <= 6000:
                return f"## {md.relative_to(root)}  (whole file)\n\n{body}"

    scored = []
    for md in sorted(kb_dir.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        low = text.lower()
        hits = {t: len(re.findall(r"\b" + re.escape(t), low)) for t in terms}
        matched = [t for t, n in hits.items() if n]
        if not matched:
            continue
        # rank by how many distinct terms matched first, then total occurrences
        scored.append((len(matched), sum(hits.values()), md, text, matched))

    if not scored:
        return (f"No knowledge entries found for '{query}'"
                + (f" in section '{section}'" if section else "")
                + f". Terms tried: {', '.join(terms)}.")

    scored.sort(key=lambda x: (-x[0], -x[1]))

    # Returning whole files blows the context on knowledge/tactics/ (60 KB+), and
    # even every matching section of every file ran to 3-4k tokens for a simple
    # question. Rank the sections themselves and send the best few; list the rest
    # by title so the model can ask for one.
    ranked = []
    for file_rank, (_, _, md, text, _) in enumerate(scored):
        rel = md.relative_to(root)
        blocks, cur = [], []
        for line in text.splitlines():
            if line.startswith("#") and cur:
                blocks.append(cur)
                cur = [line]
            else:
                cur.append(line)
        if cur:
            blocks.append(cur)
        for b in blocks:
            low = "\n".join(b).lower()
            hits = {t: len(re.findall(r"\b" + re.escape(t), low)) for t in terms}
            n = sum(1 for v in hits.values() if v)
            if n:
                title = next((l.lstrip("# ").strip() for l in b if l.startswith("#")), "(top of file)")
                body = "\n".join(b[1:] if b[0].startswith("#") else b).strip()
                ranked.append((-n, -sum(hits.values()), file_rank, rel, title, body))
    if not ranked:  # terms only in front matter: the head of the best file
        _, _, md, text, _ = scored[0]
        return f"## {md.relative_to(root)}\n\n{text[:3000]}"
    ranked.sort(key=lambda r: r[:3])
    best, rest = ranked[:SECTIONS], ranked[SECTIONS:]
    parts = []
    for *_, rel, title, body in best:
        parts += [f"## {rel} › {title}", "", body[:3000] + ("\n… (truncated)" if len(body) > 3000 else ""), ""]
    if rest:
        parts.append("Other matching sections (search their title or file name):")
        parts += [f"- {rel} › {title}" for *_, rel, title, _ in rest[:8]]
        if len(rest) > 8:
            parts.append(f"- … {len(rest) - 8} more; narrow the query")
    return "\n".join(parts).rstrip()
