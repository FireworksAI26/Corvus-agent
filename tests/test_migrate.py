"""Tests for `corvus memory migrate` between the chroma and lite backends."""
import pytest

from memory._client import build_client, migrate


def _seed(client):
    client.get_or_create_collection("lessons").add(
        ids=["l1"], documents=["Always write tests first."], metadatas=[{"score": 3}])
    client.get_or_create_collection("skills").add(
        ids=["s1"], documents=["Skill: slug"], metadatas=[{"kind": "built", "name": "slug"}])
    client.get_or_create_collection("notes").add(
        ids=["n1"], documents=["a fact"])  # no metadata (the tricky case for chroma)


def test_migrate_lite_to_chroma_and_back(tmp_path):
    pytest.importorskip("chromadb")
    lite_path = str(tmp_path / "lite")
    _seed(build_client("lite", lite_path))

    # lite -> chroma (same dir)
    moved = migrate(lite_path, "chroma", from_backend="lite")
    assert moved["lessons"] == 1 and moved["skills"] == 1 and moved["notes"] == 1
    chroma = build_client("chroma", lite_path)
    assert chroma.get_or_create_collection("lessons").count() == 1
    assert chroma.get_or_create_collection("notes").count() == 1  # empty-metadata handled

    # re-running is idempotent (nothing duplicated)
    again = migrate(lite_path, "chroma", from_backend="lite")
    assert sum(again.values()) == 0


def test_migrate_chroma_to_lite(tmp_path):
    pytest.importorskip("chromadb")
    path = str(tmp_path / "cm")
    _seed(build_client("chroma", path))
    moved = migrate(path, "lite", from_backend="chroma")
    assert moved["lessons"] == 1
    lite = build_client("lite", path)
    docs = lite.get_or_create_collection("lessons").get()["documents"]
    assert docs and "tests first" in docs[0]


def test_migrate_rejects_bad_target(tmp_path):
    with pytest.raises(ValueError):
        migrate(str(tmp_path), "postgres")


def test_build_chroma_without_dependency_is_friendly(tmp_path, monkeypatch):
    import sys

    from memory import _client
    monkeypatch.setitem(sys.modules, "chromadb", None)  # simulate not installed
    with pytest.raises(RuntimeError) as excinfo:
        _client.build_client("chroma", str(tmp_path))
    assert "corvus-agent[full]" in str(excinfo.value)   # actionable, not a traceback
