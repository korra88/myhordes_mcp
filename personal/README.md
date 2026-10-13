# personal/

Your private notes: known players (friends, allies, people to watch out for), your
own build and setup, season notes.

**Not tracked in git.** Every file in this folder except this README is local only.
`make advisor` loads all `personal/*.md` files as system prompts.

## Suggested files

- `INDEX.md` — entry point: one line per notes file, with what it covers. Keep it short.
- `friends.md` — player roster with notes (allies, neutral, do-not-trust). The advisor
  reads it at session start to recognize known players in the active town roster.
- `my-setup.md` — your class, equipment and skills, for expedition planning.

Edit freely. The agent will never overwrite your notes unless you explicitly ask it to.
