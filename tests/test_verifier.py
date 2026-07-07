"""Pluggable, multi-language verification."""
import verifier


def test_detects_language_runners(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}')
    (tmp_path / "go.mod").write_text("module x\n")
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n")
    checks = verifier.detect_checks(str(tmp_path), {})
    assert set(checks) == {"npm-test", "go-test", "cargo-test"}


def test_explicit_checks_override_detection(tmp_path):
    assert verifier.detect_checks(str(tmp_path), {"verify": {"checks": ["lint"]}}) == ["lint"]


def test_passing_pytest_project_verifies(tmp_path):
    (tmp_path / "sol.py").write_text("def f():\n    return 1\n")
    (tmp_path / "test_sol.py").write_text("from sol import f\n\n\ndef test_f():\n    assert f() == 1\n")
    r = verifier.verify(str(tmp_path), {})
    assert r["ran"] is True and r["passed"] is True and "[pytest] PASS" in r["report"]


def test_failing_pytest_project_does_not_verify(tmp_path):
    (tmp_path / "sol.py").write_text("def f():\n    return 2\n")
    (tmp_path / "test_sol.py").write_text("from sol import f\n\n\ndef test_f():\n    assert f() == 1\n")
    r = verifier.verify(str(tmp_path), {})
    assert r["ran"] is True and r["passed"] is False and "[pytest] FAIL" in r["report"]


def test_uninstalled_tool_is_skipped_not_failed(tmp_path, monkeypatch):
    # a detected check whose binary is missing must be skipped, not failed
    (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}')
    monkeypatch.setitem(verifier.CHECK_CMDS, "npm-test", ["definitely-not-a-real-binary-xyz123"])
    r = verifier.verify(str(tmp_path), {})
    assert r["ran"] is False and "skipped" in r["report"]
