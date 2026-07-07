"""Pluggable verification - the ground truth for the self-improvement loop.

Beyond pytest, it auto-detects the project type and runs the right checks
(JS/TS, Go, Rust), plus optional linting. A check whose tool isn't installed is
skipped (not failed), so a Python-only box doesn't fail a JS project it can't
build. Configure with verify.checks (["auto"] detects; or list explicit checks).
"""
import os
import subprocess
import sys

from sandbox.runner import _sandbox_env

CHECK_CMDS = {
    "pytest": [sys.executable, "-m", "pytest", "-x", "-q"],
    "lint": [sys.executable, "-m", "ruff", "check", "."],
    "npm-test": ["npm", "test", "--silent"],
    "go-test": ["go", "test", "./..."],
    "cargo-test": ["cargo", "test", "--quiet"],
}


def _has_py_tests(workspace: str) -> bool:
    for _r, _d, files in os.walk(workspace):
        for n in files:
            if n.endswith(".py") and (n.startswith("test_") or n.endswith("_test.py")):
                return True
    return False


def detect_checks(workspace: str, config: dict) -> list:
    configured = config.get("verify", {}).get("checks", ["auto"])
    if configured != ["auto"]:
        return configured
    found = []
    if _has_py_tests(workspace):
        found.append("pytest")
    if os.path.exists(os.path.join(workspace, "package.json")):
        found.append("npm-test")
    if os.path.exists(os.path.join(workspace, "go.mod")):
        found.append("go-test")
    if os.path.exists(os.path.join(workspace, "Cargo.toml")):
        found.append("cargo-test")
    return found


def verify(workspace: str, config: dict) -> dict:
    """Return {ran, passed, report}. ran=False means no automated ground truth."""
    timeout = config.get("verify", {}).get("timeout", 120)
    checks = detect_checks(workspace, config)
    ran_any, ok, reports = False, True, []
    for check in checks:
        cmd = CHECK_CMDS.get(check)
        if not cmd:
            continue
        try:
            proc = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True,
                                  timeout=timeout, env=_sandbox_env())
        except FileNotFoundError:
            reports.append(f"[{check}] skipped (tool not installed)")
            continue
        except subprocess.TimeoutExpired:
            reports.append(f"[{check}] FAIL (timed out)")
            ran_any, ok = True, False
            continue
        passed = proc.returncode == 0
        ran_any = True
        ok = ok and passed
        reports.append(f"[{check}] {'PASS' if passed else 'FAIL'}")
    return {"ran": ran_any, "passed": ok if ran_any else False,
            "report": "\n".join(reports) or "no checks detected"}
