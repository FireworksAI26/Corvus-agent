"""Team layer: role helpers, audit log, and API role enforcement."""
import pytest

import team

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import agent.tools as tools  # noqa: E402
import mock_llm as M  # noqa: E402
from agent.core import Agent  # noqa: E402
from server import create_app  # noqa: E402
from settings import load_config  # noqa: E402


def test_role_helpers():
    cfg = {"team": {"tokens": {"m": "member", "v": "viewer"}}}
    assert team.role_for("owner-tok", cfg, owner_token="owner-tok") == "owner"
    assert team.role_for("m", cfg) == "member"
    assert team.role_for("v", cfg) == "viewer"
    assert team.role_for("nope", cfg) is None
    assert team.can_write("owner") and team.can_write("member")
    assert not team.can_write("viewer")


def test_audit_roundtrip(tmp_path):
    cfg = {"memory": {"path": str(tmp_path)}}
    team.audit(cfg, "member", "task", "build X")
    rows = team.read_audit(cfg)
    assert rows and rows[-1]["role"] == "member" and rows[-1]["action"] == "task"


def _app(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("CORVUS_MEMORY_BACKEND", "lite")
    cfg = load_config()
    cfg["memory"]["path"] = str(tmp_path / ".mem")
    cfg["memory"]["backend"] = "lite"
    cfg["team"] = {"tokens": {"member-tok": "member", "viewer-tok": "viewer"}}
    agent = Agent(cfg)

    def steps(idx, _msg):
        return [M.write("sol.py", "def f():\n    return 1\n"),
                M.write("test_sol.py", "from sol import f\n\n\ndef test_f():\n    assert f() == 1\n"),
                M.run_tests(), M.final("ok")][min(idx, 3)]

    agent.llm = M.ScriptedLLM(steps, reflection={"critique": "ok", "lessons": []})
    return TestClient(create_app(config=cfg, agent=agent, api_token="owner-tok")), cfg


def test_viewer_can_read_but_not_write(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    assert client.get("/api/lessons", headers={"Authorization": "Bearer viewer-tok"}).status_code == 200
    r = client.post("/api/checkpoint", json={"name": "v1"},
                    headers={"Authorization": "Bearer viewer-tok"})
    assert r.status_code == 403


def test_member_can_write_and_is_audited(tmp_path, monkeypatch):
    client, cfg = _app(tmp_path, monkeypatch)
    r = client.post("/api/task", json={"task": "build sol with tests"},
                    headers={"Authorization": "Bearer member-tok"})
    assert r.status_code == 200 and r.json()["success"] is True
    audit = client.get("/api/audit", headers={"Authorization": "Bearer member-tok"}).json()["audit"]
    assert any(a["role"] == "member" and a["action"] == "task" for a in audit)


def test_invalid_token_rejected(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    assert client.get("/api/lessons", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_shared_skill_library_sync(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    hdr = {"Authorization": "Bearer owner-tok"}
    entry = {"name": "slug", "description": "make slug", "code": "def slug(s): return s"}
    assert client.post("/api/skills/import", json={"skills": [entry]}, headers=hdr).json()["added"] == 1
    exported = client.get("/api/skills/export", headers=hdr).json()["skills"]
    assert any(s.get("name") == "slug" for s in exported)
