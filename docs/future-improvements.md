# Future Improvements

Ideas that aren't actionable yet but worth revisiting.

## Consolidate agent-managed folders under a single shareable root

**Problem:** Agent-generated content is split across multiple top-level folders (`towns/`, `agent-notes/`, `tips/`). Sharing these with coalition members — or syncing them between machines — requires tracking each folder separately.

**Idea:** Move all agent-managed folders under a single parent (e.g. `agent-data/`) that could be its own git repo (or a submodule). This would allow:
- One `git push` to share logs + notes with coalition
- Clean separation between MCP code and agent-generated content
- Easier backup/sync between devices (e.g. Raspberry Pi and main PC)

**Open questions:**
- Which folders belong inside? `towns/` and `agent-notes/` for sure. `tips/` is debatable — it's baked into the agent prompt via the Makefile.
- Submodule vs. nested repo vs. just a separate remote on a subfolder?
- What in `agent-notes/` should be shareable vs. private?

**Status:** Idea only. No urgency.
