"""Observability: run log + stats, model routing, and the LLM cache."""
import models
import telemetry
from agent.llm import BaseLLM, CachingLLM


def test_telemetry_logs_and_aggregates(tmp_path):
    cfg = {"provider": "ollama", "model": "m1", "memory": {"path": str(tmp_path)}}
    telemetry.log_run(cfg, "task one", {"steps": 3, "result": "ok"}, True, 1.5)
    telemetry.log_run(cfg, "task two", {"steps": 5, "result": "no"}, False, 2.5)
    s = telemetry.stats(cfg)
    assert s["runs"] == 2 and s["pass_rate"] == 0.5
    assert s["avg_steps"] == 4.0 and s["by_model"]["ollama/m1"]["passed"] == 1


def test_routing_picks_strong_for_hard_tasks():
    cheap, strong = "gpt-4o-mini", "gpt-4o"
    assert models.route("add two numbers", cheap, strong) == cheap
    assert models.route("refactor the auth architecture for security", cheap, strong) == strong
    assert models.route("x" * 400, cheap, strong) == strong          # long task -> strong


def test_caching_llm_avoids_duplicate_calls(tmp_path):
    class Counter(BaseLLM):
        def __init__(self):
            self.model = "m"
            self.calls = 0

        def chat(self, messages, temperature=0.2):
            self.calls += 1
            return "answer"

    inner = Counter()
    cached = CachingLLM(inner, str(tmp_path / "cache"))
    msgs = [{"role": "user", "content": "hi"}]
    assert cached.chat(msgs) == "answer"
    assert cached.chat(msgs) == "answer"     # served from disk cache
    assert inner.calls == 1                  # inner hit only once
