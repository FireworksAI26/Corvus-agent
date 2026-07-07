"""A deterministic stand-in for a real LLM, used to drive the agent loop
offline (no Ollama / no API key) so the self-improvement machinery can be
verified end to end.

`ScriptedLLM.chat` distinguishes two kinds of calls the pipeline makes:
  * reflection calls  (improve/reflect.py) -> returns a canned reflection dict
  * agent step calls  (agent/core.py)      -> returns the next scripted step

It also records every system prompt it is handed, so tests can assert that
lessons / skills / notes actually get injected into future prompts.
"""
import json

from agent.llm import BaseLLM

# A correct FizzBuzz implementation + a passing test (used by success scenarios)
FIZZBUZZ = """def fizzbuzz(n):
    out = []
    for i in range(1, n + 1):
        if i % 15 == 0:
            out.append("FizzBuzz")
        elif i % 3 == 0:
            out.append("Fizz")
        elif i % 5 == 0:
            out.append("Buzz")
        else:
            out.append(str(i))
    return out
"""

FIZZBUZZ_TEST = """from fizzbuzz import fizzbuzz


def test_basic():
    assert fizzbuzz(5) == ["1", "2", "Fizz", "4", "Buzz"]


def test_fizzbuzz_15():
    assert fizzbuzz(15)[-1] == "FizzBuzz"
"""

# A deliberately broken implementation + a test that fails against it
ADDER_BROKEN = "def add(a, b):\n    return a - b  # bug\n"
ADDER_FIXED = "def add(a, b):\n    return a + b\n"
ADDER_TEST = """from adder import add


def test_add():
    assert add(2, 3) == 5
"""


class ScriptedLLM(BaseLLM):
    """Text-mode mock: returns scripted JSON steps via chat(); the agent loop
    reaches them through the inherited BaseLLM.step (parse-JSON) path."""

    def __init__(self, step_fn, reflection=None):
        self.step_fn = step_fn
        self._reflection = reflection or {"critique": "ok", "lessons": []}
        self.seen_systems = []      # every system prompt handed to an agent step
        self.saw_critique = False   # set True if a retry prompt was observed

    def chat(self, messages, temperature=0.2):
        joined = "\n".join(m.get("content", "") for m in messages)
        if "reviewing an AI coding agent" in joined:
            refl = self._reflection(joined) if callable(self._reflection) else self._reflection
            return json.dumps(refl)
        # It's an agent step. Record the system prompt for injection assertions.
        sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        self.seen_systems.append(sys_msg)
        if "previous attempt failed verification" in joined:
            self.saw_critique = True
        # Local step index resets each run (messages start fresh per agent.run)
        local_idx = sum(1 for m in messages if m["role"] == "assistant")
        return json.dumps(self.step_fn(local_idx, joined))


def write(path, content):
    return {"thought": f"write {path}", "tool": "write_file",
            "args": {"path": path, "content": content}}


def run_tests():
    return {"thought": "verify", "tool": "run_tests", "args": {}}


def final(msg):
    return {"thought": "done", "final_answer": msg}


class NativeScriptedLLM(BaseLLM):
    """Native-tool mock: overrides step() to return structured steps directly,
    the way a provider's tool API would - no JSON-in-text parsing involved."""

    native_tools = True

    def __init__(self, step_fn, reflection=None):
        self.step_fn = step_fn
        self._reflection = reflection or {"critique": "ok", "lessons": []}
        self.seen_systems = []

    def step(self, messages):
        self.seen_systems.append(next((m["content"] for m in messages
                                       if m["role"] == "system"), ""))
        local_idx = sum(1 for m in messages if m["role"] == "assistant")
        return self.step_fn(local_idx, "\n".join(m.get("content", "") for m in messages))

    def chat(self, messages, temperature=0.2):
        # only used for reflect() calls
        refl = self._reflection(messages) if callable(self._reflection) else self._reflection
        return json.dumps(refl)
