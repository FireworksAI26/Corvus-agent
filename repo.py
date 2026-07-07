"""Git helpers for real-repo mode.

When Corvus works on an existing project (instead of the sandbox workspace),
it commits after every pytest-verified change with a `corvus:` prefix, so the
whole session is a clean, revertible history. All commands are best-effort and
never raise - if git isn't present or the folder isn't a repo, callers fall back.
"""
import subprocess

CORVUS_PREFIX = "corvus: "


def _git(args, cwd):
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                              text=True, timeout=60)
    except (FileNotFoundError, subprocess.SubprocessError):
        class _Fail:
            returncode = 1
            stdout = ""
            stderr = "git unavailable"
        return _Fail()


def is_git_repo(path: str) -> bool:
    r = _git(["rev-parse", "--is-inside-work-tree"], path)
    return r.returncode == 0 and r.stdout.strip() == "true"


def ensure_repo(path: str) -> bool:
    """Make `path` a git repo if it isn't one yet (so we can snapshot safely)."""
    if is_git_repo(path):
        return True
    return _git(["init"], path).returncode == 0


def commit_all(path: str, message: str) -> bool:
    _git(["add", "-A"], path)
    commit = ["commit", "-m", CORVUS_PREFIX + message]
    r = _git(commit, path)
    if r.returncode != 0:
        # No git identity configured on this machine (common on fresh CI runners
        # or a bare box). Retry with a neutral fallback identity just for this
        # commit - the user's own identity is used whenever one is configured.
        r = _git(["-c", "user.name=Corvus",
                  "-c", "user.email=corvus@users.noreply.github.com", *commit], path)
    return r.returncode == 0


def diff(path: str) -> str:
    r = _git(["diff", "HEAD"], path)
    return r.stdout or "(no changes)"


def log(path: str, n: int = 10) -> str:
    r = _git(["log", f"-{n}", "--oneline"], path)
    return r.stdout or "(no history)"


def revert_last(path: str) -> str:
    """Undo the most recent corvus commit (hard reset to its parent)."""
    r = _git(["log", "-1", "--pretty=%s"], path)
    if r.returncode != 0:
        return "No git history to revert."
    if not r.stdout.strip().startswith(CORVUS_PREFIX.strip()):
        return "Most recent commit isn't a corvus commit; not touching it."
    rr = _git(["reset", "--hard", "HEAD~1"], path)
    return "Reverted the last corvus commit." if rr.returncode == 0 else "Revert failed."
