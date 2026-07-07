"""API server tests - run fully offline with an injected mock-LLM agent."""
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import agent.tools as tools  # noqa: E402
import mock_llm as M  # noqa: E402
from agent.core import Agent  # noqa: E402
from server import create_app  # noqa: E402
from settings import load_config  # noqa: E402


def _offline_agent(tmp_path, monkeypatch):
    ws = str(tmp_path / "workspace")
    monkeypatch.setattr(tools, "WORKSPACE", ws)
    cfg = load_config()
    cfg["memory"]["path"] = str(tmp_path / ".memory")
    agent = Agent(cfg)

    def steps(idx, _msg):
        return [M.write("sol.py", "def f():\n    return 1\n"),
                M.write("test_sol.py", "from sol import f\n\n\ndef test_f():\n    assert f() == 1\n"),
                M.run_tests(),
                M.final("done via API")][min(idx, 3)]

    agent.llm = M.ScriptedLLM(steps, reflection={"critique": "ok", "lessons": ["Ship tested code."]})
    return agent, cfg


def test_health_is_open(tmp_path, monkeypatch):
    agent, cfg = _offline_agent(tmp_path, monkeypatch)
    client = TestClient(create_app(config=cfg, agent=agent, api_token="secret"))
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_api_requires_token(tmp_path, monkeypatch):
    agent, cfg = _offline_agent(tmp_path, monkeypatch)
    client = TestClient(create_app(config=cfg, agent=agent, api_token="secret"))
    assert client.get("/api/lessons").status_code == 401
    ok = client.get("/api/lessons", headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200 and "lessons" in ok.json()


def test_run_task_end_to_end(tmp_path, monkeypatch):
    agent, cfg = _offline_agent(tmp_path, monkeypatch)
    client = TestClient(create_app(config=cfg, agent=agent, api_token="secret"))
    r = client.post("/api/task", json={"task": "write sol with tests"},
                    headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True and "API" in body["result"]
    # the verified success banked a lesson, visible via the API
    lessons = client.get("/api/lessons", headers={"Authorization": "Bearer secret"}).json()
    assert any("tested code" in ln.lower() for ln in lessons["lessons"])


def test_task_requires_body(tmp_path, monkeypatch):
    agent, cfg = _offline_agent(tmp_path, monkeypatch)
    client = TestClient(create_app(config=cfg, agent=agent, api_token="secret"))
    r = client.post("/api/task", json={"task": "  "}, headers={"Authorization": "Bearer secret"})
    assert r.status_code == 400


def test_task_stream_emits_steps_then_done(tmp_path, monkeypatch):
    agent, cfg = _offline_agent(tmp_path, monkeypatch)
    client = TestClient(create_app(config=cfg, agent=agent, api_token="secret"))
    # token via query param (EventSource can't set headers)
    r = client.get("/api/task/stream?task=write%20sol%20with%20tests&token=secret")
    assert r.status_code == 200
    body = r.text
    assert '"type": "step"' in body           # live steps streamed
    assert '"type": "done"' in body and '"success": true' in body


def test_task_stream_rejects_bad_token(tmp_path, monkeypatch):
    agent, cfg = _offline_agent(tmp_path, monkeypatch)
    client = TestClient(create_app(config=cfg, agent=agent, api_token="secret"))
    assert client.get("/api/task/stream?task=hi&token=wrong").status_code == 401
