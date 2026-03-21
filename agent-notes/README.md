# agent-notes/

The Desert Veteran's persistent memory across towns and seasons.

**Not tracked in git.** Files in this folder are local only.

## Files

- `INDEX.md` — entry point the agent manages; lists all notes files with one-line descriptions *(local only, not tracked)*
- `<topic>.md` — individual notes files created by the agent as it learns cross-town patterns *(local only, not tracked)*

## INDEX.md template

On first use, the agent creates `INDEX.md` with this structure:

```markdown
# Agent Notes Index

Cross-town observations the Desert Veteran carries between sessions.
This file is the entry point — keep it under 100 lines.

## Notes files

<!-- Format: - [filename.md](filename.md) — what it covers -->
```

## What gets saved here

- Behavioral patterns of specific players observed across multiple towns
- Meta-game conclusions the agent reached the hard way
- Cross-town strategy insights that don't belong in the shared `tips/` files

## What does NOT go here

- Town-specific data → use `towns/s{season}-{town-slug}/`
- Facts already in `tips/*.md` or `knowledge_base/`
- Ephemeral session state
