"""Tests for the pure-Python 'lite' memory backend (the Termux-safe path)."""
import os

import agent.session as session
import agent.tools as tools
import mock_llm as M
from agent.core import Agent
from memory._client import active_backend
from memory.lessons import LessonStore
from memory.lite import LiteCollection
from memory.skills import SkillStore
from settings import load_config


def test_lite_collection_crud_and_persistence(tmp_path):
    p = str(tmp_path / "c.json")
    c = LiteCollection(p)
    assert c.count() == 0
    c.add(ids=["1", "2"], documents=["alpha beta", "gamma delta"],
          metadatas=[{"k": "a"}, {"k": "b"}])
    assert c.count() == 2
    # reloads from disk in a fresh instance
    assert LiteCollection(p).count() == 2
    c.update(ids=["1"], metadatas=[{"k": "z"}])
    c.delete(ids=["2"])
    assert c.count() == 1 and c.get()["metadatas"][0]["k"] == "z"


def test_lite_query_ranks_similar_first_and_dedup(tmp_path):
    c = LiteCollection(str(tmp_path / "q.json"))
    c.add(ids=["1", "2"], documents=["fizzbuzz with pytest tests", "unrelated banana text"])
    res = c.query(["write fizzbuzz tests"], n_results=2)
    assert res["documents"][0][0] == "fizzbuzz with pytest tests"
    c.add(ids=["3"], documents=["exact match"])
    assert c.query(["exact match"], n_results=1)["distances"][0][0] < 1e-9  # dedup works


def test_lite_where_in_filter(tmp_path):
    c = LiteCollection(str(tmp_path / "w.json"))
    c.add(ids=["1", "2", "3"], documents=["a", "b", "c"],
          metadatas=[{"kind": "built"}, {"kind": "harvested"}, {"kind": "community"}])
    got = c.get(where={"kind": {"$in": ["built", "community"]}})
    assert set(got["ids"]) == {"1", "3"}


def test_active_backend_env_override(monkeypatch):
    monkeypatch.setenv("CORVUS_MEMORY_BACKEND", "lite")
    assert active_backend() == "lite"


def test_stores_reinforce_and_retrieve_on_lite(tmp_path, monkeypatch):
    monkeypatch.setenv("CORVUS_MEMORY_BACKEND", "lite")
    path = str(tmp_path / ".mem")
    lessons = LessonStore(path)
    lessons.add("Always write tests first.")
    lessons.add("Always write tests first.")  # identical -> reinforce, not duplicate
    alls = lessons.all()
    assert len(alls) == 1 and "score 2" in alls[0]
    SkillStore(path).add_built("slug", "make a slug", "def slug(s): return s")
    assert any("slug" in x for x in SkillStore(path).list_named())
    assert os.path.exists(os.path.join(path, "lessons.json"))  # persisted as JSON


def test_full_self_improvement_on_lite(tmp_path, monkeypatch):
    ws = str(tmp_path / "workspace")
    monkeypatch.setattr(tools, "WORKSPACE", ws)
    cfg = load_config()
    cfg["memory"]["path"] = str(tmp_path / ".mem")
    cfg["memory"]["backend"] = "lite"
    agent = Agent(cfg)

    def steps(idx, _msg):
        return [M.write("fizzbuzz.py", M.FIZZBUZZ),
                M.write("test_fizzbuzz.py", M.FIZZBUZZ_TEST),
                M.run_tests(),
                M.final("done on lite")][min(idx, 3)]

    agent.llm = M.ScriptedLLM(steps, reflection={"critique": "ok", "lessons": ["Verify with pytest."]})
    _o, success, _r = session.solve_and_learn(agent, cfg, "write fizzbuzz with tests")
    assert success is True
    assert agent.lessons.col.count() == 1 and agent.skills.count() >= 1
    # a follow-up task injects the banked lesson -> memory works on lite too
    agent.llm = M.ScriptedLLM(steps, reflection={"critique": "ok", "lessons": []})
    session.solve_and_learn(agent, cfg, "write another fizzbuzz variant with tests")
    assert "Verify with pytest." in agent.llm.seen_systems[0]
