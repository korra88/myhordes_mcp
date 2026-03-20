import json
import os
import re
import subprocess
import time
import urllib.parse

from dotenv import load_dotenv

load_dotenv()

# Configuration
WIKI_API_URL = "https://en.mhwiki.org/api.php"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge_base", "wiki")

# Cloudflare requires browser-like headers + cf_clearance cookie.
# To refresh: open en.mhwiki.org in Chrome, copy cookies from DevTools,
# then update MHWIKI_CF_CLEARANCE, MHWIKI_SESSION, MHWIKI_TOKEN in .env.
cf_clearance = os.environ.get("MHWIKI_CF_CLEARANCE", "")
mhwiki_session = os.environ.get("MHWIKI_SESSION", "")
mhwiki_token = os.environ.get("MHWIKI_TOKEN", "")

if not cf_clearance or not mhwiki_session:
    raise SystemExit(
        "Missing required env vars: MHWIKI_CF_CLEARANCE, MHWIKI_SESSION.\n"
        "Copy them from your browser DevTools (Cookies for en.mhwiki.org) into .env"
    )

COOKIES = (
    f"mhwikiUserName=USER; mhwikiUserID=ID; "
    f"mhwikiToken={mhwiki_token}; "
    f"mhwiki_session={mhwiki_session}; "
    f"cf_clearance={cf_clearance}"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)


def sanitize_filename(title: str) -> str:
    """Removes or replaces characters invalid for local filenames."""
    return re.sub(r'[\\/*?:"<>|]', "_", title)


def curl_get_json(params: dict) -> dict:
    """Fetch a URL via curl (bypasses Cloudflare) and return parsed JSON."""
    qs = urllib.parse.urlencode(params)
    url = f"{WIKI_API_URL}?{qs}"
    result = subprocess.run(
        [
            "curl", "-s",
            "-H", f"user-agent: {USER_AGENT}",
            "-H", "accept: application/json",
            "-H", 'sec-ch-ua: "Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "-H", "sec-ch-ua-mobile: ?0",
            "-H", 'sec-ch-ua-platform: "Windows"',
            "-b", COOKIES,
            url,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")
    return json.loads(result.stdout)


def download_wiki():
    """Iterates through the MediaWiki API to download all pages."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Directory ready: {OUTPUT_DIR}")

    params = {
        "action": "query",
        "generator": "allpages",
        "gaplimit": "50",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "format": "json",
    }

    pages_downloaded = 0
    batch = 0

    while True:
        batch += 1
        print(f"Fetching batch {batch}...")
        try:
            data = curl_get_json(params)
        except Exception as e:
            print(f"Error fetching batch {batch}: {e}")
            break

        pages = data.get("query", {}).get("pages", {})
        for page_id, page_info in pages.items():
            title = page_info.get("title", "Unknown_Title")
            try:
                content = page_info["revisions"][0]["slots"]["main"]["*"]
            except KeyError:
                print(f"  Skipping {title}: No content found.")
                continue

            safe_title = sanitize_filename(title)
            filepath = os.path.join(OUTPUT_DIR, f"{safe_title}.txt")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            pages_downloaded += 1

        print(f"  Batch {batch}: {len(pages)} pages (total: {pages_downloaded})")

        if "continue" in data:
            params.update(data["continue"])
            time.sleep(1)
        else:
            break

    print(f"\nWiki download complete! Total pages saved: {pages_downloaded}")


if __name__ == "__main__":
    print("Starting MyHordes Wiki download...")
    download_wiki()
