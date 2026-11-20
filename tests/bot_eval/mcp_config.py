"""The `--mcp-config` JSON that starts the offline server (server.py) for `claude -p`.

    .venv/bin/python tests/bot_eval/mcp_config.py 7365-d22 [--clock 14:30] [--user ID]
        [--context thread|dm] [--files FILE.json] [--manifest FILE] [--out FILE]

Prints the JSON (or writes it to --out). The server name is `myhordes`, as in the listener's
own config, so tool names are `mcp__myhordes__<tool>`.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def mcp_config(fixture: str, *, clock: str = "", user: str = "", context: str = "",
               files: str = "", manifest: str = "") -> dict:
    env = {"BOT_EVAL_FIXTURE": fixture, "BOT_EVAL_CLOCK": clock, "LISTENER_USER_ID": user,
           "LISTENER_CONTEXT": context, "BOT_EVAL_FILES": files, "BOT_EVAL_MANIFEST": manifest}
    return {"mcpServers": {"myhordes": {
        "type": "stdio",
        "command": str(ROOT / ".venv" / "bin" / "python"),
        "args": [str(ROOT / "tests" / "bot_eval" / "server.py")],
        "cwd": str(ROOT),
        "env": {k: v for k, v in env.items() if v},
    }}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixture")
    ap.add_argument("--clock", default="")
    ap.add_argument("--user", default="")
    ap.add_argument("--context", default="", choices=["", "thread", "dm"])
    ap.add_argument("--files", default="")
    ap.add_argument("--manifest", default="")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    text = json.dumps(mcp_config(a.fixture, clock=a.clock, user=a.user, context=a.context,
                                 files=a.files, manifest=a.manifest), indent=2)
    if a.out:
        a.out.write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
