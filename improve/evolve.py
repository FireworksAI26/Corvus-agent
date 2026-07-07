"""Turn reflections into durable improvement: store episodes, distill lessons, prune."""
from memory.episodic import EpisodeStore
from memory.lessons import LessonStore


def evolve(lessons_store: LessonStore, episodes_store: EpisodeStore,
           task: str, result: str, success: bool, reflection: dict,
           max_lessons: int = 200):
    episodes_store.add(
        task=task,
        outcome=result,
        success=success,
        reflection=reflection.get("critique", ""),
    )
    for lesson in reflection.get("lessons", [])[:3]:
        if isinstance(lesson, str) and lesson.strip():
            lessons_store.add(lesson.strip(), source_task=task)
    lessons_store.prune(max_lessons)
