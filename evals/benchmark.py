"""Run the eval suite and record pass rate over time.

This is how you PROVE the agent is self-improving: run it periodically
and watch success rate and step counts trend in history.json.

Usage: python -m evals.benchmark        # run and record
       python -m evals.benchmark --check  # also FAIL (exit 1) on a pass-rate regression
"""
import json
import os
import shutil
import sys
import time

from agent.core import Agent
from agent.session import solve_and_learn
from agent.tools import WORKSPACE
from settings import load_config

HISTORY = os.path.join(os.path.dirname(__file__), "history.json")


def check_regression(history: list, epsilon: float = 0.01):
    """Compare the latest run's pass rate to the previous one.
    Returns (regressed: bool, delta: float)."""
    if len(history) < 2:
        return False, 0.0
    delta = history[-1]["pass_rate"] - history[-2]["pass_rate"]
    return (delta < -epsilon), delta


def main(check: bool = False):
    config = load_config()
    with open(os.path.join(os.path.dirname(__file__), "tasks.json")) as f:
        tasks = json.load(f)

    agent = Agent(config)
    results = []

    for spec in tasks:
        # Fresh workspace per task
        shutil.rmtree(WORKSPACE, ignore_errors=True)
        os.makedirs(WORKSPACE, exist_ok=True)

        print(f"== {spec['id']} ==")
        outcome, success, _reflection = solve_and_learn(agent, config, spec["task"])
        print(f"   success={success} steps={outcome['steps']}")
        results.append({"id": spec["id"], "success": success, "steps": outcome["steps"]})

    run_record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": config.get("provider", "ollama"),
        "model": config["model"],
        "pass_rate": sum(r["success"] for r in results) / len(results),
        "avg_steps": sum(r["steps"] for r in results) / len(results),
        "results": results,
    }
    history = []
    if os.path.exists(HISTORY):
        with open(HISTORY) as f:
            history = json.load(f)
    history.append(run_record)
    with open(HISTORY, "w") as f:
        json.dump(history, f, indent=2)

    print(f"\nPass rate: {run_record['pass_rate']:.0%} | Avg steps: {run_record['avg_steps']:.1f}")
    print(f"History: {HISTORY} ({len(history)} runs)")

    if check:
        regressed, delta = check_regression(history)
        if regressed:
            print(f"REGRESSION: pass rate dropped {delta:+.0%} vs the previous run.")
            sys.exit(1)
        print(f"No regression (pass rate {delta:+.0%} vs previous).")


if __name__ == "__main__":
    main(check="--check" in sys.argv)
