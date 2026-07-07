"""Real-repo mode: git helpers + working on an existing project safely."""
import os
import subprocess

import agent.session as session
import agent.tools as tools
import mock_llm as M
import repo as repo_git
from agent.core import Agent
from settings import load_config


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def _init_repo(path):
    _git(["init"], path)
    _git(["config", "user.email", "t@t.t"], path)
    _git(["config", "user.name", "t"], path)
    (path / "README.md").write_text("hi\n")
    _git(["add", "-A"], path)
    _git(["commit", "-m", "initial"], path)


def test_git_helpers_commit_and_revert(tmp_path):
    _init_repo(tmp_path)
    p = str(tmp_path)
    assert repo_git.is_git_repo(p)
    (tmp_path / "new.py").write_text("x = 1\n")
    assert repo_git.commit_all(p, "add new.py")
    assert "corvus: add new.py" in repo_git.log(p)
    # revert removes the corvus commit and its file
    assert "Reverted" in repo_git.revert_last(p)
    assert not (tmp_path / "new.py").exists()


def test_revert_refuses_non_corvus_commit(tmp_path):
    _init_repo(tmp_path)
    assert "isn't a corvus commit" in repo_git.revert_last(str(tmp_path))


def test_set_workspace_confines_to_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE", tools.os.path.abspath("workspace"))
    root = tmp_path / "proj"
    root.mkdir()
    tools.set_workspace(str(root))
    assert tools.WORKSPACE == str(root)
    # writing stays inside the repo; escaping is still blocked
    tools.tool_write_file("pkg/mod.py", "y = 2\n")
    assert (root / "pkg" / "mod.py").exists()
    import pytest
    with pytest.raises(ValueError):
        tools._safe_path("../outside.txt")


def test_repo_task_does_not_reset_or_harvest(tmp_path, monkeypatch):
    """A real-repo task must leave existing files intact and NOT bank them as skills."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "keep_me.py").write_text("PRESERVE = True\n")   # pre-existing project file
    tools.set_workspace(str(root))
    monkeypatch.setenv("CORVUS_MEMORY_BACKEND", "lite")
    cfg = load_config()
    cfg["memory"]["path"] = str(tmp_path / ".mem")
    cfg["memory"]["backend"] = "lite"
    agent = Agent(cfg)

    def steps(idx, _msg):
        return [M.write("feature.py", "def f():\n    return 7\n"),
                M.write("test_feature.py", "from feature import f\n\n\ndef test_f():\n    assert f() == 7\n"),
                M.run_tests(),
                M.final("added feature")][min(idx, 3)]

    agent.llm = M.ScriptedLLM(steps, reflection={"critique": "ok", "lessons": []})
    _o, success, _r = session.solve_and_learn(agent, cfg, "add a feature",
                                              reset_workspace=False, harvest=False)
    assert success is True
    assert (root / "keep_me.py").read_text() == "PRESERVE = True\n"  # not wiped
    assert agent.skills.count() == 0                                 # not harvested
    tools.set_workspace(os.path.abspath("workspace"))                # restore for other tests
