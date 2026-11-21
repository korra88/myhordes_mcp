"""Bot evaluation runner: asks the Discord advisor the scenarios' questions through the listener's
own code (argv, settings, system prompt, stdin prompt, result parsing) with the offline MCP server
(server.py) as its only tool server, and records what it did. No grading here (phase 5).

Run with the listener's interpreter (it needs the `mcp` package):
    ../discord_mcp/.venv/bin/python tests/bot_eval/run.py [--suite core|extended|all] [--only I1,C4]
        [--model claude-haiku-5-5] [--tier public|trusted] [--label NAME] [--repeat N]
        [--allow-extra mcp__myhordes__plan_camping] [--max-budget 3] [--dry-run]
or `make bot-eval ...` (Makefile). A person runs it; never from cron or CI. Plan: docs/bot-eval-plan.md.

Differences from a deployed turn, on purpose (decision 7 and section 5.2):
- the MCP config is the generated one (offline server on the scenario's fixture, `--strict-mcp-config`);
- `Write(...)` / `Edit(...)` are removed from the allowed tools and `unsafe_allow` is emptied;
- the chat message carries the frozen game time, not the wall clock, so it agrees with the tools;
- a DM scenario's memory is the scenario's text (synthetic), not a file of the real towns/.
The real towns/ (without _eval/runs/) must be identical before and after the run, else the run
file is flagged and the exit code is 2.
"""

import argparse
import dataclasses
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tests" / "bot_eval"))
DISCORD_MCP = Path(os.environ.get("DISCORD_MCP", ROOT.parent / "discord_mcp")).resolve()
TOML = ROOT / "discord-listener.toml"
RUNS = ROOT / "towns" / "_eval" / "runs"
PRICES = ROOT / "tests" / "bot_eval" / "prices.json"
PREFIX = "mcp__myhordes__"
CHANNEL = "myhordes-ai"   # the channel name the prompt shows (the listener uses Discord's own name)

if not (DISCORD_MCP / "listener.py").is_file():
    sys.exit(f"bot-eval needs the private listener repo: {DISCORD_MCP}/listener.py not found "
             "(set DISCORD_MCP=<path>). Plan, section 9 decision 8.")
sys.path.insert(0, str(DISCORD_MCP))
try:
    import listener  # noqa: E402
except ImportError as exc:
    sys.exit(f"cannot import the listener ({exc}). Run with the listener's interpreter: "
             f"{DISCORD_MCP}/.venv/bin/python tests/bot_eval/run.py (make bot-eval does).")

from mcp_config import mcp_config  # noqa: E402
from scenario import ScenarioError, load_all  # noqa: E402
from server import SYNTH_USER, scenario_files  # noqa: E402


# ── helpers ─────────────────────────────────────────────────────────────────

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_hash(root: Path) -> str:
    """One hash of every file under root (path and content), for fixtures and wiki/processed."""
    h = hashlib.sha256()
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(str(f.relative_to(root)).encode() + b"\0" + hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def real_towns_state() -> dict:
    """{path: (size, mtime_ns)} of the real towns/ without _eval/runs/ and .git (the guard)."""
    towns = ROOT / "towns"
    out = {}
    for f in towns.rglob("*"):
        rel = f.relative_to(towns)
        if rel.parts[0] == ".git" or rel.parts[:2] == ("_eval", "runs") or not f.is_file():
            continue
        st = f.stat()
        out[str(rel)] = (st.st_size, st.st_mtime_ns)
    return out


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True).stdout.strip()


def cli_version() -> str:
    try:
        return subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unknown ({exc})"


def frozen_time(fixture: str, clock: str) -> str:
    """The scenario's frozen game time, UTC ISO, asked of the offline server (`server.py --now`)."""
    env = {**os.environ, "BOT_EVAL_FIXTURE": fixture, "BOT_EVAL_CLOCK": clock}
    p = subprocess.run([str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "tests" / "bot_eval" / "server.py"), "--now"],
                       capture_output=True, text=True, env=env, cwd=ROOT, timeout=120)
    lines = p.stdout.strip().splitlines()
    if p.returncode != 0 or not lines:
        sys.exit(f"server.py --now failed for {fixture}: {p.stderr.strip()[-400:]}")
    return lines[-1]


def trace_of(events: list[dict]) -> list[dict]:
    """tool_use blocks paired with their tool_result, in call order (full output)."""
    calls, order = {}, []
    for e in events:
        if e.get("parent_tool_use_id"):
            continue
        msg = e.get("message")
        if not isinstance(msg, dict):   # some CLI events carry a plain-text message
            continue
        for b in msg.get("content") or []:
            if not isinstance(b, dict):
                continue
            if e.get("type") == "assistant" and b.get("type") == "tool_use":
                calls[b["id"]] = {"tool": b["name"].removeprefix(PREFIX), "args": b.get("input") or {},
                                  "out": "", "out_chars": 0, "is_error": False}
                order.append(b["id"])
            elif e.get("type") == "user" and b.get("type") == "tool_result" and b.get("tool_use_id") in calls:
                c = b.get("content")
                text = c if isinstance(c, str) else "\n".join(
                    x.get("text", "") for x in c or [] if isinstance(x, dict))
                calls[b["tool_use_id"]].update(out=text, out_chars=len(text), is_error=bool(b.get("is_error")))
    return [calls[i] for i in order]


def cost_by_prices(model_usage: dict, prices: dict) -> float | None:
    """USD from tests/bot_eval/prices.json ({model: {input, output, cache_read, cache_write} per Mtok}).
    None when the file is absent or a model is missing from it."""
    if not prices:
        return None
    total = 0.0
    for model, u in model_usage.items():
        p = prices.get(model)
        if not p:
            return None
        total += (u.get("inputTokens", 0) * p["input"] + u.get("outputTokens", 0) * p["output"]
                  + u.get("cacheReadInputTokens", 0) * p["cache_read"]
                  + u.get("cacheCreationInputTokens", 0) * p["cache_write"]) / 1e6
    return round(total, 6)


# ── the listener's configuration for one scenario ───────────────────────────

def eval_claude(config, tier: str, model: str, extra_allow: list[str], max_budget: float):
    """The tier's ClaudeConfig as the listener loads it, minus Write/Edit and unsafe_allow."""
    if tier == listener.PUBLIC and config.public is None:
        sys.exit("tier public requested but discord-listener.toml has no enabled [public] section "
                 "(the listener would silently use the trusted tier).")
    claude = listener.claude_for(config, tier)
    allowed = [t for t in claude.allowed_tools
               if t.split("(")[0] not in ("Write", "Edit", "NotebookEdit")]
    allowed += [t for t in extra_allow if t not in allowed]
    return dataclasses.replace(
        claude, allowed_tools=tuple(allowed), unsafe_allow=(),
        model=model or claude.model, max_budget_usd=max_budget)


def tier_of(s: dict, override: str) -> str:
    return override or (listener.PUBLIC if s["tier"] == "public" else listener.TRUSTED)


def prompt_files(claude, s: dict, first: bool) -> tuple[list, bool]:
    """(files, is_memory) pasted into the first prompt, as `Listener.first_turn_files` does:
    the tier's first_turn_files, and in a DM the person's memory (here the scenario's text)."""
    if not first:
        return [], False
    files = listener.read_first_turn_files(claude)
    if s["context"] == "dm" and s["memory"]:
        files.append((f"towns/_bot/memory/{SYNTH_USER}.md", s["memory"], ""))
        return files, True
    return files, False


def run_turn(claude, s: dict, turn: dict, index: int, session: str, channel: str, now_iso: str,
             work: Path, dry: bool) -> dict:
    """One `claude -p` turn of a scenario; the record written to the run file."""
    first = index == 0
    # The server's inputs: the temporary files and manifest live in `work`, outside towns/.
    files_path = work / f"files-{index}.json"
    files_path.write_text(json.dumps(scenario_files(s)), encoding="utf-8")
    manifest_path = work / f"manifest-{index}.txt"
    config_path = work / f"mcp-{index}.json"
    config_path.write_text(json.dumps(mcp_config(
        s["fixture"], clock=s["clock"], user=SYNTH_USER, context=s["context"],
        files=str(files_path), manifest=str(manifest_path))), encoding="utf-8")
    cl = dataclasses.replace(claude, mcp_config=(config_path,))
    settings_path = work / f"settings-{index}.json"
    settings = listener.settings_payload(cl)
    # The user-level CLAUDE.md is loaded even with --setting-sources project (measured 2026-11-20:
    # the bot saw the maintainer's other projects). The Pi has none; the project CLAUDE.md stays,
    # as in production.
    settings["claudeMdExcludes"] = [str(Path.home() / ".claude" / "CLAUDE.md")]
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    when = datetime.datetime.fromisoformat(now_iso) + datetime.timedelta(minutes=2 * index)
    message = {"id": listener.snowflake_at(int(when.timestamp() * 1000)),
               "timestamp": when.isoformat(timespec="seconds"),
               "author": "Tester", "author_id": SYNTH_USER, "content": turn["text"]}
    files, is_memory = prompt_files(cl, s, first)
    prompt = listener.build_prompt([message], first, channel, files=files,
                                   where=s["context"], memory=is_memory)
    argv = listener.claude_argv(cl, session, not first, settings_path)
    # The maintainer's PC has the project skills (.claude/commands, .claude/skills: build-plan,
    # inspect-town...); the Pi checkout has none, so the deployed bot cannot launch them. Measured
    # 2026-11-20: both models called Skill("build-plan") in A1/B1 here. Off, as on the Pi (the
    # listener passes it itself since discord_mcp 2026-11-20; kept for an older checkout).
    if "--disable-slash-commands" not in argv:
        argv.append("--disable-slash-commands")
    env = listener.child_env(dict(os.environ), SYNTH_USER, s["context"])
    # The CLI loads this machine's auto-memory for the cwd's project (~/.claude/projects/<cwd>/memory)
    # even with --setting-sources project; on the maintainer's PC that is a full index of private
    # project notes, on the Pi it is empty. Measured 2026-11-20: Haiku tried to Read one of those
    # files in R1. Off, so the bot sees what the deployed listener sees.
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    record = {"lang": turn.get("lang", ""), "prompt": prompt, "user_text": turn["text"],
              "resume": not first}
    if dry:
        record["argv"] = [a if len(a) < 300 else a[:300] + f"...[{len(a)} chars]" for a in argv]
        return record
    t0 = time.time()
    timed_out = False
    try:
        p = subprocess.run(argv, input=prompt, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=cl.cwd, env=env, timeout=cl.timeout_seconds)
        stdout, stderr, code = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code, timed_out = (exc.stdout or "") if isinstance(exc.stdout, str) else "", "", None, True
    secs = round(time.time() - t0, 1)
    res = listener.parse_claude_result(stdout, stderr, code, timed_out)
    events = listener._jsonl(stdout)
    data = res.data or {}
    record.update(
        ok=res.ok, kind=res.kind,
        answer=res.text if res.ok else "",
        error="" if res.ok else res.text,
        trace=trace_of(events), secs=secs,
        num_turns=data.get("num_turns"),
        usage=listener.usage_numbers(data, res.context_tokens) if data else {},
        model_usage=data.get("modelUsage") or {},
        cli_cost_usd=data.get("total_cost_usd"),   # as reported by the CLI; not trusted for cost
        permission_denials=data.get("permission_denials") or [],
        manifest=manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None,
        stderr_tail=stderr.strip()[-600:])
    return record


def run_scenario(config, s: dict, args, repeat: int, now_iso: str) -> dict:
    tier = tier_of(s, args.tier)
    claude = eval_claude(config, tier, args.model, args.allow_extra, args.max_budget)
    # tools_any: a list of names, or a list of lists (grade.py tool_groups)
    wanted = [t for g in s["tools_any"] for t in ([g] if isinstance(g, str) else g)]
    missing = [PREFIX + t for t in wanted if PREFIX + t not in claude.allowed_tools]
    if missing:
        print(f"  WARNING {s['id']}: not in the {tier} allowed_tools of discord-listener.toml "
              f"(the model will be denied them): {', '.join(missing)}", file=sys.stderr)
    session = str(uuid.uuid4())
    out = {"id": s["id"], "repeat": repeat, "fixture": s["fixture"], "tier": tier,
           "context": s["context"], "turns": []}
    with tempfile.TemporaryDirectory(prefix="bot-eval-run-") as w:
        for i, turn in enumerate(s["turns"]):
            r = run_turn(claude, s, turn, i, session, CHANNEL, now_iso, Path(w), args.dry_run)
            out["turns"].append(r)
            if not args.dry_run and not r["ok"]:
                break   # later turns would resume a session that has no answer
    return out


# ── the run ─────────────────────────────────────────────────────────────────

def select(args) -> list[dict]:
    try:
        every = load_all()
    except ScenarioError as exc:
        sys.exit(str(exc))
    if args.only:
        wanted = [x for x in args.only.split(",") if x]
        known = {s["id"] for s in every}
        if bad := [x for x in wanted if x not in known]:
            sys.exit(f"unknown scenario id(s): {', '.join(bad)} (have: {', '.join(sorted(known))})")
        return [s for s in every if s["id"] in wanted]
    return [s for s in every if args.suite == "all" or s["suite"] == args.suite]


def summary_line(r: dict) -> str:
    turns = r["turns"]
    last = turns[-1]
    # ToolSearch (loading a deferred tool's schema) is not a game tool call; the trace keeps it.
    calls = sum(1 for t in turns for c in t.get("trace", []) if c["tool"] != "ToolSearch")
    secs = round(sum(t.get("secs", 0) for t in turns), 1)
    langs = ",".join(t["lang"] for t in turns)
    tok = {"in": 0, "out": 0, "cache": 0}
    cost = 0.0
    for t in turns:
        u = t.get("usage") or {}
        tok["in"] += u.get("input_tokens") or 0
        tok["out"] += u.get("output_tokens") or 0
        tok["cache"] += (u.get("cache_read") or 0) + (u.get("cache_created") or 0)
        cost += t.get("cli_cost_usd") or 0
    note = "" if last.get("ok", True) else f"{last['kind']}: {last['error'][:60]}"
    return (f"{r['id']:<5}{langs:<8}{calls:<7}{secs:<8}{len(last.get('answer', '')):<10}"
            f"{tok['in']}/{tok['out']}/{tok['cache']:<12}${cost:<9.4f}{note}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", default="core", choices=["core", "extended", "all"])
    ap.add_argument("--only", default="")
    ap.add_argument("--model", default="", help="full model id, e.g. claude-haiku-5-5 (alias haiku is an older model)")
    ap.add_argument("--tier", default="", choices=["", "public", "trusted"])
    ap.add_argument("--label", default="run")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--allow-extra", action="append", default=[],
                    help="a tool missing from this machine's discord-listener.toml, as the deployed one has it")
    ap.add_argument("--max-budget", type=float, default=3.0, help="USD per turn, passed as --max-budget-usd")
    ap.add_argument("--dry-run", action="store_true", help="build prompts, argv and configs; no claude call, no file")
    args = ap.parse_args()
    if args.repeat < 1:
        sys.exit("--repeat must be >= 1")
    if args.repeat > 1 and not args.only:
        sys.exit("REPEAT>1 needs ONLY=<ids> (budget rule, plan 6.2).")
    if not TOML.is_file():
        sys.exit(f"{TOML} not found (private file; see discord-listener.example.toml)")
    try:
        config = listener.load_config(TOML)
    except listener.ConfigError as exc:
        sys.exit(f"discord-listener.toml: {exc}")
    scenarios = select(args)
    if not scenarios:
        sys.exit("no scenario selected")
    allow_extra = [t if t.startswith("mcp__") else PREFIX + t for t in args.allow_extra]
    args.allow_extra = allow_extra

    before = real_towns_state()
    tier_of_first = tier_of(scenarios[0], args.tier)
    base = eval_claude(config, tier_of_first, args.model, allow_extra, args.max_budget)
    fixtures = sorted({s["fixture"] for s in scenarios})
    prices = json.loads(PRICES.read_text()) if PRICES.is_file() else {}
    dirty = git("status", "--porcelain")
    meta = {
        "label": args.label, "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "suite": args.suite if not args.only else f"only:{args.only}", "repeat": args.repeat,
        "git_sha": git("rev-parse", "HEAD"), "git_dirty": bool(dirty),
        "git_dirty_files": dirty.splitlines()[:30],
        "model_requested": base.model, "tier_override": args.tier or None,
        "cli_version": cli_version(),
        "system_prompt_sha256": {t: sha256(eval_claude(config, t, args.model, allow_extra, args.max_budget)
                                           .system_prompt.encode())
                                 for t in sorted({tier_of(s, args.tier) for s in scenarios})},
        "toml_sha256": sha256(TOML.read_bytes()),
        "allowed_tools": {t: list(eval_claude(config, t, args.model, allow_extra, args.max_budget).allowed_tools)
                          for t in sorted({tier_of(s, args.tier) for s in scenarios})},
        "extra_allowed": allow_extra, "max_budget_usd_per_turn": args.max_budget,
        "fixture_sha256": {f: tree_hash(ROOT / "towns" / "_eval" / "fixtures" / f) for f in fixtures},
        "wiki_processed_sha256": tree_hash(ROOT / "wiki" / "processed") if (ROOT / "wiki" / "processed").is_dir() else None,
        "scenario_sha256": {s["id"]: sha256(json.dumps(s, sort_keys=True).encode()) for s in scenarios},
        "prices_file": PRICES.name if prices else None,
    }
    print(f"suite={meta['suite']} model={meta['model_requested']} tier={args.tier or 'per scenario'} "
          f"label={args.label} sha={meta['git_sha'][:7]}{'+dirty' if dirty else ''} cli={meta['cli_version']}",
          file=sys.stderr)

    results: list[dict] = []
    out_path = None
    if not args.dry_run:
        RUNS.mkdir(parents=True, exist_ok=True)
        stem = f"{datetime.date.today():%Y-%m-%d}-{args.label}-{base.model}"
        out_path = RUNS / f"{stem}.json"
        n = 2
        while out_path.exists():
            out_path = RUNS / f"{stem}-{n}.json"
            n += 1
    print(f"{'ID':<5}{'lang':<8}{'calls':<7}{'secs':<8}{'out_chars':<10}{'tok in/out/cache':<20}{'cli cost':<10}note")
    for s in scenarios:
        now_iso = frozen_time(s["fixture"], s["clock"])
        for rep in range(1, args.repeat + 1):
            r = run_scenario(config, s, args, rep, now_iso)
            results.append(r)
            if args.dry_run:
                print(f"{s['id']}: dry run, {len(r['turns'])} turn(s)")
                for t in r["turns"]:
                    print(json.dumps({k: t[k] for k in ("argv",)}, ensure_ascii=False, indent=1))
                    print(t["prompt"])
                continue
            print(summary_line(r), flush=True)
            write_run(out_path, meta, results, None)   # partial runs survive

    if args.dry_run:
        return 0
    after = real_towns_state()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    guard = {"ok": not changed, "changed": changed[:50]}
    write_run(out_path, meta, results, guard)
    totals = totals_of(results, prices)
    print(totals["text"])
    print(f"run file: {out_path}")
    if changed:
        print(f"FLAGGED: the real towns/ changed during the run ({len(changed)} path(s), first: {changed[:5]}). "
              "Nothing in an eval run may write there; check the listener / refresh timers before trusting the run.")
        return 2
    return 0


def totals_of(results: list[dict], prices: dict) -> dict:
    keys = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
    per_model: dict[str, dict] = {}
    for r in results:
        for t in r["turns"]:
            for model, u in (t.get("model_usage") or {}).items():
                acc = per_model.setdefault(model, dict.fromkeys(keys, 0))
                for k in keys:
                    acc[k] += u.get(k, 0)
    cli = round(sum(t.get("cli_cost_usd") or 0 for r in results for t in r["turns"]), 4)
    secs = round(sum(t.get("secs", 0) for r in results for t in r["turns"]), 1)
    price = cost_by_prices(per_model, prices)
    lines = [f"tokens by model: {json.dumps(per_model)}",
             f"CLI-reported cost (not trusted for Haiku 5.5): ${cli} · wall {secs}s"]
    if price is not None:
        lines.append(f"cost by prices.json: ${price}")
    return {"per_model": per_model, "cli_cost_usd": cli, "secs": secs, "cost_by_prices_usd": price,
            "text": "\n".join(lines)}


def write_run(path: Path, meta: dict, results: list[dict], guard: dict | None) -> None:
    doc = {"meta": meta, "real_towns_guard": guard, "scenarios": results}
    if guard is not None:
        doc["totals"] = totals_of(results, json.loads(PRICES.read_text()) if PRICES.is_file() else {})
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
