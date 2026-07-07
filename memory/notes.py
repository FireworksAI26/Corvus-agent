"""Self-managed memories: facts the agent chooses to remember about itself,
its environment, and recurring problems - via its own `remember` tool.
"""
import uuid

from memory._client import get_client


class NoteStore:
    def __init__(self, path: str, dedup_distance: float = 0.1):
        self.col = get_client(path).get_or_create_collection("notes")
        self.dedup_distance = dedup_distance

    def add(self, note: str):
        # Skip near-duplicates
        if self.col.count() > 0:
            res = self.col.query(query_texts=[note], n_results=1)
            if res["documents"][0] and res["distances"][0][0] < self.dedup_distance:
                return
        self.col.add(ids=[str(uuid.uuid4())], documents=[note])

    def search(self, query: str, k: int = 5) -> list[str]:
        if self.col.count() == 0:
            return []
        res = self.col.query(query_texts=[query], n_results=min(k, self.col.count()))
        return res["documents"][0]

    def all(self) -> list[str]:
        if self.col.count() == 0:
            return []
        return self.col.get(include=["documents"])["documents"]
