"""Ship a verified sandbox project to a real folder on the user's machine.

The workflow: Corvus drafts + runs + fixes code in the sandbox `workspace/`
until pytest passes, then `corvus ship <dest>` graduates that verified project
to a destination directory - refusing to clobber existing files unless --force,
with a dry-run preview and optional `git init` + initial commit.
"""
import os
import shutil

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git"}


def _iter_files(root: str):
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(".pyc"):
                continue
            full = os.path.join(dirpath, name)
            yield full, os.path.relpath(full, root)


def plan(workspace: str, dest: str):
    files = list(_iter_files(workspace))
    conflicts = [rel for _full, rel in files if os.path.exists(os.path.join(dest, rel))]
    return files, conflicts


def promote(workspace: str, dest: str, force: bool = False,
            do_git: bool = False, dry_run: bool = False) -> dict:
    workspace = os.path.abspath(workspace)
    dest = os.path.abspath(os.path.expanduser(dest))
    if not os.path.isdir(workspace):
        return {"error": f"no sandbox workspace at {workspace}"}
    files, conflicts = plan(workspace, dest)
    if not files:
        return {"error": "the sandbox workspace is empty - run a task first"}
    if dry_run:
        return {"dry_run": True, "dest": dest,
                "files": [rel for _f, rel in files], "conflicts": conflicts}
    if conflicts and not force:
        return {"error": "shipping would overwrite existing files; re-run with --force",
                "conflicts": conflicts}
    for full, rel in files:
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target) or dest, exist_ok=True)
        shutil.copy2(full, target)
    committed = False
    if do_git:
        import repo as repo_git
        if repo_git.ensure_repo(dest):
            committed = repo_git.commit_all(dest, "initial project shipped from corvus")
    return {"dest": dest, "copied": len(files), "git": committed}
