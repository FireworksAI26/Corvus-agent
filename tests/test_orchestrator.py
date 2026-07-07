"""Multi-agent planner -> coder -> reviewer orchestration."""
import json

import agent.tools as tools
import mock_llm as M
from agent.core import Agent
from agent.llm import BaseLLM
from agent.orchestrator import solve_with_team
from settings import load_config


class TeamLLM(BaseLLM):
    """One LLM playing planner (chat), coder (step), and reviewer (chat)."""

    def __init__(self, coder_steps, approve=True):
        self.coder_steps = coder_steps
        self.approve = approve
        self.saw_plan = False
        self.saw_review = False

    def chat(self, messages, temperature=0.2):
        joined = "\n".join(m.get("content", "") for m in messages)
        if "PLANNER" in joined:
            self.saw_plan = True
            return "1. Write the function\n2. Write tests\n3. Run them"
        if "REVIEWER" in joined:
            self.saw_review = True
            return json.dumps({"approved": self.approve, "feedback": "looks correct"})
        if "reviewing an AI coding agent" in joined:  # reflect()
            return json.dumps({"critique": "ok", "lessons": []})
        return ""

    def step(self, messages):
        idx = sum(1 for m in messages if m["role"] == "assistant")
        return self.coder_steps(idx, "\n".join(m.get("content", "") for m in messages))


def test_team_plans_codes_and_reviews(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("CORVUS_MEMORY_BACKEND", "lite")
    cfg = load_config()
    cfg["memory"]["path"] = str(tmp_path / ".mem")
    cfg["memory"]["backend"] = "lite"
    agent = Agent(cfg)

    def coder(idx, _msg):
        return [M.write("sol.py", "def f():\n    return 1\n"),
                M.write("test_sol.py", "from sol import f\n\n\ndef test_f():\n    assert f() == 1\n"),
                M.run_tests(),
                M.final("implemented")][min(idx, 3)]

    agent.llm = TeamLLM(coder, approve=True)
    res = solve_with_team(agent, cfg, "make f() return 1 with a test")
    assert res["success"] is True
    assert agent.llm.saw_plan and agent.llm.saw_review        # all three roles ran
    assert res["plan"].startswith("1.") and res["review"]["approved"] is True
    assert res["review_rounds"] == 0                          # approved first pass
