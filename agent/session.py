"""Shared task pipeline: attempt -> verify -> reflect -> retry -> harvest skills.

This is the full self-improvement cycle used by the terminal, one-shot mode,
and the eval suite. If verification fails, the agent's own critique is fed
back and it retries (Reflexion-style), up to improve.max_attempts.

Verification uses pytest as ground truth, but ONLY when the task actually
produced tests. Tasks with no tests (explanations, one-off scripts) have no
automated ground truth, so we accept a completed answer rather than declaring
a false failure and burning retries. The sandbox workspace is reset per task so
stale files can't pollute verification/harvesting - but in real-repo mode the
caller passes reset_workspace=False and harvest=False so the project is left
intact and its files aren't banked as skills.

The workspace root is read from agent.tools at call time (tools.WORKSPACE), so
real-repo mode can repoint it via tools.set_workspace().
"""
import os
import shutil
import time

from agent import tools
from improve.evolve import evolve
from improve.reflect import reflect


def _reset_workspace():
    shutil.rmtree(tools.WORKSPACE, ignore_errors=True)
    os.makedirs(tools.WORKSPACE, exist_ok=True)


def _workspace_has_tests() -> bool:
    if not os.path.isdir(tools.WORKSPACE):
        return False
    for _root, _dirs, files in os.walk(tools.WORKSPACE):
        for name in files:
            if name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")):
                return True
    return False


def solve_and_learn(agent, config: dict, task: str, on_attempt=None,
                    reset_workspace: bool = True, on_step=None, harvest: bool = True):
    """Run one task through the full loop. Returns (outcome, success, reflection)."""
    max_attempts = config.get("improve", {}).get("max_attempts", 1)
    attempt_task = task
    outcome, success, reflection = None, False, {}
    started = time.time()
    if reset_workspace:
        _reset_workspace()

    for attempt in range(1, max_attempts + 1):
        if on_attempt:
            on_attempt(attempt, max_attempts)
        outcome = agent.run(attempt_task, on_step=on_step)

        # Verify with the pluggable verifier (pytest + lint + JS/Go/Rust) as
        # ground truth. If nothing is verifiable, accept a completed answer.
        import verifier
        result = verifier.verify(tools.WORKSPACE, config)
        has_tests = result["ran"]
        if has_tests:
            success = result["passed"]
        else:
            success = not str(outcome["result"]).startswith("Max iterations")

        # Reflect on the attempt and bank the lessons for future tasks
        reflection = reflect(agent.llm, task, outcome["transcript"],
                             outcome["result"], success)
        evolve(agent.lessons, agent.episodes, task, outcome["result"], success,
               reflection, config["improve"]["max_lessons"])

        if success:
            if has_tests and harvest:  # only bank code that pytest actually verified
                _harvest_skills(agent, task)
            break

        # Only retry when there are tests to satisfy; otherwise there is
        # nothing for a second attempt to fix.
        if not has_tests or attempt >= max_attempts:
            break

        # Feed the self-critique back into the next attempt
        critique = reflection.get("critique", "")
        attempt_task = (
            f"{task}\n\nYour previous attempt failed verification. "
            f"Critique of that attempt: {critique}\n"
            f"Fix those problems and try again."
        )

    try:  # observability: record the run (never breaks the task)
        import telemetry
        telemetry.log_run(config, task, outcome, success, time.time() - started)
    except Exception:
        pass
    return outcome, success, reflection


def _harvest_skills(agent, task: str):
    """Save non-test Python files from a verified success into the skill library."""
    if not os.path.isdir(tools.WORKSPACE):
        return
    for root, _, files in os.walk(tools.WORKSPACE):
        for name in files:
            if name.endswith(".py") and not name.startswith("test_") and not name.endswith("_test.py"):
                with open(os.path.join(root, name)) as f:
                    code = f.read()
                if code.strip():
                    agent.skills.add(task, name, code)
