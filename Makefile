# Makefile — MyHordes MCP
#
# Usage:
#   make advisor      Start Claude Code as the town advisor (needs persona.md)
#   make kb           Build the knowledge base (fetch → process)
#   make fetch        Fetch the wiki (requires browser cookies in .env)
#   make process      Process raw wiki into structured data
#   make clean-kb     Remove processed output (keeps raw wiki)
#   make clean-all    Remove everything (raw wiki + processed)
#   make discord-listen  Answer Discord mentions (../discord_mcp listener)

-include .env
export

PYTHON ?= python3

WIKI_DIR      := wiki/wiki
PROC_DIR      := wiki/processed
ENTITIES_JSON := $(PROC_DIR)/entities.json
INDEX_JSON    := $(PROC_DIR)/index.json

# Knowledge files appended to the advisor's system prompt.
KNOWLEDGE_FILES := $(wildcard ./knowledge/tactics/*.md)
PERSONAL_FILES  := $(wildcard ./personal/*.md)

# Sentinel: any Data_ file means the wiki has been fetched
WIKI_SENTINEL := $(WIKI_DIR)/Data_Apple.txt

# ─── Main targets ─────────────────────────────────────────────

.PHONY: kb fetch process clean-kb clean-all help advisor persona discord-listen discord-listen-once \
	discord-service-install discord-service-disable discord-service-uninstall

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-26s\033[0m %s\n", $$1, $$2}'

persona.md:
	@echo "ERROR: persona.md not found. Create it from the example:"
	@echo "  cp persona.example.md persona.md"
	@exit 1

persona: persona.md ## Check that persona.md exists

advisor: persona.md ## Start Claude Code as the town advisor (persona + tactics + personal notes)
	claude \
		$(foreach f,$(KNOWLEDGE_FILES),--append-system-prompt-file $(f)) \
		$(foreach f,$(PERSONAL_FILES),--append-system-prompt-file $(f)) \
		--append-system-prompt-file persona.md \
		"Persona and knowledge loaded. Introduce yourself briefly and await orders."

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

DISCORD_MCP ?= ../discord_mcp

discord-listener.toml discord-listener.mcp.json:
	@echo "ERROR: $@ not found. Create it from the example and fill it in:"
	@echo "  cp $(subst .toml,.example.toml,$(subst .mcp.json,.mcp.example.json,$@)) $@"
	@exit 1

discord-listen: persona.md discord-listener.toml discord-listener.mcp.json ## Answer Discord mentions with Claude Code (../discord_mcp listener, discord-listener.toml). Ctrl-C to stop
	$(DISCORD_MCP)/.venv/bin/python $(DISCORD_MCP)/listen.py --config discord-listener.toml

discord-listen-once: persona.md discord-listener.toml discord-listener.mcp.json ## One poll cycle of the Discord listener, then exit
	$(DISCORD_MCP)/.venv/bin/python $(DISCORD_MCP)/listen.py --config discord-listener.toml --once

# ─── Discord listener as a systemd user service ───────────────

SERVICE      := discord-listener
SERVICE_FILE := $(HOME)/.config/systemd/user/$(SERVICE).service

discord-service-install: persona.md discord-listener.toml discord-listener.mcp.json ## Install and start the listener as a systemd user service (restarts on failure)
	@mkdir -p $(dir $(SERVICE_FILE))
	sed -e 's|@MCP_DIR@|$(CURDIR)|g' -e 's|@DISCORD_MCP@|$(abspath $(DISCORD_MCP))|g' \
		templates/systemd/$(SERVICE).service > $(SERVICE_FILE)
	systemctl --user daemon-reload
	systemctl --user enable --now $(SERVICE)
	@loginctl show-user $(USER) -p Linger 2>/dev/null | grep -q yes || \
		echo "NOTE: linger is off, so the service stops at logout and does not start at boot. Fix: sudo loginctl enable-linger $(USER)"

discord-service-disable: ## Stop the listener service and keep it from starting at boot (unit file kept)
	systemctl --user disable --now $(SERVICE)

discord-service-uninstall: ## Stop the listener service and remove its unit file
	-systemctl --user disable --now $(SERVICE)
	rm -f $(SERVICE_FILE)
	systemctl --user daemon-reload
