# Offline wiki (`search_wiki`)

`search_wiki` and `list_wiki_categories` search a local copy of [MHWiki](https://en.mhwiki.org),
kept in `wiki/` (gitignored). Without it they find nothing; every other tool works.
Two ways to build or update it:

## Targeted update (recommended for a few changed pages)

No auth or cookies needed — uses a browser export.

1. Go to `https://en.mhwiki.org/wiki/Special:Export`
2. Paste the page titles (one per line), check **"Include only the current revision"**, click **Export**
3. Save the XML, then run:

```bash
.venv/bin/python kb_build/update_pages.py path/to/MHWiki-export.xml
```

Running without arguments prints the full instructions.

## Full crawl

Fetches all ~3000 pages (5–10 min). Requires Cloudflare cookies in `.env`
(`MHWIKI_CF_CLEARANCE`, `MHWIKI_SESSION`, `MHWIKI_TOKEN`) copied from browser DevTools.
Must be run from the same machine as the browser (cookies are IP-bound).

```bash
make kb
# or manually:
.venv/bin/python kb_build/fetch_wiki.py
.venv/bin/python kb_build/process_wiki.py
```

`make clean-kb` removes the processed output (keeps the raw pages), `make clean-all` both.
