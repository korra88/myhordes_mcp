# Makefile — MyHordes MCP knowledge-base pipeline
#
# Usage:
#   make kb           Build the knowledge base (fetch → process)
#   make fetch        Fetch the wiki (requires browser cookies in .env)
#   make process      Process raw wiki into structured data
#   make clean-kb     Remove processed output (keeps raw wiki)
#   make clean-all    Remove everything (raw wiki + processed)

PYTHON ?= python3

WIKI_DIR      := knowledge_base/wiki
PROC_DIR      := knowledge_base/processed
ENTITIES_JSON := $(PROC_DIR)/entities.json
INDEX_JSON    := $(PROC_DIR)/index.json
PERSONA	      := persona-town-elder.md

TIPS_FILES        := $(wildcard ./tips/*.md)
AGENT_NOTES_FILES := $(wildcard ./agent-notes/*.md)
PERSONAL_FILES    := $(wildcard ./personal/*.md)

# Sentinel: any Data_ file means the wiki has been fetched
WIKI_SENTINEL := $(WIKI_DIR)/Data_Apple.txt

# ─── Main targets ─────────────────────────────────────────────

.PHONY: kb fetch process clean-kb clean-all help desert-veteran gemini-veteran install-persona

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install-persona:
	rm -rf .claude/output-styles/persona.md || true
	ln -s $(shell pwd)/$(PERSONA) .claude/output-styles/persona.md

gemini-veteran: ## Start Gemini as the Desert Veteran advisor (embedded agent, proper CLI)
	.venv/bin/python gemini_client.py

desert-veteran: ## Start Claude as the Desert Veteran advisor (loads personality + tips)
	claude \
		$(foreach f,$(TIPS_FILES),--append-system-prompt-file $(f)) \
		$(foreach f,$(AGENT_NOTES_FILES),--append-system-prompt-file $(f)) \
		$(foreach f,$(PERSONAL_FILES),--append-system-prompt-file $(f)) \
		"Read persona-town-elder.md and adopt the persona described in it completely before responding to anything else."

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
