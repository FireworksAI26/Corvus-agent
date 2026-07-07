"""Surgical edit_file tool."""
import agent.tools as tools


def test_edit_unique_snippet(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE", str(tmp_path))
    (tmp_path / "m.py").write_text("def add(a, b):\n    return a - b  # bug\n")
    out = tools.tool_edit_file("m.py", "a - b  # bug", "a + b")
    assert "1 replacement" in out
    assert (tmp_path / "m.py").read_text() == "def add(a, b):\n    return a + b\n"


def test_edit_missing_snippet_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE", str(tmp_path))
    (tmp_path / "m.py").write_text("x = 1\n")
    out = tools.tool_edit_file("m.py", "not there", "y")
    assert "not present" in out and (tmp_path / "m.py").read_text() == "x = 1\n"


def test_edit_ambiguous_snippet_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE", str(tmp_path))
    (tmp_path / "m.py").write_text("v = 1\nv = 1\n")
    out = tools.tool_edit_file("m.py", "v = 1", "v = 2")
    assert "matches 2 places" in out and (tmp_path / "m.py").read_text() == "v = 1\nv = 1\n"


def test_edit_path_confined(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE", str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()
    import pytest
    with pytest.raises(ValueError):
        tools.tool_edit_file("../escape.py", "a", "b")
