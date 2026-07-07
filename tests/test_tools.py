import pytest

from agent.tools import _safe_path


def test_workspace_escape_blocked():
    with pytest.raises(ValueError):
        _safe_path("../outside.txt")


def test_normal_path_allowed():
    assert _safe_path("sub/file.py").endswith("file.py")
