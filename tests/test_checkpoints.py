import os

import pytest

import checkpoints


def test_save_list_load(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs(".memory")
    with open(".memory/data.txt", "w") as f:
        f.write("learned state")

    checkpoints.save("v1")
    assert any("v1" in c for c in checkpoints.list_checkpoints())

    # memory changes after the checkpoint...
    with open(".memory/extra.txt", "w") as f:
        f.write("later")

    # ...loading restores the exact saved state
    checkpoints.load("v1")
    assert os.path.exists(".memory/data.txt")
    assert not os.path.exists(".memory/extra.txt")
    assert os.path.exists(".memory.backup/extra.txt")


def test_save_requires_memory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        checkpoints.save("nope")


def test_duplicate_name_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs(".memory")
    checkpoints.save("v1")
    with pytest.raises(ValueError):
        checkpoints.save("v1")
