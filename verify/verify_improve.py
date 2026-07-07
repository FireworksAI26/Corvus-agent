"""Drive the FULL self-improvement pipeline with a deterministic mock model.

Proves, without any real LLM:
  1. A verified success banks a lesson, stores an episode, and harvests a skill.
  2. On the next task, that lesson + skill are actually injected into the prompt.
  3. Re-learning the same lesson reinforces (score++) instead of duplicating.
  4. A failed attempt feeds its own critique back and the retry succeeds.
"""
import os
import shutil
import sys
import tempfile

# The agent computes WORKSPACE = abspath("workspace") at import time, so chdir first.
ROOT = tempfile.mkdtemp(prefix="corvus_verify_")
os.chdir(ROOT)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.core import Agent            # noqa: E402
from agent.session import solve_and_learn  # noqa: E402
from agent.tools import WORKSPACE       # noqa: E402
from settings import load_config        # noqa: E402
import mock_llm as M                    # noqa: E402


def fresh_workspace():
    shutil.rmtree(WORKSPACE, ignore_errors=True)
    os.makedirs(WORKSPACE, exist_ok=True)


def banner(t):
    print(f"\n{'=' * 62}\n{t}\n{'=' * 62}")


config = load_config()          # no config.yaml here -> defaults (provider ollama)
agent = Agent(config)           # builds real chromadb stores under ./.memory
LESSON = "Always write pytest tests and run them before finishing."

# ----- Scenario 1: a verified success -----------------------------------------
banner("SCENARIO 1  success -> bank lesson, store episode, harvest skill")


def script1(idx, _msg):
    return [M.write("fizzbuzz.py", M.FIZZBUZZ),
            M.write("test_fizzbuzz.py", M.FIZZBUZZ_TEST),
            M.run_tests(),
            M.final("fizzbuzz implemented and tests pass")][min(idx, 3)]


agent.llm = M.ScriptedLLM(script1, reflection={"critique": "Good, verified.",
                                               "lessons": [LESSON]})
fresh_workspace()
outcome, success, refl = solve_and_learn(agent, config,
                                         "Write fizzbuzz.py with pytest tests")
print(f"  verified success   : {success}   (steps={outcome['steps']})")
print(f"  lessons banked      : {agent.lessons.all()}")
print(f"  episodes stored     : {agent.episodes.col.count()}")
print(f"  skills harvested    : {agent.skills.count()}  -> {agent.skills.list_named() or '[harvested, unnamed]'}")
assert success and agent.lessons.col.count() == 1 and agent.skills.count() >= 1

# ----- Scenario 2: next task -> memory is injected + lesson reinforced ---------
banner("SCENARIO 2  next task pulls prior lesson+skill INTO the prompt, reinforces")


def script2(idx, _msg):
    return [M.write("fizzbuzz.py", M.FIZZBUZZ),
            M.write("test_fizzbuzz.py", M.FIZZBUZZ_TEST),
            M.run_tests(),
            M.final("done again")][min(idx, 3)]


agent.llm = M.ScriptedLLM(script2, reflection={"critique": "Same discipline.",
                                              "lessons": [LESSON]})  # identical lesson
fresh_workspace()
outcome, success, refl = solve_and_learn(agent, config,
                                         "Write a FizzBuzz variant with tests")
injected = agent.llm.seen_systems[0]     # the system prompt for this task's 1st step
lesson_in_prompt = LESSON in injected
skill_in_prompt = "fizzbuzz" in injected.lower()
scores = agent.lessons.all()
print(f"  lesson injected into next prompt : {lesson_in_prompt}")
print(f"  skill injected into next prompt  : {skill_in_prompt}")
print(f"  lesson store after re-learning   : {scores}")
assert lesson_in_prompt and skill_in_prompt
assert agent.lessons.col.count() == 1 and "score 2" in scores[0], "should reinforce, not duplicate"

# ----- Scenario 3: fail -> critique fed back -> retry succeeds -----------------
banner("SCENARIO 3  attempt 1 fails verification, critique fed back, attempt 2 passes")


def script3(idx, msg):
    if "previous attempt failed verification" in msg:      # attempt 2
        return [M.write("adder.py", M.ADDER_FIXED),
                M.run_tests(),
                M.final("fixed")][min(idx, 2)]
    return [M.write("adder.py", M.ADDER_BROKEN),            # attempt 1 (buggy)
            M.write("test_adder.py", M.ADDER_TEST),
            M.run_tests(),
            M.final("attempted")][min(idx, 3)]


agent.llm = M.ScriptedLLM(script3, reflection=lambda _j: {
    "critique": "add() subtracts instead of adding; fix the operator.",
    "lessons": ["Check arithmetic operators against the test's expected value."]})
fresh_workspace()
outcome, success, refl = solve_and_learn(agent, config,
                                         "Write adder.py add(a,b) with a pytest test")
print(f"  final verified success : {success}")
print(f"  retry saw critique     : {agent.llm.saw_critique}")
print(f"  total lessons now      : {agent.lessons.col.count()}")
assert success and agent.llm.saw_critique, "retry with critique must drive success"

banner("ALL SELF-IMPROVEMENT CHECKS PASSED")
shutil.rmtree(ROOT, ignore_errors=True)
