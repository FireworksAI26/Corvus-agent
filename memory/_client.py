"""Shared memory client, one per (backend, on-disk path).

Two backends live behind the same tiny interface (get_or_create_collection):
  - chroma: chromadb.PersistentClient (fast vector search; needs native builds)
  - lite:   memory.lite.LiteClient (pure-Python JSON + TF-IDF; runs anywhere,
            including Termux/Android where chromadb won't compile)

Selection order: the CORVUS_MEMORY_BACKEND env var, then configure() (from
memory.backend in config.yaml), then "auto" - which uses chroma when it's
importable and otherwise falls back to lite. Sharing one client per path also
avoids chroma's "already exists" instance warnings.
"""
import os

_BACKEND = None          # set via configure(); env var still takes precedence
_CLIENTS = {}
_CHROMA_OK = None


def configure(backend: str | None):
    """Set the preferred backend ('auto' | 'chroma' | 'lite')."""
    global _BACKEND
    _BACKEND = backend


def _chroma_available() -> bool:
    global _CHROMA_OK
    if _CHROMA_OK is None:
        try:
            import chromadb  # noqa: F401
            _CHROMA_OK = True
        except Exception:
            _CHROMA_OK = False
    return _CHROMA_OK


def active_backend() -> str:
    pref = (os.environ.get("CORVUS_MEMORY_BACKEND") or _BACKEND or "auto").lower()
    if pref == "auto":
        return "chroma" if _chroma_available() else "lite"
    if pref == "chroma" and not _chroma_available():
        raise RuntimeError(
            "memory backend 'chroma' requested but chromadb is not installed. "
            "Install it with  pip install 'corvus-agent[full]'  or set "
            "memory.backend: lite (recommended on Termux/Android)."
        )
    return pref


def build_client(backend: str, path: str):
    """Build a client for an explicit backend (bypasses resolution). Used by
    get_client and by migrate(), which needs both backends at once."""
    if backend == "lite":
        from memory.lite import LiteClient
        return LiteClient(path)
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as err:
        raise RuntimeError(
            "chromadb isn't installed. Install it with  pip install 'corvus-agent[full]'  "
            "to use the chroma backend (the pure-Python 'lite' backend needs no extras)."
        ) from err
    return chromadb.PersistentClient(
        path=path, settings=Settings(anonymized_telemetry=False))


def get_client(path: str):
    backend = active_backend()
    key = (backend, os.path.abspath(path))
    client = _CLIENTS.get(key)
    if client is None:
        client = build_client(backend, path)
        _CLIENTS[key] = client
    return client


COLLECTIONS = ("lessons", "episodes", "notes", "skills")


def migrate(path: str, to_backend: str, from_backend: str | None = None) -> dict:
    """Copy all learned state between the chroma and lite backends (in `path`).
    Idempotent: records already present in the destination (by id) are skipped.
    Returns {collection: number_of_records_copied}."""
    if to_backend not in ("chroma", "lite"):
        raise ValueError("to_backend must be 'chroma' or 'lite'")
    from_backend = from_backend or ("chroma" if to_backend == "lite" else "lite")
    src = build_client(from_backend, path)
    dst = build_client(to_backend, path)
    moved = {}
    for name in COLLECTIONS:
        s = src.get_or_create_collection(name)
        d = dst.get_or_create_collection(name)
        data = s.get(include=["documents", "metadatas"])
        existing = set(d.get().get("ids", []))
        ids, docs, metas = [], [], []
        for i, doc, meta in zip(data.get("ids", []), data.get("documents", []),
                                data.get("metadatas", [])):
            if i not in existing:
                ids.append(i)
                docs.append(doc)
                metas.append(meta or {})
        if ids:
            # chroma rejects empty metadata dicts; if a collection has none
            # (e.g. notes), omit metadatas entirely.
            d.add(ids=ids, documents=docs, metadatas=metas if any(metas) else None)
        moved[name] = len(ids)
    return moved
