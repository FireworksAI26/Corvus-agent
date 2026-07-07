"""Code execution with a pluggable isolation backend.

Two backends (sandbox.backend in config):
  - subprocess (default): fast; API keys/tokens/secrets are stripped from the
    child's environment so a prompt-injected snippet can't read them.
  - docker: run code inside a throwaway container (--network=none, memory cap,
    no host env) for real isolation of untrusted tasks. Falls back to subprocess
    with a warning if docker isn't available. The image (sandbox.image) must
    contain the project's runtime/deps.
"""
import os
import subprocess
import sys
import tempfile

# Env var names containing any of these (case-insensitive) are withheld from
# code the agent writes. Covers OPENAI_API_KEY, ANTHROPIC_API_KEY, *_TOKEN, etc.
_SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL")

_BACKEND = "subprocess"
_IMAGE = "python:3.12"
_DOCKER_OK = None


def configure(backend: str | None = None, image: str | None = None):
    global _BACKEND, _IMAGE
    if backend:
        _BACKEND = backend
    if image:
        _IMAGE = image


def _sandbox_env() -> dict:
    return {k: v for k, v in os.environ.items()
            if not any(h in k.upper() for h in _SECRET_HINTS)}


def _docker_available() -> bool:
    global _DOCKER_OK
    if _DOCKER_OK is None:
        try:
            _DOCKER_OK = subprocess.run(["docker", "--version"], capture_output=True,
                                        timeout=10).returncode == 0
        except Exception:
            _DOCKER_OK = False
    return _DOCKER_OK


def _use_docker() -> bool:
    pref = os.environ.get("CORVUS_SANDBOX_BACKEND") or _BACKEND
    return pref == "docker" and _docker_available()


def _docker_cmd(cwd: str, argv: list) -> list:
    return ["docker", "run", "--rm", "--network=none", "--memory=512m",
            "-v", f"{os.path.abspath(cwd)}:/app", "-w", "/app", _IMAGE, *argv]


def _format(proc) -> str:
    return f"exit_code={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"[:8000]


def run_python(code: str, cwd: str, timeout: int = 30, env: dict | None = None) -> str:
    os.makedirs(cwd, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".py", dir=cwd, delete=False) as f:
        f.write(code)
        script = f.name
    name = os.path.basename(script)
    try:
        if _use_docker():
            proc = subprocess.run(_docker_cmd(cwd, ["python", name]),
                                  capture_output=True, text=True, timeout=timeout)
        else:
            proc = subprocess.run([sys.executable, script], cwd=cwd, capture_output=True,
                                  text=True, timeout=timeout,
                                  env=env if env is not None else _sandbox_env())
        return _format(proc)
    except subprocess.TimeoutExpired:
        return f"Execution timed out after {timeout}s"
    finally:
        os.unlink(script)


def run_pytest(cwd: str, timeout: int = 60, env: dict | None = None) -> str:
    os.makedirs(cwd, exist_ok=True)
    try:
        if _use_docker():
            proc = subprocess.run(_docker_cmd(cwd, ["python", "-m", "pytest", "-x", "-q"]),
                                  capture_output=True, text=True, timeout=timeout)
        else:
            proc = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q"], cwd=cwd,
                                  capture_output=True, text=True, timeout=timeout,
                                  env=env if env is not None else _sandbox_env())
        return f"exit_code={proc.returncode}\n{proc.stdout}\n{proc.stderr}"[:8000]
    except subprocess.TimeoutExpired:
        return f"Tests timed out after {timeout}s"
