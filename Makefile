# Makefile — MyHordes MCP wiki build pipeline
#
# Usage:
#   make kb           Build the knowledge base (fetch → process)
#   make fetch        Fetch the wiki (requires browser cookies in .env)
#   make process      Process raw wiki into structured data
#   make clean-kb     Remove processed output (keeps raw wiki)
#   make clean-all    Remove everything (raw wiki + processed)

include .env
export

PYTHON ?= python3

WIKI_DIR      := wiki/wiki
PROC_DIR      := wiki/processed
ENTITIES_JSON := $(PROC_DIR)/entities.json
INDEX_JSON    := $(PROC_DIR)/index.json
PERSONA       ?= town-elder

# ── Local model (Ollama) ──────────────────────────────────────────────
# Claude Code speaks to Ollama's Anthropic-compatible /v1/messages endpoint,
# so it needs no proxy — only a base URL, a dummy token, and the model name.
# OLLAMA_HOST is the Windows host as seen from WSL; override on the CLI.
OLLAMA_HOST   ?= 172.29.0.1:11434
LOCAL_MODEL   ?= gemma4-hermes-qat:latest
# Claude Code does not know this model's window, so state it explicitly or it
# assumes 200k and auto-compacts early. The tag bakes num_ctx=262144.
LOCAL_CTX     ?= 262144

TIPS_FILES        := $(wildcard ./tips/*.md)
PERSONAL_FILES    := $(wildcard ./personal/*.md)

# Sentinel: any Data_ file means the wiki has been fetched
WIKI_SENTINEL := $(WIKI_DIR)/Data_Apple.txt

# ─── Main targets ─────────────────────────────────────────────

.PHONY: kb fetch process clean-kb clean-all help desert-veteran gemini-veteran use-persona hermes-skills hermes-gateway local-veteran local-shell local-check

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

use-persona: ## Switch active persona: make use-persona p=town-elder
	@test -f personas/$(or $(p),$(PERSONA)).md || (echo "ERROR: personas/$(or $(p),$(PERSONA)).md not found"; exit 1)
	rm -f AGENT-PERSONALITY.md
	ln -s personas/$(or $(p),$(PERSONA)).md AGENT-PERSONALITY.md
	rm -f .claude/output-styles/persona.md
	ln -s $(shell pwd)/personas/$(or $(p),$(PERSONA)).md .claude/output-styles/persona.md
	@echo "Active persona: $(or $(p),$(PERSONA))"

gemini-veteran: ## Start Gemini as the Desert Veteran advisor (embedded agent, proper CLI)
	.venv/bin/python gemini_client.py

desert-veteran: ## Start Claude as the Desert Veteran advisor (loads personality + tips)
	@test -f AGENT-PERSONALITY.md || (echo "ERROR: AGENT-PERSONALITY.md not found. Run: make use-persona p=<name>"; exit 1)
	claude \
		$(foreach f,$(TIPS_FILES),--append-system-prompt-file $(f)) \
		$(foreach f,$(PERSONAL_FILES),--append-system-prompt-file $(f)) \
		--append-system-prompt-file AGENT-PERSONALITY.md \
		"Persona and tips loaded. Introduce yourself briefly and await orders."

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


# ─── Discord ──────────────────────────────────────────────────

install-discord-mcp: ## Install mcp-discord Node package (optional — only needed for Discord channel/role management via MCP)
	$(HOME)/.nvm/versions/node/v22.22.0/bin/node $(HOME)/.nvm/versions/node/v22.22.0/lib/node_modules/npm/bin/npm-cli.js install


# ─── Hermes gateway ───────────────────────────────────────────
# HERMES_SKILLS_LINK: where Hermes discovers skills. Symlinking the repo's
# hermes-skills/ dir here means new skills appear with no re-install, and the
# SKILL.md stubs read the .claude/commands/*.md source of truth each run — so
# improving a command file needs no skill edit.
HERMES_HOME ?= $(HOME)/.hermes
HERMES_SKILLS_LINK := $(HERMES_HOME)/skills/myhordes

hermes-skills: ## Symlink repo skills into Hermes (~/.hermes/skills/myhordes)
	@test -d $(HERMES_HOME)/skills || (echo "ERROR: $(HERMES_HOME)/skills not found — is Hermes installed?"; exit 1)
	rm -f $(HERMES_SKILLS_LINK)
	ln -s $(shell pwd)/hermes-skills $(HERMES_SKILLS_LINK)
	@echo "Linked $(HERMES_SKILLS_LINK) -> $(shell pwd)/hermes-skills"
	@echo "Skills now visible to Hermes:"
	@ls hermes-skills/

hermes-gateway: hermes-skills ## Run the Hermes Discord gateway from this repo (cwd loads AGENTS.md)
	cd $(shell pwd) && hermes gateway run

discord-monitor: ## Monitor Discord #generale and reply to bot mentions (loops every 5 min, Haiku)
	claude \
		--model sonnet \
		$(foreach f,$(TIPS_FILES),--append-system-prompt-file $(f)) \
		$(foreach f,$(PERSONAL_FILES),--append-system-prompt-file $(f)) \
		--append-system-prompt-file personas/town-elder.md \
		"/loop 5m /discord-monitor loop"

# ── Local-model advisor (zero API cost) ───────────────────────────────

local-check: ## Verify Ollama is reachable and serving the Anthropic endpoint
	@curl -sf --max-time 10 http://$(OLLAMA_HOST)/api/tags >/dev/null \
		|| (echo "ERROR: Ollama unreachable at $(OLLAMA_HOST)"; exit 1)
	@curl -sf --max-time 10 http://$(OLLAMA_HOST)/api/tags \
		| grep -q '"$(LOCAL_MODEL)"' \
		|| (echo "ERROR: model $(LOCAL_MODEL) not pulled. Run: ollama pull $(LOCAL_MODEL)"; exit 1)
	@curl -sf --max-time 20 -o /dev/null http://$(OLLAMA_HOST)/v1/messages \
		-H 'content-type: application/json' \
		-d '{"model":"$(LOCAL_MODEL)","max_tokens":8,"messages":[{"role":"user","content":"ok"}]}' \
		|| (echo "ERROR: /v1/messages not served — Ollama too old? Need >= 0.31"; exit 1)
	@echo "OK: $(LOCAL_MODEL) reachable at $(OLLAMA_HOST), /v1/messages works"

local-veteran: local-check ## Start Claude Code as the advisor on the LOCAL model (no API cost)
	@test -f AGENT-PERSONALITY.md || (echo "ERROR: AGENT-PERSONALITY.md not found. Run: make use-persona p=<name>"; exit 1)
	ANTHROPIC_BASE_URL=http://$(OLLAMA_HOST) \
	ANTHROPIC_AUTH_TOKEN=ollama \
	ANTHROPIC_MODEL=$(LOCAL_MODEL) \
	ANTHROPIC_SMALL_FAST_MODEL=$(LOCAL_MODEL) \
	CLAUDE_CODE_MAX_CONTEXT_TOKENS=$(LOCAL_CTX) \
	CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
	claude \
		$(foreach f,$(TIPS_FILES),--append-system-prompt-file $(f)) \
		$(foreach f,$(PERSONAL_FILES),--append-system-prompt-file $(f)) \
		--append-system-prompt-file AGENT-PERSONALITY.md \
		--append-system-prompt-file TOOL-DISCIPLINE.md \
		"Persona and tips loaded. Introduce yourself briefly and await orders."

local-shell: local-check ## Bare Claude Code on the local model, no persona (for probing)
	ANTHROPIC_BASE_URL=http://$(OLLAMA_HOST) \
	ANTHROPIC_AUTH_TOKEN=ollama \
	ANTHROPIC_MODEL=$(LOCAL_MODEL) \
	ANTHROPIC_SMALL_FAST_MODEL=$(LOCAL_MODEL) \
	CLAUDE_CODE_MAX_CONTEXT_TOKENS=$(LOCAL_CTX) \
	CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
	claude
