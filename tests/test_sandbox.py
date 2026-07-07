from sandbox.runner import run_python


def test_run_python_success(tmp_path):
    out = run_python("print('hello-sandbox')", cwd=str(tmp_path))
    assert "exit_code=0" in out
    assert "hello-sandbox" in out


def test_run_python_error(tmp_path):
    out = run_python("raise ValueError('boom')", cwd=str(tmp_path))
    assert "exit_code=0" not in out
    assert "boom" in out


def test_run_python_timeout(tmp_path):
    out = run_python("while True: pass", cwd=str(tmp_path), timeout=2)
    assert "timed out" in out
