"""Post-task reflection: the agent critiques its own attempt (Reflexion-style)."""
import json
import re

REFLECT_PROMPT = """You are reviewing an AI coding agent's attempt at a task.

Task: {task}

Transcript (steps and observations):
{transcript}

Final result: {result}
Verified success: {success}

Analyze the attempt and respond with ONE JSON object:
{{
  "critique": "what went well and what went wrong, 2-4 sentences",
  "lessons": ["short, general, actionable rule the agent should follow next time", "..."]
}}

Rules for lessons: generalize beyond this specific task, max 3 lessons,
each under 25 words, phrased as an imperative (e.g. "Always run tests before finishing").
"""


def reflect(llm, task: str, transcript: list, result: str, success: bool) -> dict:
    prompt = REFLECT_PROMPT.format(
        task=task,
        transcript=json.dumps(transcript, indent=1)[:6000],
        result=result[:1000],
        success=success,
    )
    raw = llm.chat([{"role": "user", "content": prompt}], temperature=0.3)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {"critique": raw[:500], "lessons": []}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"critique": raw[:500], "lessons": []}
