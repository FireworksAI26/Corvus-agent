"""Skill library: working code retrieved by task similarity.

Skill kinds:
  - harvested: auto-banked from pytest-verified task successes (Voyager-style)
  - built:     skills the agent authored on purpose via its build_skill tool
  - community: skills imported from shared files/URLs (corvus skills import)
"""
import uuid

from memory._client import get_client


class SkillStore:
    def __init__(self, path: str, dedup_distance: float = 0.1):
        self.col = get_client(path).get_or_create_collection("skills")
        self.dedup_distance = dedup_distance

    def _add_doc(self, doc: str, metadata: dict) -> bool:
        """Add unless a near-duplicate already exists."""
        if self.col.count() > 0:
            res = self.col.query(query_texts=[doc], n_results=1)
            if res["documents"][0] and res["distances"][0][0] < self.dedup_distance:
                return False
        self.col.add(ids=[str(uuid.uuid4())], documents=[doc], metadatas=[metadata])
        return True

    def add(self, task: str, filename: str, code: str):
        doc = f"Task: {task}\nFile: {filename}\n```python\n{code[:1500]}\n```"
        self._add_doc(doc, {"kind": "harvested", "task": task[:300], "filename": filename})

    def add_built(self, name: str, description: str, code: str):
        doc = f"Skill: {name}\nDescription: {description}\n```python\n{code[:2000]}\n```"
        self._add_doc(doc, {"kind": "built", "name": name[:100],
                            "description": description[:300]})

    def similar(self, task: str, k: int = 2) -> list[str]:
        if self.col.count() == 0:
            return []
        res = self.col.query(query_texts=[task], n_results=min(k, self.col.count()))
        return res["documents"][0]

    def count(self) -> int:
        return self.col.count()

    def list_named(self) -> list[str]:
        """Built + community skills, for `corvus skills list`."""
        res = self.col.get(where={"kind": {"$in": ["built", "community"]}},
                           include=["metadatas"])
        return [f"[{m['kind']}] {m.get('name', '?')}: {m.get('description', '')}"
                for m in res["metadatas"]]

    def export_named(self) -> list[dict]:
        """Shareable JSON entries, for `corvus skills export`."""
        res = self.col.get(where={"kind": {"$in": ["built", "community"]}},
                           include=["documents", "metadatas"])
        return [{"name": m.get("name", ""), "description": m.get("description", ""),
                 "document": d}
                for d, m in zip(res["documents"], res["metadatas"])]

    def import_entries(self, entries: list[dict]) -> int:
        """Import shared skills. Returns how many new ones were added."""
        added = 0
        for e in entries:
            doc = e.get("document") or (
                f"Skill: {e.get('name', '?')}\nDescription: {e.get('description', '')}\n"
                f"```python\n{e.get('code', '')}\n```"
            )
            meta = {"kind": "community", "name": str(e.get("name", "?"))[:100],
                    "description": str(e.get("description", ""))[:300]}
            if self._add_doc(doc, meta):
                added += 1
        return added
