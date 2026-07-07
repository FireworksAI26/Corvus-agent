"""Smoke-test the `corvus bench` eval path end to end with the mock model:
fresh workspace per task, pytest verification, pass-rate + history.json.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent.core as core   # noqa: E402
import mock_llm as M        # noqa: E402


def _scripted(_config):
    def step_fn(idx, _msg):
        return [M.write("sol.py", "def f():\n    return 1\n"),
                M.write("test_sol.py", "from sol import f\n\n\ndef test_f():\n    assert f() == 1\n"),
                M.run_tests(),
                M.final("done")][min(idx, 3)]
    return M.ScriptedLLM(step_fn, reflection={"critique": "ok", "lessons": ["Write tests first."]})


core.make_llm = _scripted        # so Agent(config) uses the mock, not Ollama
from evals import benchmark      # noqa: E402

benchmark.main()
