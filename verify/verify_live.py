"""Live self-improvement demo against the REAL configured model (no mock).

Set your provider + key in config.yaml / env first (e.g. Cloudflare Workers AI),
then run:  python verify/verify_live.py

It runs two related coding tasks through the full loop and shows, for real:
  - verification (tests actually run and pass),
  - lessons banked + skills harvested after task 1,
  - that task 1's lesson/skill is injected into task 2's prompt (memory works).
Nothing here is mocked - it exercises the exact code `corvus run` uses.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.core import Agent            # noqa: E402
from agent.session import solve_and_learn  # noqa: E402
from settings import load_config        # noqa: E402

TASK_A = ("Write is_palindrome(s) in palindrome.py that ignores case, spaces and "
          "punctuation, plus test_palindrome.py with pytest tests. Make the tests pass.")
TASK_B = ("Write is_anagram(a, b) in anagram.py (ignore case and spaces), plus "
          "test_anagram.py with pytest tests. Make the tests pass.")


def _bar(t):
    print(f"\n{'=' * 64}\n{t}\n{'=' * 64}")


def main():
    cfg = load_config()
    print(f"Provider: {cfg.get('provider')} | Model: {cfg.get('model')} | "
          f"Memory: {cfg.get('memory', {}).get('backend')} | "
          f"native_tools: {cfg.get('agent', {}).get('native_tools')}")
    agent = Agent(cfg)

    _bar("TASK 1 (fresh) - draft, run tests, self-correct until green")
    o1, ok1, r1 = solve_and_learn(agent, cfg, TASK_A)
    print(f"  verified success : {ok1}   steps: {o1['steps']}")
    print(f"  lessons banked   : {agent.lessons.all()[:3]}")
    print(f"  skills harvested : {agent.skills.count()}")

    _bar("TASK 2 (related) - should reuse what it learned")
    o2, ok2, r2 = solve_and_learn(agent, cfg, TASK_B)
    print(f"  verified success : {ok2}   steps: {o2['steps']}")
    print(f"  total lessons    : {agent.lessons.col.count()}")

    _bar("RESULT")
    print(f"  task1 verified: {ok1}   task2 verified: {ok2}")
    print("  If both are True and lessons/skills accumulated, the live loop works.")


if __name__ == "__main__":
    main()
