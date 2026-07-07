"""A dependency-free memory backend for platforms where chromadb won't build
(notably Termux/Android). It mirrors the small slice of the chromadb collection
API the stores use - add / query / get / update / delete / count - persisted as
plain JSON, with stdlib-only TF-IDF cosine retrieval.

Retrieval returns a distance = 1 - cosine_similarity, so identical text scores
distance 0 (dedup/reinforcement still works) and more-similar docs sort first,
matching how the stores consume chroma results.
"""
import json
import math
import os
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list:
    return _TOKEN.findall((text or "").lower())


def _rank(query: str, records: list):
    """Return [(distance, record), ...] sorted nearest-first via TF-IDF cosine."""
    doc_tokens = [_tokenize(r["document"]) for r in records]
    n = len(records)
    df = Counter()
    for toks in doc_tokens:
        for t in set(toks):
            df[t] += 1

    def idf(t):
        return math.log((n + 1) / (df.get(t, 0) + 1)) + 1.0

    def vec(toks):
        tf = Counter(toks)
        return {t: c * idf(t) for t, c in tf.items()}

    qv = vec(_tokenize(query))
    qnorm = math.sqrt(sum(v * v for v in qv.values())) or 1.0
    out = []
    for rec, toks in zip(records, doc_tokens):
        dv = vec(toks)
        dnorm = math.sqrt(sum(v * v for v in dv.values())) or 1.0
        dot = sum(w * dv.get(t, 0.0) for t, w in qv.items())
        cos = dot / (qnorm * dnorm)
        out.append((1.0 - cos, rec))
    out.sort(key=lambda pair: pair[0])
    return out


def _matches(meta: dict, where: dict) -> bool:
    if not where:
        return True
    for key, cond in where.items():
        val = meta.get(key)
        if isinstance(cond, dict):
            if "$in" in cond and val not in cond["$in"]:
                return False
            if "$eq" in cond and val != cond["$eq"]:
                return False
            if "$ne" in cond and val == cond["$ne"]:
                return False
        elif val != cond:
            return False
    return True


class LiteCollection:
    def __init__(self, path: str):
        self.path = path
        self.records = []
        if os.path.exists(path):
            try:
                with open(path) as f:
                    self.records = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.records = []

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.records, f)
        os.replace(tmp, self.path)

    def count(self) -> int:
        return len(self.records)

    def add(self, ids, documents, metadatas=None):
        metadatas = metadatas or [{} for _ in ids]
        for i, doc, meta in zip(ids, documents, metadatas):
            self.records.append({"id": i, "document": doc, "metadata": dict(meta or {})})
        self._save()

    def update(self, ids, metadatas):
        by_id = {r["id"]: r for r in self.records}
        for i, meta in zip(ids, metadatas):
            if i in by_id:
                by_id[i]["metadata"] = dict(meta or {})
        self._save()

    def delete(self, ids):
        drop = set(ids)
        self.records = [r for r in self.records if r["id"] not in drop]
        self._save()

    def get(self, where=None, include=None):
        recs = [r for r in self.records if _matches(r["metadata"], where)]
        return {"ids": [r["id"] for r in recs],
                "documents": [r["document"] for r in recs],
                "metadatas": [r["metadata"] for r in recs]}

    def query(self, query_texts, n_results=5, where=None):
        recs = [r for r in self.records if _matches(r["metadata"], where)]
        if not recs:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        top = _rank(query_texts[0] if query_texts else "", recs)[:max(0, n_results)]
        return {"ids": [[r["id"] for _d, r in top]],
                "documents": [[r["document"] for _d, r in top]],
                "metadatas": [[r["metadata"] for _d, r in top]],
                "distances": [[d for d, _r in top]]}


class LiteClient:
    """Drop-in stand-in for chromadb.PersistentClient (the subset we use)."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(path, exist_ok=True)
        self._cols = {}

    def get_or_create_collection(self, name: str) -> LiteCollection:
        if name not in self._cols:
            self._cols[name] = LiteCollection(os.path.join(self.path, f"{name}.json"))
        return self._cols[name]
