"""ReAct-style agent loop with lesson-augmented prompting.

The self-improvement hook: before each task, relevant lessons, self-saved
memories, similar past episodes, and proven skills are retrieved from memory
and injected into the system prompt, so the agent gets measurably better at
recurring task patterns over time. The agent can also write to its own
memory mid-task via the `remember` tool.
"""
import json

from agent.llm import make_llm, parse_json_step
from agent.tools import TOOL_DESCRIPTIONS, ToolContext, build_tools
from memory.episodic import EpisodeStore
from memory.lessons import LessonStore
from memory.notes import NoteStore
from memory.skills import SkillStore

SYSTEM_TEMPLATE = """You are Corvus, an expert autonomous coding agent.
You solve tasks step by step using tools. Always verify your work by
running code or tests before finishing. When you discover something
important and reusable, save it with the remember tool.

{tools}

Lessons learned from your past attempts (apply them):
{lessons}

Your saved memories (facts you chose to remember):
{notes}

Similar tasks you solved before (reuse what worked):
{episodes}

Proven skills - verified working code from past successes (reuse it):
{skills}
"""

# Text-mode providers get the JSON protocol; native-tool providers are told to
# use the tool API and finish with a plain-text answer.
JSON_PROTOCOL = """
Respond with EXACTLY ONE JSON object per step, no other text:
{"thought": "...", "tool": "tool_name", "args": {...}}
or, when the task is fully solved and verified:
{"thought": "...", "final_answer": "..."}
"""

NATIVE_PROTOCOL = """
Use the provided tools to act, one tool call per step. Always verify with
run_tests before finishing. When the task is fully solved, reply with your
final answer as plain text (no tool call).
"""


# Kept for backward compatibility (and existing tests): parse a JSON step.
_parse_step = parse_json_step


def _trim_orphans(tail: list) -> list:
    """Drop leading messages that would be orphaned tool results after trimming.

    Native tool calling pairs an assistant tool-call message with a following
    tool-result message. If history trimming slices between them, the leftover
    result has no matching call and the provider rejects it. Drop any leading
    tool-result (OpenAI role="tool", or an Anthropic user turn whose content is
    a tool_result block) until the tail starts with a clean message.
    """
    while tail:
        m = tail[0]
        content = m.get("content")
        is_openai_tool = m.get("role") == "tool"
        is_anthropic_result = (m.get("role") == "user" and isinstance(content, list)
                               and any(isinstance(b, dict) and b.get("type") == "tool_result"
                                       for b in content))
        if is_openai_tool or is_anthropic_result:
            tail = tail[1:]
        else:
            break
    return tail


class Agent:
    def __init__(self, config: dict):
        self.config = config
        self.llm = make_llm(config)
        mem = config["memory"]
        # Pick the memory backend (auto/chroma/lite) before opening any store.
        from memory._client import configure as _configure_memory
        _configure_memory(mem.get("backend", "auto"), mem.get("embedding", "hash"))
        # Configure the web-search backend from config.
        from agent.search import configure as _configure_search
        _configure_search(config.get("search", {}))
        # Configure the sandbox execution backend (subprocess/docker).
        from sandbox.runner import configure as _configure_sandbox
        sb = config.get("sandbox", {})
        _configure_sandbox(sb.get("backend"), sb.get("image"))
        self.lessons = LessonStore(mem["path"], mem.get("lesson_dedup_distance", 0.15))
        self.episodes = EpisodeStore(mem["path"])
        self.notes = NoteStore(mem["path"], mem.get("dedup_distance", 0.1))
        self.skills = SkillStore(mem["path"], mem.get("dedup_distance", 0.1))
        # Per-agent tool state (no module globals): memory handles + the
        # computer-control policy, which stays off unless explicitly granted.
        cc = config.get("computer_control", {})
        self.ctx = ToolContext(
            notes=self.notes, skills=self.skills,
            computer_enabled=cc.get("enabled", False),
            computer_confirm=cc.get("require_confirmation", True),
            computer_allowlist=cc.get("allowlist", []),
        )
        self.tools = build_tools(self.ctx)

    def run(self, task: str, on_step=None) -> dict:
        """Run one task. Returns transcript, result, and step count.

        If `on_step(step, observation)` is given, it is called after each tool
        step so callers can show live progress.
        """
        mem_cfg = self.config["memory"]
        lessons = self.lessons.relevant(task, k=mem_cfg["lessons_top_k"])
        episodes = self.episodes.similar(task, k=mem_cfg["episodes_top_k"])
        notes = self.notes.search(task, k=mem_cfg.get("notes_top_k", 5))
        skills = self.skills.similar(task, k=mem_cfg.get("skills_top_k", 2))

        native = getattr(self.llm, "native_tools", False)
        system = SYSTEM_TEMPLATE.format(
            tools=TOOL_DESCRIPTIONS,
            lessons="\n".join(f"- {lesson}" for lesson in lessons) or "(none yet)",
            notes="\n".join(f"- {n}" for n in notes) or "(none yet)",
            episodes="\n".join(f"- {e}" for e in episodes) or "(none yet)",
            skills="\n\n".join(skills) or "(none yet)",
        ) + (NATIVE_PROTOCOL if native else JSON_PROTOCOL)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Task: {task}"},
        ]
        transcript = []
        # Keep the prompt bounded on long tasks: always retain the system
        # prompt + original task, then only the most recent exchanges.
        max_history = self.config["agent"].get("max_history_messages", 24)

        for step_num in range(self.config["agent"]["max_iterations"]):
            if len(messages) > max_history:
                messages = messages[:2] + _trim_orphans(messages[-(max_history - 2):])
            try:
                step = self.llm.step(messages)
            except (ValueError, json.JSONDecodeError) as err:
                messages.append({"role": "assistant", "content": f"(unparseable step: {err})"})
                messages.append({"role": "user", "content": f"Invalid format: {err}. Reply with one JSON object only."})
                continue

            transcript.append(step)

            if "final_answer" in step:
                return {"task": task, "transcript": transcript,
                        "result": step["final_answer"], "steps": step_num + 1}

            tool_name = step.get("tool")
            tool = self.tools.get(tool_name)
            if tool is None:
                observation = f"Unknown tool: {tool_name}"
            else:
                try:
                    observation = tool(**step.get("args", {}))
                except Exception as err:  # surface tool errors to the model
                    observation = f"Tool error: {err}"

            transcript.append({"observation": observation[:4000]})
            if on_step:
                on_step(step, observation)
            # Append the provider-appropriate turns (native tool-call + tool
            # result for OpenAI/Anthropic; assistant text + observation otherwise).
            messages.extend(self.llm.history_after_tool(step, observation[:4000]))

        return {"task": task, "transcript": transcript,
                "result": "Max iterations reached without a final answer.",
                "steps": self.config["agent"]["max_iterations"]}
