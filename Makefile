# Makefile — MyHordes MCP knowledge-base pipeline
#
# Usage:
#   make kb           Build the knowledge base (fetch → process)
#   make fetch        Fetch the wiki (requires browser cookies in .env)
#   make process      Process raw wiki into structured data
#   make clean-kb     Remove processed output (keeps raw wiki)
#   make clean-all    Remove everything (raw wiki + processed)

PYTHON ?= python3

WIKI_DIR     := knowledge_base/wiki
PROC_DIR     := knowledge_base/processed
ENTITIES_JSON := $(PROC_DIR)/entities.json
INDEX_JSON    := $(PROC_DIR)/index.json

# Sentinel: any Data_ file means the wiki has been fetched
WIKI_SENTINEL := $(WIKI_DIR)/Data_Apple.txt

# ─── Main targets ─────────────────────────────────────────────

.PHONY: kb fetch process clean-kb clean-all help desert-veteran gemini-veteran

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

gemini-veteran: ## Start Gemini as the Desert Veteran advisor (embedded agent, proper CLI)
	.venv/bin/python gemini_client.py

desert-veteran: ## Start Claude as the Desert Veteran advisor (loads personality + tips)
	claude \
		--append-system-prompt-file ./tips/game-mechanics.md \
		--append-system-prompt-file ./tips/mcp-guidelines.md \
		--append-system-prompt-file ./tips/player-behavior.md \
		--append-system-prompt-file ./tips/strategy-quirks.md \
		--append-system-prompt-file ./tips/buildings-cheatsheet.md \
		--append-system-prompt-file ./agent-notes/INDEX.md \
		--append-system-prompt-file ./personal/INDEX.md \
		"Read AGENT-PERSONALITY-2.md and adopt the persona described in it completely before responding to anything else."

kb: process ## Build the full knowledge base (fetch if needed, then process)

# ─── Fetch ────────────────────────────────────────────────────

fetch: $(WIKI_SENTINEL) ## Fetch the wiki from en.mhwiki.org

$(WIKI_SENTINEL):
	$(PYTHON) kb_build/fetch_wiki.py

# ─── Process ──────────────────────────────────────────────────

process: $(INDEX_JSON) ## Process raw wiki into structured data + cleaned pages

$(INDEX_JSON): $(WIKI_SENTINEL) kb_build/process_wiki.py
	$(PYTHON) kb_build/process_wiki.py

# ─── Clean ────────────────────────────────────────────────────

clean-kb: ## Remove processed output (keeps raw wiki)
	rm -rf $(PROC_DIR)

clean-all: clean-kb ## Remove everything (raw wiki + processed)
	rm -rf $(WIKI_DIR)
