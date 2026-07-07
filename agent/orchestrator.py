"""Multi-agent orchestration: planner -> coder -> reviewer.

A lightweight team built on the single Agent. The planner drafts a short plan,
the coder executes it through the normal verified self-improvement loop, and the
reviewer critiques the result - requesting another pass if it isn't right. All
three roles share the agent's LLM, so it works with any provider.
"""
import json
import re

from agent.session import solve_and_learn

PLAN_PROMPT = ("You are the PLANNER for a coding task. Output a short numbered "
               "plan (3-6 concrete steps), no code.\n\nTask: {task}")

REVIEW_PROMPT = ("You are the REVIEWER of a coding agent's work.\n\n"
                 "Task: {task}\nResult: {result}\nTests passed: {success}\n\n"
                 'Respond with ONE JSON object: {{"approved": true|false, '
                 '"feedback": "what to fix if not approved"}}')


def _plan(llm, task: str) -> str:
    try:
        return llm.chat([{"role": "user", "content": PLAN_PROMPT.format(task=task)}]).strip()
    except Exception:
        return ""


def _review(llm, task: str, result: str, success: bool) -> dict:
    prompt = REVIEW_PROMPT.format(task=task, result=str(result)[:1000], success=success)
    try:
        raw = llm.chat([{"role": "user", "content": prompt}])
    except Exception:
        return {"approved": success, "feedback": ""}
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {"approved": success, "feedback": raw[:300]}
    try:
        data = json.loads(match.group(0))
        return {"approved": bool(data.get("approved", success)),
                "feedback": data.get("feedback", "")}
    except json.JSONDecodeError:
        return {"approved": success, "feedback": raw[:300]}


def solve_with_team(agent, config: dict, task: str, on_step=None,
                    max_review_rounds: int = 1) -> dict:
    plan = _plan(agent.llm, task)
    coder_task = f"{task}\n\nFollow this plan:\n{plan}" if plan else task
    outcome, success, reflection = solve_and_learn(agent, config, coder_task, on_step=on_step)
    review = _review(agent.llm, task, outcome["result"], success)

    rounds = 0
    while not (success and review["approved"]) and rounds < max_review_rounds:
        rounds += 1
        retry_task = (f"{task}\n\nReviewer feedback to address:\n{review.get('feedback', '')}")
        outcome, success, reflection = solve_and_learn(agent, config, retry_task, on_step=on_step)
        review = _review(agent.llm, task, outcome["result"], success)

    return {"plan": plan, "outcome": outcome, "success": success,
            "review": review, "reflection": reflection, "review_rounds": rounds}
