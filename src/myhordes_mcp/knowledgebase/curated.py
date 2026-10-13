"""Curated advisor knowledge base: markdown files under knowledge/."""

import re

from ..utils.config import PROJECT_ROOT

KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"


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

    # Returning whole files blows the context on knowledge/tactics/ (60 KB+), so
    # send the matching sections instead, and only fall back to the head of the
    # file when no heading contains a term.
    parts = [f"Found {len(scored)} file(s) for '{query}':\n"]
    for nterms, total, md, text, matched in scored[:4]:
        rel = md.relative_to(root)
        parts.append(f"## {rel}  (matched: {', '.join(matched)})\n")
        blocks, cur = [], []
        for line in text.splitlines():
            if line.startswith("#") and cur:
                blocks.append(cur)
                cur = [line]
            else:
                cur.append(line)
        if cur:
            blocks.append(cur)
        keep = [b for b in blocks
                if any(re.search(r"\b" + re.escape(t), "\n".join(b).lower())
                       for t in terms)]
        chosen = keep[:6] if keep else blocks[:2]
        body = "\n\n".join("\n".join(b).strip() for b in chosen)
        parts.append(body[:6000] + ("\n… (section truncated)" if len(body) > 6000 else ""))
        parts.append("\n---\n")
    if len(scored) > 4:
        parts.append(f"({len(scored) - 4} more file(s) matched; narrow the query.)")
    return "\n".join(parts)
