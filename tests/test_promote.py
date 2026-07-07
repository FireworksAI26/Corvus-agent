"""Tests for `corvus ship` - promoting the verified sandbox project to a folder."""
import os

import promote


def _sandbox(tmp_path):
    ws = tmp_path / "workspace"
    (ws / "pkg").mkdir(parents=True)
    (ws / "app.py").write_text("print('hi')\n")
    (ws / "pkg" / "mod.py").write_text("X = 1\n")
    (ws / "__pycache__").mkdir()
    (ws / "__pycache__" / "junk.pyc").write_text("nope")
    return str(ws)


def test_ship_copies_verified_project(tmp_path):
    ws = _sandbox(tmp_path)
    dest = str(tmp_path / "out")
    res = promote.promote(ws, dest)
    assert res["copied"] == 2                      # app.py + pkg/mod.py, not the .pyc
    assert os.path.isfile(os.path.join(dest, "app.py"))
    assert os.path.isfile(os.path.join(dest, "pkg", "mod.py"))
    assert not os.path.exists(os.path.join(dest, "__pycache__"))  # junk skipped


def test_dry_run_copies_nothing(tmp_path):
    ws = _sandbox(tmp_path)
    dest = str(tmp_path / "out")
    res = promote.promote(ws, dest, dry_run=True)
    assert res["dry_run"] and "app.py" in res["files"]
    assert not os.path.exists(dest)


def test_refuses_to_overwrite_without_force(tmp_path):
    ws = _sandbox(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "app.py").write_text("PRECIOUS\n")
    res = promote.promote(ws, str(dest))
    assert "error" in res and "app.py" in res["conflicts"]
    assert (dest / "app.py").read_text() == "PRECIOUS\n"   # untouched
    # with --force it overwrites
    res2 = promote.promote(ws, str(dest), force=True)
    assert res2["copied"] == 2 and (dest / "app.py").read_text() == "print('hi')\n"


def test_ship_with_git_inits_repo(tmp_path):
    import repo as repo_git
    ws = _sandbox(tmp_path)
    dest = str(tmp_path / "out")
    res = promote.promote(ws, dest, do_git=True)
    assert res["git"] is True and repo_git.is_git_repo(dest)
    assert "corvus:" in repo_git.log(dest)


def test_empty_workspace_errors(tmp_path):
    ws = tmp_path / "empty"
    ws.mkdir()
    assert "empty" in promote.promote(str(ws), str(tmp_path / "out"))["error"]
