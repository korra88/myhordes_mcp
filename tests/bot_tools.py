"""Offline test of log_feedback / remember / forget and the memory migration.

Run: .venv/bin/python tests/bot_tools.py   (temp dirs only, never touches towns/)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from myhordes_mcp.bot import migrate, store  # noqa: E402

tmp = Path(tempfile.mkdtemp())
store.BOT_DIR = tmp / "_bot"
U = "394972002051424256"


def env(user=None, ctx=None):
    for k, v in (("LISTENER_USER_ID", user), ("LISTENER_CONTEXT", ctx)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


FB = ("complaint", "1563872498196549633", "DM", 'quando "ti" chiedo', "tool X returned Y", "none")

# refusal without env
env()
assert "only from the Discord listener" in store.log_feedback(*FB)
assert "only from the Discord listener" in store.remember("x")
assert "only from the Discord listener" in store.forget("x")
env("../x", "dm")
assert "only from the Discord listener" in store.remember("x")
assert not (tmp / "_bot").exists()

# feedback
env(U, "thread")
out = store.log_feedback(*FB)
files = list((store.BOT_DIR / "feedback").glob("*.md"))
assert len(files) == 1 and files[0].name.endswith("-1563872498196549633.md"), files
assert out.startswith("logged"), out
body = files[0].read_text()
lines = body.splitlines()
assert lines[0].startswith("# complaint — #DM [1563872498196549633] 20"), lines[0]
assert f"(author id {U})" in lines[2] and lines[2].startswith('- said: "'), lines[2]
assert lines[3] == "- context: tool X returned Y" and lines[4] == "- idea: none"
# duplicate: not overwritten
assert "already logged" in store.log_feedback("praise", FB[1], "DM", "other", "c", "i")
assert files[0].read_text() == body
# validation
assert "kind must be" in store.log_feedback("bogus", "1", "DM", "a", "b", "c")
assert "digits only" in store.log_feedback("praise", "12ab", "DM", "a", "b", "c")
assert "digits only" in store.log_feedback("praise", "../1", "DM", "a", "b", "c")
assert "limit is 300" in store.log_feedback("praise", "2", "DM", "a" * 301, "b", "c")
assert "1000" in store.log_feedback("praise", "2", "DM", "a", "b" * 1001, "c")
assert "1000" in store.log_feedback("praise", "2", "DM", "a", "b", "c" * 1001)
assert len(list((store.BOT_DIR / "feedback").glob("*.md"))) == 1
# author is never an argument: env user only
env("111", "thread")
store.log_feedback("praise", "3", "x", "hi", "c", "i")
assert "(author id 111)" in next((store.BOT_DIR / "feedback").glob("*-3.md")).read_text()

# memory refused outside dm
env(U, "thread")
assert "memory exists only in private messages" in store.remember("x")
assert "memory exists only in private messages" in store.forget("x")
env(U, None)
assert "memory exists only in private messages" in store.remember("x")
assert not (store.BOT_DIR / "memory").exists()

# memory in dm
env(U, "dm")
mem = store.BOT_DIR / "memory" / f"{U}.md"
assert store.remember("Plays a Guardian\nin town 8299").startswith("remembered")
text = mem.read_text().splitlines()
assert text[0] == "# Bot memory" and len(text) == 2
assert text[1].endswith(" · Plays a Guardian in town 8299") and text[1].startswith("- 20"), text
assert "limit is 300" in store.remember("a" * 301)
assert "empty" in store.remember("   ")
for i in range(39):
    assert store.remember(f"fact {i}").startswith("remembered")
assert len([ln for ln in mem.read_text().splitlines() if ln.startswith("- ")]) == 40
assert "full" in store.remember("one more")
assert len(mem.read_text().splitlines()) == 41
# forget
assert "nothing matched" in store.forget("zzz-nope")
assert "at least 3 characters" in store.forget("ab")  # a 1-2 char text would match almost every line
assert len(mem.read_text().splitlines()) == 41
assert store.forget("GUARDIAN") == "forgot 1 line(s)."
assert "guardian" not in mem.read_text().lower()
assert store.remember("after forget").startswith("remembered")
assert not list(store.BOT_DIR.rglob("*.tmp"))
# other user's file is separate
env("222", "dm")
store.remember("mine")
assert (store.BOT_DIR / "memory" / "222.md").exists() and "mine" not in mem.read_text()

# migration on a temp copy
mig = tmp / "migbot"
mig.mkdir()
src = Path(__file__).resolve().parent.parent / "towns" / "_bot" / "memory.md"
(mig / "memory.md").write_text(src.read_text() if src.exists() else "")
if not src.exists():  # fixture when the real file is absent
    (mig / "memory.md").write_text(
        f"# Bot memory\n- 2026-10-16 · {U} · Discord ID {U} is Korra\n"
        f"- 2026-10-25 · {U} · Korra: when she asks for the town status, also run inspect-town to update the logs\n"
        f"- 2026-10-26 · {U} · Korra (Guardian): 18 AP\n")
print(migrate.migrate(mig))
new = (mig / "memory" / f"{U}.md").read_text()
assert new.startswith("# Bot memory\n")
assert "inspect-town" not in new
assert f"- 2026-10-16 · Discord ID {U} is the player Korra" in new or f"Discord ID {U} is Korra" in new
assert all(ln.startswith("- 20") and f" · {U} · " not in ln for ln in new.splitlines()[1:]), new
assert len(new.splitlines()) - 1 == 3, new
assert not (mig / "memory.md").exists() and (mig / "memory.md.migrated").exists()
before = new
assert "nothing to migrate" in migrate.migrate(mig)
assert (mig / "memory" / f"{U}.md").read_text() == before
print(new)
print("ok: all bot tool checks passed")
