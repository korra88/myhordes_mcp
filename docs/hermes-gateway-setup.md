# Hermes Discord Gateway — Setup & Handoff

How the MyHordes advisor runs on the **Hermes CLI gateway** (self-hosted, native
Discord integration, local Ollama model — no Anthropic tokens). This is the
production Discord bot path. Written for cold-context handoff.

## TL;DR — how to run it

```sh
cd /absolute/path/to/myhordes_mcp
make hermes-gateway        # symlinks skills (idempotent) + runs `hermes gateway run` from repo cwd
```

Then in a Discord thread, once per thread:

```
/personality gazetteer     # enable the on-demand Gazetteer persona for THIS thread
```

That's it. cwd = repo is what loads the rules; the persona is opt-in per thread.

## Architecture — three independent layers

| Layer | Lives in | Scope / activation | Contents |
|---|---|---|---|
| **Persona** (Gazetteer) | `~/.hermes/config.yaml` → `agent.personalities.gazetteer` (dict form: `system_prompt` + `tone` + `style`) | **On-demand, per session.** `display.personality` is left empty so it is NOT a global default. Enable per Discord thread with `/personality gazetteer`; clear with `/personality none`. | Darkly-journalistic town chronicler voice. |
| **Rules** | repo `AGENTS.md` | **Always-on, cwd-scoped.** Auto-injected into the system prompt when the gateway's working dir is this repo (Hermes reads `AGENTS.md` from cwd, top-level only, no walk). Persona-independent. | Read-only rule, no-polling, tool discipline + condensed defaults, session-start memory reads, **memory full-rewrite rule**, skill trigger table. |
| **Skills** | repo `hermes-skills/<name>/SKILL.md`, symlinked to `~/.hermes/skills/myhordes` | cwd-independent (discovered from the skills store). Preload with `-s`, or invoke by name. **The 12B does NOT auto-discover skills** — must be invoked explicitly (see caveat). | Thin stubs that `read_file` the real workflow in `.claude/commands/<name>.md`. |

## Why these choices

- **Persona is a config `personalities` entry, not `SOUL.md`.** `SOUL.md` (`~/.hermes/SOUL.md`)
  is an always-on identity slot injected into *every* Hermes context (CLI included) — wrong for
  an opt-in game persona. It is left as the stock Nous boilerplate. The `personalities` overlay
  is appended ephemerally at API-call time (preserves prompt cache) and is resolved **per session**
  (`tui_gateway/server.py`: `personality = session.get("personality", cfg_personality)`), so
  `/personality` scopes to one Discord thread. Verified: default session = neutral Hermes;
  `_validate_personality("gazetteer")` renders a ~2.1KB overlay through Hermes' own code path.
- **Rules are cwd `AGENTS.md`, not the persona.** Read-only / anti-botting / tool discipline must
  hold under *any* persona, so they live in the always-on file. cwd-scoped means zero bloat when
  Hermes is used elsewhere.
- **Skills point at `.claude/commands/*.md` — single source of truth, zero drift.** The Claude Code
  command files and the Hermes skills would otherwise be two copies that drift. Instead each
  `hermes-skills/<name>/SKILL.md` is a stub telling the model to `read_file .claude/commands/<name>.md`
  and follow it. Edit the command file once → both Claude Code and Hermes follow the new version.
  Verified end-to-end: `-s myhordes-build-plan` → model opened stub → read the command file →
  quoted its step 1 verbatim.
- **Symlink, not copy.** `make hermes-skills` links the whole `hermes-skills/` dir into
  `~/.hermes/skills/myhordes`. New skills appear with no re-install (Hermes scans with
  `os.walk(..., followlinks=True)` for any `<name>/SKILL.md`). Skills stay versioned in-repo.
- **Launch from repo folder, NOT "set as home".** `HERMES_HOME` (`~/.hermes`) is the config/persona/
  skills store and is unrelated to the town data. Only the gateway's *cwd* must be the repo (for
  `AGENTS.md` + `tips/` + `towns/` memory). `make hermes-gateway` handles the cwd.

## Skills currently wired

`myhordes-build-plan`, `myhordes-close-day`, `myhordes-inspect-town`, `myhordes-building-report`
(each → its `.claude/commands/*.md` source). Plus the pre-existing `myhordes-memory` skill at
`~/.hermes/skills/games/myhordes-memory/SKILL.md` (memory full-rewrite rules).

To add a skill: create `hermes-skills/myhordes-<name>/SKILL.md` (frontmatter `name` + `description`
+ `platforms: [linux]`, body = "read_file `.claude/commands/<name>.md` and follow it"). No Makefile
or symlink change needed — the dir is already linked.

## Model & infra (from ../claude-ollama-protocol/HANDOFF.md)

- Model: `gemma4-hermes-qat:latest` (Ollama, QAT gemma4:12b + 256K ctx + FC stop-token recipe).
  262K context, ~74 tok/s, zero VRAM spill. Config default in `~/.hermes/config.yaml`.
- Ollama reachable from WSL at `http://172.29.0.1:11434` (WSL default-gateway IP).
- MCP server registered: `mcp_servers.myhordes` → `.venv/bin/python main.py`, read-only, 17 tools.

## Caveats (from Hermes battery testing — verified in `~/.hermes/state.db`)

1. **12B never auto-opens skills (T5).** The skill catalog is in the system prompt but the model
   will not `skill_view` on its own. In Discord it must *choose* to invoke by trigger phrase; the
   `AGENTS.md` trigger table is the lever. For a guaranteed load use `-s <skill>` — but the gateway
   has no per-thread `-s` flag, so reliability rests on the model obeying AGENTS.md.
2. **Memory files: full-rewrite only (T2).** The 12B "appends" by REPLACING the last line and
   double-escapes `\n` (data loss). The rule is baked into both `AGENTS.md` and every log-writing
   skill: read whole file → `write_file` entire file → read back to verify.
3. **`send_discord_message` is an exposed MCP write tool.** Under `--yolo` the model could post
   unprompted. `AGENTS.md` restricts it to intended replies only. Consider `hermes mcp configure`
   to disable it for non-Discord/test runs.

## Files touched by this setup

- `~/.hermes/config.yaml` — added `agent.personalities.gazetteer` (NOT in repo).
- `~/.hermes/SOUL.md` — reverted to stock Nous boilerplate (NOT in repo).
- `~/.hermes/skills/myhordes` — symlink → repo `hermes-skills/` (created by `make hermes-skills`).
- repo `AGENTS.md`, `hermes-skills/*/SKILL.md`, `Makefile` (targets `hermes-skills`, `hermes-gateway`).
