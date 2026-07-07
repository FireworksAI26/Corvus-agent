"""Lesson store: distilled rules from past failures and successes.

Each lesson tracks a score. Lessons that keep getting reinforced rise;
stale ones get pruned. This is the core of the self-improvement signal.
"""
import uuid

from memory._client import get_client


class LessonStore:
    def __init__(self, path: str, dedup_distance: float = 0.15):
        self.col = get_client(path).get_or_create_collection("lessons")
        self.dedup_distance = dedup_distance

    def add(self, lesson: str, source_task: str = ""):
        # Reinforce near-duplicate lessons instead of adding new ones
        if self.col.count() > 0:
            res = self.col.query(query_texts=[lesson], n_results=1)
            if res["documents"][0] and res["distances"][0][0] < self.dedup_distance:
                existing_id = res["ids"][0][0]
                meta = res["metadatas"][0][0]
                meta["score"] = meta.get("score", 1) + 1
                self.col.update(ids=[existing_id], metadatas=[meta])
                return
        self.col.add(
            ids=[str(uuid.uuid4())],
            documents=[lesson],
            metadatas=[{"score": 1, "source_task": source_task[:300]}],
        )

    def relevant(self, task: str, k: int = 5) -> list[str]:
        if self.col.count() == 0:
            return []
        res = self.col.query(query_texts=[task], n_results=min(k, self.col.count()))
        return res["documents"][0]

    def all(self) -> list[str]:
        """All lessons, highest score first (for the /lessons terminal command)."""
        if self.col.count() == 0:
            return []
        items = self.col.get(include=["documents", "metadatas"])
        ranked = sorted(
            zip(items["documents"], items["metadatas"]),
            key=lambda pair: -pair[1].get("score", 1),
        )
        return [f"[score {m.get('score', 1)}] {d}" for d, m in ranked]

    def prune(self, max_lessons: int):
        """Drop the lowest-scoring lessons when over capacity."""
        total = self.col.count()
        if total <= max_lessons:
            return
        all_items = self.col.get(include=["metadatas"])
        ranked = sorted(
            zip(all_items["ids"], all_items["metadatas"]),
            key=lambda pair: pair[1].get("score", 1),
        )
        to_remove = [item_id for item_id, _ in ranked[: total - max_lessons]]
        self.col.delete(ids=to_remove)
