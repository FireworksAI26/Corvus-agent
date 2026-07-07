"""Container sandbox backend selection + subprocess fallback."""
import sandbox.runner as runner


def test_falls_back_to_subprocess_when_docker_missing(tmp_path, monkeypatch):
    runner.configure(backend="docker")
    monkeypatch.setattr(runner, "_docker_available", lambda: False)
    # docker requested but unavailable -> still runs via subprocess and works
    out = runner.run_python("print('hello-fallback')", cwd=str(tmp_path))
    assert "hello-fallback" in out and "exit_code=0" in out
    runner.configure(backend="subprocess")


def test_docker_backend_builds_isolated_command(tmp_path, monkeypatch):
    runner.configure(backend="docker", image="python:3.12")
    monkeypatch.setattr(runner, "_docker_available", lambda: True)
    captured = {}

    class _Proc:
        returncode = 0
        stdout = "ran-in-docker"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    out = runner.run_python("print('x')", cwd=str(tmp_path))
    cmd = captured["cmd"]
    assert cmd[0] == "docker" and "--network=none" in cmd and "python:3.12" in cmd
    assert "ran-in-docker" in out
    runner.configure(backend="subprocess")


def test_use_docker_reflects_env_and_availability(monkeypatch):
    monkeypatch.setattr(runner, "_docker_available", lambda: True)
    monkeypatch.setenv("CORVUS_SANDBOX_BACKEND", "docker")
    assert runner._use_docker() is True
    monkeypatch.setenv("CORVUS_SANDBOX_BACKEND", "subprocess")
    assert runner._use_docker() is False
