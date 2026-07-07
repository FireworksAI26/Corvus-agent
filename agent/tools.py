"""Tools the agent can call during its reason/act loop.

Tool state - the agent's self-saved notes, its skill library, and the
computer-control policy - is carried on a per-agent ToolContext instead of
module globals, so several agents can run in one process (or one test run)
without clobbering each other's state.
"""
import fnmatch
import os
import subprocess

from agent.search import web_search
from sandbox.runner import run_pytest, run_python

WORKSPACE = os.path.abspath("workspace")


def set_workspace(path: str) -> str:
    """Point the file tools at a different root (e.g. an existing project in
    real-repo mode). Path confinement in _safe_path then applies to this root."""
    global WORKSPACE
    WORKSPACE = os.path.abspath(path)
    return WORKSPACE


# Shell operators that chain/redirect commands. A command containing any of
# these is never auto-approved by the allowlist, even if the leading command
# matches - otherwise "git status && rm -rf /" could slip through "git *".
_SHELL_CHAINERS = (";", "&&", "||", "|", "`", "$(", ">", "<", "&", "\n")


def _is_simple_command(command: str) -> bool:
    return not any(op in command for op in _SHELL_CHAINERS)


def command_auto_approved(command: str, allowlist) -> bool:
    """True only if the command matches an allowlist glob AND is a single,
    un-chained command (so allowlisting `git *` can't smuggle in a `; rm`)."""
    cmd = command.strip()
    if not cmd or not _is_simple_command(cmd):
        return False
    return any(fnmatch.fnmatch(cmd, pattern) for pattern in (allowlist or []))


def _safe_path(path: str) -> str:
    full = os.path.abspath(os.path.join(WORKSPACE, path))
    # commonpath (not startswith) so a sibling like ../workspace-evil, which
    # shares the WORKSPACE string prefix, cannot slip through.
    if os.path.commonpath([full, WORKSPACE]) != WORKSPACE:
        raise ValueError("Path escapes workspace")
    return full


def tool_write_file(path: str, content: str) -> str:
    full = _safe_path(path)
    os.makedirs(os.path.dirname(full) or WORKSPACE, exist_ok=True)
    with open(full, "w") as f:
        f.write(content)
    return f"Wrote {len(content)} chars to {path}"


def tool_read_file(path: str) -> str:
    with open(_safe_path(path)) as f:
        return f.read()


def tool_edit_file(path: str, find: str, replace: str) -> str:
    """Surgical edit: replace an exact, unique snippet instead of rewriting the
    whole file. `find` must occur exactly once (safer on large files)."""
    full = _safe_path(path)
    if not os.path.exists(full):
        return f"File not found: {path}"
    with open(full) as f:
        content = f.read()
    count = content.count(find)
    if count == 0:
        return f"`find` snippet not present in {path}; nothing changed. Read the file and match exactly."
    if count > 1:
        return f"`find` matches {count} places in {path}; add surrounding context to make it unique."
    with open(full, "w") as f:
        f.write(content.replace(find, replace, 1))
    return f"Edited {path} (1 replacement, {len(replace) - len(find):+d} chars)."


def tool_list_files(path: str = ".") -> str:
    full = _safe_path(path)
    entries = []
    for root, _, files in os.walk(full):
        for name in files:
            entries.append(os.path.relpath(os.path.join(root, name), WORKSPACE))
    return "\n".join(entries) or "(empty)"


def tool_run_python(code: str, timeout: int = 30) -> str:
    return run_python(code, cwd=WORKSPACE, timeout=timeout)


def tool_run_tests(timeout: int = 60) -> str:
    return run_pytest(cwd=WORKSPACE, timeout=timeout)


def tool_web_search(query: str) -> str:
    return web_search(query)


def tool_search_code(query: str) -> str:
    """Find the most relevant code chunks in the current project/workspace."""
    from index import search_code
    return search_code(query, WORKSPACE, k=5)


class ToolContext:
    """Per-agent tool state: memory handles + computer-control policy."""

    def __init__(self, notes=None, skills=None,
                 computer_enabled: bool = False, computer_confirm: bool = True,
                 computer_allowlist=None):
        self.notes = notes
        self.skills = skills
        self.computer = {"enabled": bool(computer_enabled),
                         "confirm": bool(computer_confirm),
                         "allowlist": list(computer_allowlist or [])}


def _make_remember(ctx: ToolContext):
    def tool_remember(note: str) -> str:
        if ctx.notes is None:
            return "Memory is not available"
        ctx.notes.add(note)
        return f"Remembered: {note}"
    return tool_remember


def _make_recall(ctx: ToolContext):
    def tool_recall(query: str) -> str:
        if ctx.notes is None:
            return "Memory is not available"
        hits = ctx.notes.search(query, k=5)
        return "\n".join(f"- {h}" for h in hits) or "(no matching memories)"
    return tool_recall


def _make_build_skill(ctx: ToolContext):
    def tool_build_skill(name: str, description: str, code: str) -> str:
        """AI skill builder: the agent authors a named, reusable, documented skill."""
        if ctx.skills is None:
            return "Skill library is not available"
        ctx.skills.add_built(name, description, code)
        return f"Skill '{name}' saved to the library for future reuse"
    return tool_build_skill


def _make_computer(ctx: ToolContext):
    def tool_computer(command: str) -> str:
        """Run a command on the USER'S machine - only with explicit permission."""
        if not ctx.computer["enabled"]:
            return ("Computer control is disabled. The user must grant permission first "
                    "(/grant in the terminal, or computer_control.enabled in config.yaml).")
        auto = command_auto_approved(command, ctx.computer.get("allowlist"))
        if ctx.computer["confirm"] and not auto:
            try:
                answer = input(
                    f"\n[PERMISSION] Corvus wants to run this on YOUR computer:\n"
                    f"  $ {command}\nAllow? [y/N] "
                )
            except EOFError:
                return "Permission prompt unavailable; command blocked."
            if answer.strip().lower() != "y":
                return "User denied permission for this command."
        try:
            proc = subprocess.run(command, shell=True, capture_output=True,
                                  text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return "Command timed out after 120s"
        return f"exit_code={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"[:8000]
    return tool_computer


def build_tools(ctx: ToolContext) -> dict:
    """The tool name -> callable map, bound to one agent's context."""
    return {
        "write_file": tool_write_file,
        "read_file": tool_read_file,
        "edit_file": tool_edit_file,
        "list_files": tool_list_files,
        "run_python": tool_run_python,
        "run_tests": tool_run_tests,
        "web_search": tool_web_search,
        "search_code": tool_search_code,
        "remember": _make_remember(ctx),
        "recall": _make_recall(ctx),
        "build_skill": _make_build_skill(ctx),
        "computer": _make_computer(ctx),
    }


# Neutral tool specs -> rendered into OpenAI or Anthropic function schemas for
# providers that support native tool-calling.
_S = "string"
TOOL_SPECS = [
    {"name": "write_file", "description": "Create or overwrite a file in the workspace.",
     "params": {"path": (_S, True), "content": (_S, True)}},
    {"name": "read_file", "description": "Read a file from the workspace.",
     "params": {"path": (_S, True)}},
    {"name": "edit_file", "description": "Replace an exact, unique snippet in a file (surgical edit).",
     "params": {"path": (_S, True), "find": (_S, True), "replace": (_S, True)}},
    {"name": "list_files", "description": "List files in the workspace.",
     "params": {"path": (_S, False)}},
    {"name": "run_python", "description": "Execute a Python snippet; returns stdout/stderr.",
     "params": {"code": (_S, True)}},
    {"name": "run_tests", "description": "Run pytest in the workspace; returns results.",
     "params": {}},
    {"name": "web_search", "description": "Search the web for docs, APIs, and examples.",
     "params": {"query": (_S, True)}},
    {"name": "search_code", "description": "Find the most relevant code in the current project.",
     "params": {"query": (_S, True)}},
    {"name": "remember", "description": "Save an important, reusable insight to long-term memory.",
     "params": {"note": (_S, True)}},
    {"name": "recall", "description": "Search your saved long-term memories.",
     "params": {"query": (_S, True)}},
    {"name": "build_skill", "description": "Save a polished, reusable skill to your library.",
     "params": {"name": (_S, True), "description": (_S, True), "code": (_S, True)}},
    {"name": "computer", "description": ("Run a shell command on the user's machine. "
                                        "Requires explicit permission; use sparingly."),
     "params": {"command": (_S, True)}},
]


def _json_schema(spec: dict) -> dict:
    props = {p: {"type": t} for p, (t, _req) in spec["params"].items()}
    required = [p for p, (_t, req) in spec["params"].items() if req]
    return {"type": "object", "properties": props, "required": required}


def openai_tools() -> list:
    """OpenAI / OpenAI-compatible function-calling schema."""
    return [{"type": "function",
             "function": {"name": s["name"], "description": s["description"],
                          "parameters": _json_schema(s)}}
            for s in TOOL_SPECS]


def anthropic_tools() -> list:
    """Anthropic tool-use schema."""
    return [{"name": s["name"], "description": s["description"],
             "input_schema": _json_schema(s)}
            for s in TOOL_SPECS]


TOOL_DESCRIPTIONS = """
Available tools (call exactly one per step):
- write_file(path, content): create or overwrite a file in the workspace
- read_file(path): read a file from the workspace
- edit_file(path, find, replace): replace an exact, unique snippet (surgical edit; preferred for big files)
- list_files(path="."): list workspace files
- run_python(code): execute a Python snippet, returns stdout/stderr
- run_tests(): run pytest in the workspace, returns results
- web_search(query): search the web for docs, APIs, and examples
- search_code(query): find the most relevant code in the current project/workspace
- remember(note): permanently save an important insight to your long-term memory
- recall(query): search your saved long-term memories
- build_skill(name, description, code): save a polished, reusable skill to your library
- computer(command): run a shell command on the user's machine - requires the user's
  explicit permission and per-command confirmation; use only when truly necessary
"""
