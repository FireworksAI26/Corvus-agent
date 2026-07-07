#!/usr/bin/env python3
"""Corvus - a self-improving autonomous coding agent.

Usage:
  corvus                       interactive terminal (same as: corvus chat)
  corvus chat                  interactive terminal
  corvus run "task"            solve a task, then keep chatting about the result
  corvus bench                 run the eval suite to measure improvement
  corvus init                  write a default config.yaml here
  corvus schedule "task" --at "2026-07-08 09:00"   run a task at a time/date
  corvus schedule "task" --in 2h                   run a task after a delay (m/h/d)
  corvus schedule --list                           show scheduled tasks
  corvus scheduler             start the loop that runs due tasks

Terminal commands:
  /lessons            show banked lessons (highest score first)
  /memories           show the agent's self-saved memories
  /skills             count reusable skills in the library
  /models             show model suggestions for the current provider
  /model [name]       pick a model from the list, or type any model id yourself
  /provider [name]    pick a provider from the list, or type one; then choose a model
                      (ollama, openai, anthropic, cloudflare, codex, groq, mistral,
                       deepseek, xai, gemini, openrouter, together, openai-compatible)
  /grant              allow the agent to run commands on YOUR computer (y/N per command)
  /revoke             take that permission away
  /allow <glob>       auto-approve matching single commands (e.g. /allow git *)
  /allowlist          show the current auto-approve patterns
  /repo <path>        work on an existing project folder (real-repo mode); /repo off to exit
  /ship <dest>        copy the verified sandbox project to a folder (git-inits it)
  /task <task>        (in run mode) start another task
  /help               show this help
  /quit               exit

Skills & checkpoints:
  corvus skills list | export [file] | import <file-or-url>
  corvus checkpoint save <name> | load <name> | list

Install the `corvus` command:  pip install -e .
"""
import argparse

import models
from settings import load_config, write_default_config


def _make_agent(config):
    from agent.core import Agent
    return Agent(config)


def _switch(agent, config, provider=None, model=None):
    from agent.llm import make_llm
    old = (config.get("provider"), config.get("model"))
    if provider:
        config["provider"] = provider
    if model:
        config["model"] = model
    try:
        agent.llm = make_llm(config)
        print(f"Now using provider={config['provider']} model={config['model']}")
    except (RuntimeError, ValueError) as err:
        config["provider"], config["model"] = old
        print(f"Switch failed, keeping previous settings: {err}")


def _print_outcome(outcome, success, reflection):
    print(f"\nResult ({outcome['steps']} steps):\n{outcome['result']}")
    print(f"Verification (pytest): {'PASS' if success else 'FAIL'}")
    for lesson in reflection.get("lessons", []):
        print(f"Lesson banked: {lesson}")
    print()


def _trace_step(step, observation):
    """Live progress line for each agent step (streamed to the terminal)."""
    if "final_answer" in step:
        return
    tool = step.get("tool", "?")
    args = step.get("args", {})
    preview = ", ".join(f"{k}={str(v)[:40]}" for k, v in args.items())
    first_line = (observation or "").splitlines()[0] if observation else ""
    print(f"  → {tool}({preview})")
    if first_line:
        print(f"    {first_line[:100]}")


def _maybe_route(agent, config, task):
    r = config.get("routing", {})
    if r.get("enabled") and r.get("cheap") and r.get("strong"):
        chosen = models.route(task, r["cheap"], r["strong"])
        if chosen and chosen != config.get("model"):
            _switch(agent, config, model=chosen)


def _solve(agent, config, task):
    from agent.session import solve_and_learn
    _maybe_route(agent, config, task)
    repo_path = config.get("_repo_active")
    outcome, success, reflection = solve_and_learn(
        agent, config, task,
        on_attempt=lambda a, m: print(f"Attempt {a}/{m}..." if m > 1 else "Working..."),
        on_step=_trace_step,
        reset_workspace=not repo_path,   # never wipe a real project
        harvest=not repo_path,           # don't bank a project's own files as skills
    )
    # In real-repo mode, snapshot verified changes so the session is revertible.
    if repo_path and success and config.get("repo", {}).get("autocommit", True):
        import repo as repo_git
        if repo_git.ensure_repo(repo_path) and repo_git.commit_all(repo_path, task[:60]):
            print(f"  ✓ committed to {repo_path} (undo with: corvus repo revert)")
    return outcome, success, reflection


def _enter_repo(config, path):
    """Point the agent at an existing project folder (real-repo mode)."""
    import os

    from agent import tools
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        print(f"No such directory: {path}")
        return False
    tools.set_workspace(path)
    config["_repo_active"] = path
    print(f"Real-repo mode ON → {path}\n  Corvus now reads/writes files here (confined to this folder).")
    return True


def _exit_repo(config):
    from agent import tools
    tools.set_workspace("workspace")
    config["_repo_active"] = None
    print("Real-repo mode OFF → back to the sandbox workspace.")


def _stream_reply(agent, history):
    """Stream the assistant reply to the terminal live; return the full text."""
    import sys

    from agent.llm import stream_text
    text = stream_text(agent.llm, history,
                       sink=lambda c: (sys.stdout.write(c), sys.stdout.flush()))
    print("\n")
    return text


def _followup(agent, config, task, outcome):
    """Conversation mode after `corvus run`: discuss the result, refine, or start new tasks."""
    print("Chat about the result below. /task <new task> runs another task, /quit exits.\n")
    history = [
        {"role": "system", "content": (
            "You are Corvus, a helpful coding agent. You just completed a task for the user. "
            "Discuss the result, explain decisions, and help plan refinements. Be concise.")},
        {"role": "user", "content": f"Task: {task}\n\nOutcome: {outcome['result']}"},
        {"role": "assistant", "content": "Done. Ask me anything about it, or give me a follow-up."},
    ]
    while True:
        try:
            line = input("corvus> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("/quit", "/exit"):
            break
        if line.startswith("/task "):
            new_task = line[len("/task "):].strip()
            outcome, success, reflection = _solve(agent, config, new_task)
            _print_outcome(outcome, success, reflection)
            history.append({"role": "user", "content": f"New task completed: {new_task}\nOutcome: {outcome['result']}"})
            history.append({"role": "assistant", "content": "Done. What next?"})
            continue
        if line.startswith("/ship "):
            dest = line[len("/ship "):].strip()
            import promote
            from agent import tools
            res = promote.promote(tools.WORKSPACE, dest, do_git=True)
            if res.get("error"):
                extra = "  (add nothing to overwrite, or use: corvus ship <dest> --force)" \
                    if res.get("conflicts") else ""
                print("Cannot ship: " + res["error"] + extra)
            else:
                print(f"Shipped {res['copied']} files to {res['dest']}" +
                      (" and initialized a git repo." if res["git"] else "."))
            continue
        history.append({"role": "user", "content": line})
        try:
            reply = _stream_reply(agent, history)
        except Exception as err:
            print(f"Error: {err}")
            history.pop()
            continue
        history.append({"role": "assistant", "content": reply})


def cmd_run(task: str, repo_path: str | None = None):
    config = load_config()
    agent = _make_agent(config)
    if repo_path or config.get("repo", {}).get("path"):
        _enter_repo(config, repo_path or config["repo"]["path"])
    print(f"Provider: {config['provider']} | Model: {config['model']}\nTask: {task}\n")
    outcome, success, reflection = _solve(agent, config, task)
    _print_outcome(outcome, success, reflection)
    _followup(agent, config, task, outcome)


def cmd_team(task: str):
    """Run a task with the planner -> coder -> reviewer team."""
    from agent.orchestrator import solve_with_team
    config = load_config()
    agent = _make_agent(config)
    print(f"Provider: {config['provider']} | Model: {config['model']}\nTeam task: {task}\n")
    res = solve_with_team(agent, config, task, on_step=_trace_step)
    print(f"\nPlan:\n{res['plan']}\n")
    _print_outcome(res["outcome"], res["success"], res["reflection"])
    review = res["review"]
    print(f"Reviewer: {'approved' if review['approved'] else 'changes requested'}"
          f"  (rounds: {res['review_rounds']})")
    if review.get("feedback"):
        print(f"  {review['feedback']}")


def cmd_verify(args):
    """Run the project's verification checks (pytest/lint/JS/Go/Rust) on a path."""
    import os

    import verifier
    path = os.path.abspath(os.path.expanduser(args.path or "."))
    result = verifier.verify(path, load_config())
    print(result["report"])
    print("VERIFIED ✓" if (result["ran"] and result["passed"])
          else ("FAILED" if result["ran"] else "no automated checks detected"))


def cmd_stats():
    """Summarize past runs (pass rate, steps, time, tokens, by model)."""
    import telemetry
    s = telemetry.stats(load_config())
    if not s.get("runs"):
        print("No runs recorded yet. Run some tasks first.")
        return
    print(f"Runs: {s['runs']}   pass rate: {s['pass_rate']:.0%}   "
          f"avg steps: {s['avg_steps']:.1f}   avg time: {s['avg_seconds']:.1f}s   "
          f"~tokens: {s['tokens_est']:,}")
    for model, b in s["by_model"].items():
        print(f"  {model}: {b['passed']}/{b['runs']} passed")


def cmd_plan(args):
    """Show plan entitlements and the fairness policy."""
    import plan as plan_mod
    name = args.name or load_config().get("plan", "free")
    print(plan_mod.summary(name))


def cmd_ship(args):
    """Copy the verified sandbox project to a folder on the user's machine."""
    import promote
    from agent import tools
    source = args.from_ or tools.WORKSPACE
    res = promote.promote(source, args.dest, force=args.force,
                          do_git=args.git, dry_run=args.dry_run)
    if res.get("error"):
        print("Cannot ship: " + res["error"])
        for c in res.get("conflicts", [])[:20]:
            print("   would overwrite: " + c)
        return
    if res.get("dry_run"):
        print(f"Would copy {len(res['files'])} files to {res['dest']}:")
        for r in res["files"][:60]:
            print("   " + r)
        if res["conflicts"]:
            print(f"   ({len(res['conflicts'])} already exist there - needs --force)")
        return
    msg = f"Shipped {res['copied']} files to {res['dest']}"
    if res["git"]:
        msg += " (git repo initialized + first commit made)"
    print(msg)


def cmd_memory(args):
    """Inspect the memory backend or migrate learned state between backends."""
    from memory._client import COLLECTIONS, active_backend, build_client
    path = load_config()["memory"]["path"]
    if args.action == "info":
        backend = active_backend()
        client = build_client(backend, path)
        print(f"Active memory backend: {backend}   (path: {path})")
        for name in COLLECTIONS:
            print(f"  {name}: {client.get_or_create_collection(name).count()}")
    elif args.action == "migrate":
        from memory._client import migrate
        if not args.to:
            print("Specify --to lite|chroma")
            return
        try:
            moved = migrate(path, args.to)
        except RuntimeError as err:
            print(err)
            return
        total = sum(moved.values())
        print(f"Migrated {total} records to '{args.to}': " +
              ", ".join(f"{k}={v}" for k, v in moved.items()))
        print(f"Now set  memory.backend: {args.to}  in config.yaml (or export "
              f"CORVUS_MEMORY_BACKEND={args.to}).")


def cmd_repo(args):
    """Inspect / undo Corvus's changes in a project (git-backed real-repo mode)."""
    import os

    import repo as repo_git
    path = os.path.abspath(os.path.expanduser(args.path or "."))
    if not repo_git.is_git_repo(path):
        print(f"{path} is not a git repo (real-repo commits need git).")
        return
    if args.action == "diff":
        print(repo_git.diff(path))
    elif args.action == "log":
        print(repo_git.log(path))
    elif args.action == "revert":
        print(repo_git.revert_last(path))


def cmd_init():
    if write_default_config():
        print("Wrote config.yaml - edit it to pick your provider and model.")
    else:
        print("config.yaml already exists, leaving it untouched.")


def cmd_models():
    """Print model suggestions for every provider (you can also type your own)."""
    for provider in models.PROVIDERS:
        options = models.models_for(provider)
        shown = ", ".join(options) if options else "(type any model id your endpoint serves)"
        print(f"{provider}:\n  {shown}")
    print("\nThese are suggestions - in the terminal, /model lets you pick one or "
          "type any model id your provider supports.")


def cmd_skills(args):
    import json
    from memory.skills import SkillStore
    store = SkillStore(load_config()["memory"]["path"])
    if args.action == "list":
        named = store.list_named()
        print("\n".join(named) if named else
              "(no named skills yet - the agent builds them with its build_skill tool)")
        print(f"{store.count()} total skills including auto-harvested")
    elif args.action == "export":
        path = args.path or "skills-export.json"
        with open(path, "w") as f:
            json.dump(store.export_named(), f, indent=2)
        print(f"Exported to {path} - share it with the community!")
    elif args.action == "import":
        if not args.path:
            print("Provide a file path or URL to import from")
            return
        try:
            if args.path.startswith(("http://", "https://")):
                import requests
                resp = requests.get(args.path, timeout=30)
                resp.raise_for_status()
                entries = resp.json()
            else:
                with open(args.path) as f:
                    entries = json.load(f)
        except FileNotFoundError:
            print(f"No such file: {args.path}")
            return
        except (OSError, ValueError) as err:  # bad JSON, network, etc.
            print(f"Could not import from {args.path}: {err}")
            return
        if not isinstance(entries, list):
            print("Import source must be a JSON list of skill objects.")
            return
        print(f"Imported {store.import_entries(entries)} new skills")


def cmd_checkpoint(args):
    import checkpoints
    memory_path = load_config()["memory"]["path"]
    if args.action == "list":
        items = checkpoints.list_checkpoints()
        print("\n".join(items) if items else "(no checkpoints yet)")
        return
    if not args.name:
        print("Provide a checkpoint name")
        return
    try:
        if args.action == "save":
            checkpoints.save(args.name, memory_path)
            print(f"Checkpoint '{args.name}' saved. Start a new conversation from it "
                  f"anytime with: corvus checkpoint load {args.name}")
        else:
            checkpoints.load(args.name, memory_path)
            print(f"Checkpoint '{args.name}' loaded - new conversations now start from "
                  f"this learned state (previous memory kept at {memory_path}.backup).")
    except ValueError as err:
        print(err)


def cmd_schedule(args):
    from datetime import datetime
    from scheduler import add, format_items, parse_when
    if args.list:
        lines = format_items()
        print("\n".join(lines) if lines else "(no scheduled tasks)")
        return
    if not args.task:
        print("Provide a task plus --at or --in. Example: corvus schedule \"fix bug\" --in 2h")
        return
    try:
        when = parse_when(at=args.at, in_=args.in_)
    except ValueError as err:
        print(err)
        return
    item = add(" ".join(args.task), when)
    stamp = datetime.fromtimestamp(when).strftime("%Y-%m-%d %H:%M")
    print(f"Scheduled #{item['id']} for {stamp}. Start `corvus scheduler` to run due tasks.")


def cmd_scheduler():
    import time as _time
    from scheduler import run_loop
    config = load_config()
    agent = _make_agent(config)
    print("Scheduler running - due tasks execute automatically. Ctrl+C to stop.")

    def runner(task):
        stamp = _time.strftime("%H:%M:%S")
        print(f"\n[{stamp}] Running scheduled task: {task}")
        outcome, success, reflection = _solve(agent, config, task)
        _print_outcome(outcome, success, reflection)

    try:
        run_loop(runner)
    except KeyboardInterrupt:
        print("\nScheduler stopped.")


def cmd_chat():
    config = load_config()
    try:
        agent = _make_agent(config)
    except RuntimeError as err:  # e.g. missing API key
        print(f"Setup error: {err}")
        return

    print("Corvus - self-improving coding agent")
    print(f"provider={config['provider']} model={config['model']}")
    print("Type a coding task, or /help for commands.\n")

    while True:
        try:
            line = input("corvus> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("/quit", "/exit"):
            break
        if line == "/help":
            print(__doc__)
            continue
        if line == "/lessons":
            lessons = agent.lessons.all()
            print("\n".join(lessons) if lessons else "(no lessons banked yet)")
            continue
        if line == "/memories":
            notes = agent.notes.all()
            print("\n".join(f"- {n}" for n in notes) if notes else "(no memories saved yet)")
            continue
        if line == "/skills":
            print(f"{agent.skills.count()} verified skills in the library")
            continue
        if line == "/models":
            print(models.render_model_menu(config["provider"], config["model"]))
            continue
        if line == "/model":  # no arg -> interactive picker (or type your own)
            print(models.render_model_menu(config["provider"], config["model"]))
            try:
                choice = input("model> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            if not choice:
                continue
            model = models.resolve_model_choice(choice, models.models_for(config["provider"]))
            if not model:
                print("Invalid choice - pick a listed number or type a model id.")
                continue
            _switch(agent, config, model=model)
            continue
        if line.startswith("/model "):
            _switch(agent, config, model=line.split(maxsplit=1)[1])
            continue
        if line == "/provider":  # no arg -> pick a provider, then its models
            print(models.render_provider_menu(config["provider"]))
            try:
                choice = input("provider> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            if not choice:
                continue
            provider = models.resolve_provider_choice(choice)
            if not provider:
                print("Invalid choice - pick a listed number or type a provider name.")
                continue
            _switch(agent, config, provider=provider)
            print(models.render_model_menu(config["provider"], config["model"]))
            continue
        if line.startswith("/provider "):
            _switch(agent, config, provider=line.split(maxsplit=1)[1])
            print(models.render_model_menu(config["provider"], config["model"]))
            continue
        if line == "/grant":
            agent.ctx.computer["enabled"] = True
            print("Computer control GRANTED for this session. Every command still asks "
                  "y/N before running. Use /revoke to disable.")
            continue
        if line == "/revoke":
            agent.ctx.computer["enabled"] = False
            print("Computer control revoked.")
            continue
        if line == "/repo" or line == "/repo off":
            _exit_repo(config) if line.endswith("off") else print(
                f"Real-repo mode: {config.get('_repo_active') or 'off'}  (use /repo <path> to set)")
            continue
        if line.startswith("/repo "):
            _enter_repo(config, line.split(maxsplit=1)[1].strip())
            continue
        if line == "/allowlist":
            patterns = agent.ctx.computer.get("allowlist", [])
            print("\n".join(f"- {p}" for p in patterns) if patterns else
                  "(allowlist empty - every command asks y/N)")
            continue
        if line.startswith("/allow "):
            pattern = line.split(maxsplit=1)[1].strip()
            agent.ctx.computer.setdefault("allowlist", []).append(pattern)
            print(f"Allowlisted '{pattern}' for this session - matching single "
                  "commands now skip the y/N prompt (chained commands never do).")
            continue
        if line.startswith("/"):
            print("Unknown command. Try /help")
            continue

        try:
            outcome, success, reflection = _solve(agent, config, line)
        except Exception as err:
            print(f"Error: {err}")
            continue
        _print_outcome(outcome, success, reflection)


def main():
    parser = argparse.ArgumentParser(prog="corvus", description="Corvus - self-improving coding agent")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("chat", help="interactive terminal")
    run_parser = sub.add_parser("run", help="solve a task, then chat about the result")
    run_parser.add_argument("task", nargs="+", help="the coding task to solve")
    run_parser.add_argument("--repo", default=None,
                            help="work on an existing project folder (real-repo mode)")
    repo_parser = sub.add_parser("repo", help="inspect/undo Corvus changes in a project")
    repo_parser.add_argument("action", choices=["diff", "log", "revert"])
    repo_parser.add_argument("path", nargs="?", help="project path (default: current dir)")
    mem_parser = sub.add_parser("memory", help="inspect or migrate the memory backend")
    mem_parser.add_argument("action", choices=["info", "migrate"])
    mem_parser.add_argument("--to", choices=["lite", "chroma"], help="target backend for migrate")
    plan_parser = sub.add_parser("plan", help="show plan entitlements (free = any provider, BYO key)")
    plan_parser.add_argument("name", nargs="?", help="plan: free | pro | team | enterprise")
    verify_parser = sub.add_parser("verify", help="run verification checks on a project")
    verify_parser.add_argument("path", nargs="?", help="project path (default: current dir)")
    team_parser = sub.add_parser("team", help="solve a task with the planner/coder/reviewer team")
    team_parser.add_argument("task", nargs="+", help="the coding task")
    sub.add_parser("stats", help="show run history (pass rate, steps, time, tokens)")
    ship_parser = sub.add_parser("ship", help="copy the verified sandbox project to a folder")
    ship_parser.add_argument("dest", help="destination folder on your machine")
    ship_parser.add_argument("--from", dest="from_", default=None,
                             help="source dir (default: the sandbox workspace)")
    ship_parser.add_argument("--force", action="store_true", help="overwrite existing files")
    ship_parser.add_argument("--git", action="store_true", help="git init + initial commit at dest")
    ship_parser.add_argument("--dry-run", action="store_true", help="preview what would be copied")
    bench_parser = sub.add_parser("bench", help="run the eval suite")
    bench_parser.add_argument("--check", action="store_true",
                              help="exit non-zero if pass rate regressed vs last run")
    sub.add_parser("init", help="write a default config.yaml")
    sub.add_parser("models", help="list model suggestions for every provider")
    serve_parser = sub.add_parser("serve", help="run the HTTP API (backend for the mobile apps)")
    serve_parser.add_argument("--host", default=None, help="bind host (default 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=None, help="bind port (default 8000)")
    sched = sub.add_parser("schedule", help="schedule a task for a time or date")
    sched.add_argument("task", nargs="*", help="the task to schedule")
    sched.add_argument("--at", help="'YYYY-MM-DD HH:MM', 'YYYY-MM-DD', or 'HH:MM'")
    sched.add_argument("--in", dest="in_", help="delay like 30m, 2h, 1d")
    sched.add_argument("--list", action="store_true", help="show scheduled tasks")
    sub.add_parser("scheduler", help="run the loop that executes due tasks")
    skills_parser = sub.add_parser("skills", help="list/export/import shareable skills")
    skills_parser.add_argument("action", choices=["list", "export", "import"])
    skills_parser.add_argument("path", nargs="?", help="file path or URL")
    ckpt_parser = sub.add_parser("checkpoint", help="save/load/list learned-state checkpoints")
    ckpt_parser.add_argument("action", choices=["save", "load", "list"])
    ckpt_parser.add_argument("name", nargs="?", help="checkpoint name")
    args = parser.parse_args()

    if args.command == "run":
        cmd_run(" ".join(args.task), repo_path=args.repo)
    elif args.command == "repo":
        cmd_repo(args)
    elif args.command == "memory":
        cmd_memory(args)
    elif args.command == "ship":
        cmd_ship(args)
    elif args.command == "plan":
        cmd_plan(args)
    elif args.command == "verify":
        cmd_verify(args)
    elif args.command == "team":
        cmd_team(" ".join(args.task))
    elif args.command == "stats":
        cmd_stats()
    elif args.command == "bench":
        from evals.benchmark import main as bench
        bench(check=args.check)
    elif args.command == "init":
        cmd_init()
    elif args.command == "models":
        cmd_models()
    elif args.command == "serve":
        from server import serve
        serve(host=args.host, port=args.port)
    elif args.command == "schedule":
        cmd_schedule(args)
    elif args.command == "scheduler":
        cmd_scheduler()
    elif args.command == "skills":
        cmd_skills(args)
    elif args.command == "checkpoint":
        cmd_checkpoint(args)
    else:
        cmd_chat()


if __name__ == "__main__":
    main()
