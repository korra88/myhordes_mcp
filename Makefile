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
#   make golden       Check every tool's output against the recorded goldens (tests/golden.py)

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

.PHONY: kb fetch process clean-kb clean-all help advisor persona town discord-listen discord-listen-once \
	discord-service-install discord-service-disable discord-service-uninstall \
	towns-commit towns-commit-install towns-commit-disable towns-commit-uninstall \
	golden golden-update golden-freeze

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

town: ## Show or set the default town: make town TOWN=<Fata town ID>; FOR=<discord id> for one user's own (no restart needed)
	@$(PYTHON) scripts/set_town.py $(if $(FOR),--user $(FOR)) $(TOWN)

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

SERVICE  := discord-listener
UNIT_DIR := $(HOME)/.config/systemd/user

# Render templates/systemd/$(1) with this checkout's paths into the user unit dir.
define render-unit
	@mkdir -p $(UNIT_DIR)
	sed -e 's|@MCP_DIR@|$(CURDIR)|g' -e 's|@DISCORD_MCP@|$(abspath $(DISCORD_MCP))|g' \
		templates/systemd/$(1) > $(UNIT_DIR)/$(1)
endef

define check-linger
	@loginctl show-user $(USER) -p Linger 2>/dev/null | grep -q yes || \
		echo "NOTE: linger is off, so user units stop at logout and do not start at boot. Fix: sudo loginctl enable-linger $(USER)"
endef

discord-service-install: persona.md discord-listener.toml discord-listener.mcp.json ## Install and start the listener as a systemd user service (restarts on failure)
	$(call render-unit,$(SERVICE).service)
	systemctl --user daemon-reload
	systemctl --user enable --now $(SERVICE)
	$(check-linger)

discord-service-disable: ## Stop the listener service and keep it from starting at boot (unit file kept)
	systemctl --user disable --now $(SERVICE)

discord-service-uninstall: ## Stop the listener service and remove its unit file
	-systemctl --user disable --now $(SERVICE)
	rm -f $(UNIT_DIR)/$(SERVICE).service
	systemctl --user daemon-reload

# ─── Town logs: nightly commit of towns/ (separate git repo) ──

towns-commit: ## Commit and push towns/ (pull --rebase first: other machines push too)
	@cd towns && git add -A && \
	if git diff --cached --quiet; then echo "towns: nothing to commit"; \
	else git commit -q -m "logs: snapshot $$(date '+%F %H:%M')" && echo "towns: committed $$(git log -1 --format='%h %s')"; fi && \
	{ git pull --rebase -q || { git rebase --abort; echo "towns: rebase conflict, resolve by hand"; exit 1; }; } && \
	git push -q && echo "towns: pushed, HEAD $$(git log -1 --format=%h)"

towns-commit-install: ## Install the systemd user timer that runs towns-commit every night at 04:00
	$(call render-unit,towns-commit.service)
	$(call render-unit,towns-commit.timer)
	systemctl --user daemon-reload
	systemctl --user enable --now towns-commit.timer
	$(check-linger)

towns-commit-disable: ## Stop the nightly towns-commit timer (unit files kept)
	systemctl --user disable --now towns-commit.timer

towns-commit-uninstall: ## Stop the nightly towns-commit timer and remove its unit files
	-systemctl --user disable --now towns-commit.timer
	rm -f $(UNIT_DIR)/towns-commit.service $(UNIT_DIR)/towns-commit.timer
	systemctl --user daemon-reload

# ─── Golden-output tests (offline; fixtures and outputs stay local in tests/golden/) ───

golden: ## Check every tool's output against the recorded goldens (exit 1 on a difference)
	@.venv/bin/python tests/golden.py

golden-update: ## Record the current tool outputs as the goldens (review the change first)
	@.venv/bin/python tests/golden.py --update

golden-freeze: ## Copy the fixture towns from towns/ and fetch the Gest'Hordes stats once
	@.venv/bin/python tests/golden.py --freeze
