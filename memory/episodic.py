"""Episodic memory: past tasks, outcomes, and reflections, retrieved by similarity."""
import uuid

from memory._client import get_client


class EpisodeStore:
    def __init__(self, path: str):
        self.col = get_client(path).get_or_create_collection("episodes")

    def add(self, task: str, outcome: str, success: bool, reflection: str):
        summary = (
            f"Task: {task}\nSuccess: {success}\n"
            f"Outcome: {outcome[:500]}\nReflection: {reflection[:500]}"
        )
        self.col.add(
            ids=[str(uuid.uuid4())],
            documents=[summary],
            metadatas=[{"task": task[:500], "success": success}],
        )

    def similar(self, task: str, k: int = 3) -> list[str]:
        if self.col.count() == 0:
            return []
        res = self.col.query(query_texts=[task], n_results=min(k, self.col.count()))
        return res["documents"][0]
