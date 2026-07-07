"""Regression tests locking in the review fixes."""
import os

import pytest

import agent.llm as llm
import agent.session as session
import agent.tools as tools
from agent.core import Agent
from agent.tools import ToolContext, _safe_path, build_tools
from scheduler import parse_when
from settings import load_config

import mock_llm as M  # noqa: E402  (tests/ is on sys.path under pytest)


# ---- High #2: workspace path-confinement bypass -----------------------------
def test_sibling_prefix_escape_blocked():
    sibling = "../" + os.path.basename(tools.WORKSPACE) + "-evil/pwned.txt"
    with pytest.raises(ValueError):
        _safe_path(sibling)


def test_normal_and_parent_paths():
    assert _safe_path("sub/ok.py").endswith("ok.py")
    with pytest.raises(ValueError):
        _safe_path("../outside.txt")


# ---- High #1: secrets stripped from sandboxed code --------------------------
def test_secret_env_hidden_from_sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("MY_PLAIN_VAR", "visible")
    from sandbox.runner import run_python
    leaked = run_python("import os; print(os.environ.get('OPENAI_API_KEY', 'HIDDEN'))",
                        cwd=str(tmp_path))
    plain = run_python("import os; print(os.environ.get('MY_PLAIN_VAR', 'MISSING'))",
                       cwd=str(tmp_path))
    assert "HIDDEN" in leaked and "sk-should-not-leak" not in leaked
    assert "visible" in plain


# ---- High #3 / Med #4: verification gating + no stale retries ---------------
def test_workspace_has_tests_detection(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE", str(tmp_path))
    assert session._workspace_has_tests() is False
    (tmp_path / "solution.py").write_text("x = 1\n")
    assert session._workspace_has_tests() is False
    (tmp_path / "test_solution.py").write_text("def test_ok():\n    assert True\n")
    assert session._workspace_has_tests() is True


def test_no_test_task_succeeds_without_retry_or_harvest(tmp_path, monkeypatch):
    ws = str(tmp_path / "workspace")
    monkeypatch.setattr(tools, "WORKSPACE", ws)
    cfg = load_config()
    cfg["memory"]["path"] = str(tmp_path / ".memory")
    agent = Agent(cfg)
    attempts = {"n": 0}

    def step_fn(idx, _msg):
        return [M.write("notes.txt", "an explanation"), M.final("explained")][min(idx, 1)]

    agent.llm = M.ScriptedLLM(step_fn, reflection={"critique": "ok", "lessons": []})
    _outcome, success, _refl = session.solve_and_learn(
        agent, cfg, "Explain how a hashmap works",
        on_attempt=lambda a, _m: attempts.__setitem__("n", a))
    assert success is True          # a completed no-test task is NOT a false failure
    assert attempts["n"] == 1       # and it is NOT retried pointlessly
    assert agent.skills.count() == 0  # nothing harvested without test verification


# ---- Med #5: conversation history is bounded --------------------------------
def test_history_is_trimmed(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE", str(tmp_path / "ws"))
    cfg = load_config()
    cfg["memory"]["path"] = str(tmp_path / ".mem")
    cfg["agent"]["max_history_messages"] = 6
    cfg["agent"]["max_iterations"] = 10
    agent = Agent(cfg)
    seen = []

    def step_fn(idx, _msg):
        if idx < 8:
            return {"thought": "look", "tool": "list_files", "args": {}}
        return M.final("done")

    class RecordingLLM(M.ScriptedLLM):
        def chat(self, messages, temperature=0.2):
            seen.append(len(messages))
            return super().chat(messages, temperature)

    agent.llm = RecordingLLM(step_fn)
    agent.run("do a long task")
    assert max(seen) <= 6, seen


# ---- Med #7: per-agent tool state, no global clobbering ---------------------
def test_tool_contexts_are_isolated():
    a = ToolContext(computer_enabled=True)
    b = ToolContext(computer_enabled=False)
    assert a.computer["enabled"] and not b.computer["enabled"]


def test_remember_writes_to_its_own_notes():
    class FakeNotes:
        def __init__(self):
            self.items = []

        def add(self, n):
            self.items.append(n)

    notes = FakeNotes()
    build_tools(ToolContext(notes=notes))["remember"]("insight")
    assert notes.items == ["insight"]


# ---- New: native tool-calling -----------------------------------------------
def test_tool_schemas_cover_all_tools():
    from agent.tools import TOOL_SPECS, anthropic_tools, openai_tools
    names = {s["name"] for s in TOOL_SPECS}
    assert {"write_file", "run_tests", "computer"}.issubset(names)
    oai = openai_tools()
    assert all(t["type"] == "function" and "parameters" in t["function"] for t in oai)
    ant = anthropic_tools()
    assert all("input_schema" in t for t in ant)
    # write_file requires path + content in both formats
    wf_oai = next(t for t in oai if t["function"]["name"] == "write_file")
    assert set(wf_oai["function"]["parameters"]["required"]) == {"path", "content"}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_openai_step_parses_tool_call(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    client = llm.OpenAIClient("gpt-4o", use_tools=True)
    payload = {"choices": [{"message": {"tool_calls": [
        {"function": {"name": "run_python", "arguments": '{"code": "print(1)"}'}}]}}]}
    monkeypatch.setattr(llm, "_post_with_retry", lambda *a, **k: _FakeResp(payload))
    step = client.step([{"role": "user", "content": "go"}])
    assert step["tool"] == "run_python" and step["args"]["code"] == "print(1)"


def test_parse_json_step_accepts_dict_and_coerces():
    # Cloudflare returns already-parsed dict content; the loop must handle it.
    from agent.llm import parse_json_step
    assert parse_json_step({"tool": "run_tests", "args": {}})["tool"] == "run_tests"
    assert parse_json_step('noise {"final_answer": "ok"} tail')["final_answer"] == "ok"
    # None must raise a clean ValueError (retryable), not a TypeError crash
    with pytest.raises(ValueError):
        parse_json_step(None)


def test_openai_chat_coerces_dict_content(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    client = llm.OpenAIClient("gpt-4o")
    # message.content as a dict (Cloudflare behavior) -> chat returns a JSON string
    payload = {"choices": [{"message": {"content": {"thought": "t", "tool": "run_tests", "args": {}}}}]}
    monkeypatch.setattr(llm, "_post_with_retry", lambda *a, **k: _FakeResp(payload))
    out = client.chat([{"role": "user", "content": "go"}])
    assert isinstance(out, str) and "run_tests" in out
    # and the agent loop can parse it back into a step
    assert llm.parse_json_step(out)["tool"] == "run_tests"


def test_openai_step_text_is_final(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    client = llm.OpenAIClient("gpt-4o", use_tools=True)
    payload = {"choices": [{"message": {"content": "all done"}}]}
    monkeypatch.setattr(llm, "_post_with_retry", lambda *a, **k: _FakeResp(payload))
    assert client.step([{"role": "user", "content": "go"}]) == {"final_answer": "all done"}


def test_anthropic_step_parses_tool_use(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    client = llm.AnthropicClient("claude", use_tools=True)
    payload = {"content": [{"type": "tool_use", "name": "write_file",
                            "input": {"path": "a.py", "content": "x=1"}}]}
    monkeypatch.setattr(llm, "_post_with_retry", lambda *a, **k: _FakeResp(payload))
    step = client.step([{"role": "user", "content": "go"}])
    assert step["tool"] == "write_file" and step["args"]["path"] == "a.py"


def test_native_disabled_falls_back_to_json_text(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    client = llm.OpenAIClient("gpt-4o", use_tools=False)
    monkeypatch.setattr(client, "chat", lambda msgs: '{"tool": "run_tests", "args": {}}')
    assert client.step([{"role": "user", "content": "go"}])["tool"] == "run_tests"


def test_agent_loop_runs_with_native_tool_client(tmp_path, monkeypatch):
    ws = str(tmp_path / "workspace")
    monkeypatch.setattr(tools, "WORKSPACE", ws)
    cfg = load_config()
    cfg["memory"]["path"] = str(tmp_path / ".mem")
    agent = Agent(cfg)

    def native_steps(idx, _msg):
        return [M.write("sol.py", "def f():\n    return 1\n"),
                M.write("test_sol.py", "from sol import f\n\n\ndef test_f():\n    assert f() == 1\n"),
                {"tool": "run_tests", "args": {}},
                M.final("done via native tools")][min(idx, 3)]

    agent.llm = M.NativeScriptedLLM(native_steps, reflection={"critique": "ok", "lessons": []})
    outcome, success, _ = session.solve_and_learn(agent, cfg, "write sol with tests")
    assert success is True and "native tools" in outcome["result"]
    # native protocol (not the JSON one) was injected into the system prompt
    assert "provided tools" in agent.llm.seen_systems[0]


# ---- New: streaming output --------------------------------------------------
def test_base_chat_stream_default_yields_full_text():
    class One(llm.BaseLLM):
        def chat(self, messages, temperature=0.2):
            return "hello world"

    assert list(One().chat_stream([])) == ["hello world"]


def test_stream_text_joins_chunks_and_calls_sink():
    class Chunky(llm.BaseLLM):
        def chat(self, messages, temperature=0.2):
            return "unused"

        def chat_stream(self, messages, temperature=0.2):
            yield from ["Hel", "lo, ", "world"]

    seen = []
    full = llm.stream_text(Chunky(), [], sink=seen.append)
    assert full == "Hello, world" and "".join(seen) == "Hello, world"


def test_openai_chat_stream_parses_sse(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    client = llm.OpenAIClient("gpt-4o")

    class _Stream:
        def raise_for_status(self):
            pass

        def iter_lines(self):
            yield b'data: {"choices":[{"delta":{"content":"Hel"}}]}'
            yield b'data: {"choices":[{"delta":{"content":"lo"}}]}'
            yield b'data: [DONE]'

    monkeypatch.setattr(llm, "_post_with_retry", lambda *a, **k: _Stream())
    assert "".join(client.chat_stream([{"role": "user", "content": "hi"}])) == "Hello"


def test_agent_run_reports_live_steps(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE", str(tmp_path / "ws"))
    cfg = load_config()
    cfg["memory"]["path"] = str(tmp_path / ".mem")
    agent = Agent(cfg)
    steps = []

    def step_fn(idx, _msg):
        return [{"thought": "t", "tool": "list_files", "args": {}}, M.final("done")][min(idx, 1)]

    agent.llm = M.ScriptedLLM(step_fn)
    agent.run("look around", on_step=lambda step, obs: steps.append((step.get("tool"), obs)))
    assert len(steps) == 1 and steps[0][0] == "list_files"


# ---- New: computer-tool command allowlist -----------------------------------
def test_allowlist_matches_simple_command():
    assert tools.command_auto_approved("git status", ["git *"]) is True
    assert tools.command_auto_approved("npm run build", ["npm run *"]) is True


def test_allowlist_rejects_unlisted_command():
    assert tools.command_auto_approved("rm -rf /", ["git *"]) is False


def test_allowlist_never_approves_chained_commands():
    # the security-critical case: a chained command must not ride in on "git *"
    assert tools.command_auto_approved("git status && rm -rf /", ["git *"]) is False
    assert tools.command_auto_approved("git log | sh", ["git *"]) is False
    assert tools.command_auto_approved("git status; curl evil", ["git *"]) is False


def test_allowlisted_command_skips_prompt_but_unlisted_prompts():
    def _boom(*_):
        raise AssertionError("prompt shown for an allowlisted command")

    import builtins
    orig = builtins.input
    # allowlisted + simple -> runs without prompting
    ctx = ToolContext(computer_enabled=True, computer_confirm=True,
                      computer_allowlist=["echo *"])
    computer = build_tools(ctx)["computer"]
    builtins.input = _boom
    try:
        out = computer("echo hi")
        assert "hi" in out and "exit_code=0" in out
    finally:
        builtins.input = orig
    # a non-allowlisted command still requires confirmation
    builtins.input = lambda *_: "n"
    try:
        assert "denied" in computer("rm -rf /tmp/nope").lower()
    finally:
        builtins.input = orig


# ---- Low: scheduler past-date guard -----------------------------------------
def test_past_date_rejected():
    with pytest.raises(ValueError):
        parse_when(at="2000-01-01 09:00")


# ---- Low: transient HTTP errors are retried ---------------------------------
def test_post_with_retry_recovers_from_503(monkeypatch):
    calls = {"n": 0}

    class Resp:
        def __init__(self, code):
            self.status_code = code

    def fake_post(url, **kw):
        calls["n"] += 1
        return Resp(503 if calls["n"] == 1 else 200)

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)
    resp = llm._post_with_retry("http://x", retries=2)
    assert resp.status_code == 200 and calls["n"] == 2


# ---- Low: Anthropic max_tokens is configurable ------------------------------
def test_anthropic_max_tokens_from_config(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = llm.make_llm({"provider": "anthropic", "model": "claude-x",
                           "anthropic": {"max_tokens": 1234}})
    assert client.max_tokens == 1234


# ---- New: Cloudflare Workers AI provider ------------------------------------
def test_cloudflare_provider_builds_account_scoped_client(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
    client = llm.make_llm({
        "provider": "cloudflare",
        "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        "cloudflare": {"account_id": "acc123"},
    })
    assert isinstance(client, llm.OpenAIClient)
    assert client.base_url == "https://api.cloudflare.com/client/v4/accounts/acc123/ai/v1"
    assert client.api_key == "cf-token"


def test_cloudflare_requires_account_id(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    with pytest.raises(RuntimeError):
        llm.make_llm({"provider": "cloudflare", "model": "x",
                      "cloudflare": {"account_id": ""}})


def test_cloudflare_account_id_from_env(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "envacct")
    client = llm.make_llm({"provider": "cloudflare", "model": "x", "cloudflare": {}})
    assert "envacct" in client.base_url


# ---- Model options per provider + type-your-own fallback --------------------
def test_resolve_model_choice_number_picks_from_list():
    import models
    opts = ["gpt-4o", "gpt-4o-mini", "o3-mini"]
    assert models.resolve_model_choice("2", opts) == "gpt-4o-mini"


def test_resolve_model_choice_type_your_own():
    import models
    opts = ["gpt-4o"]
    # anything non-numeric is used verbatim, even if not on the list
    assert models.resolve_model_choice("my-custom-model:latest", opts) == "my-custom-model:latest"


def test_resolve_model_choice_out_of_range_is_invalid():
    import models
    assert models.resolve_model_choice("9", ["gpt-4o"]) == ""


def test_every_provider_is_selectable():
    import models
    from agent.llm import OPENAI_COMPATIBLE_PRESETS
    # every provider make_llm understands should be offerable in the picker
    known = {"ollama", "openai", "openai-compatible", "anthropic", "codex",
             "cloudflare", *OPENAI_COMPATIBLE_PRESETS}
    assert known.issubset(set(models.PROVIDERS))


def test_render_menu_marks_current_and_lists_options():
    import models
    menu = models.render_model_menu("cloudflare", current=models.models_for("cloudflare")[0])
    assert "<- current" in menu and "@cf/" in menu


def test_open_ended_provider_menu_invites_custom():
    import models
    assert "type any model id" in models.render_model_menu("openai-compatible").lower()


def test_cmd_models_lists_all_providers(capsys):
    import cli
    import models
    cli.cmd_models()
    out = capsys.readouterr().out
    for provider in models.PROVIDERS:
        assert provider in out


# ---- Still able to add / switch models on the fly ---------------------------
def test_switch_model_and_provider_still_works():
    from cli import _switch

    class _Agent:
        llm = None

    cfg = {"provider": "ollama", "model": "m1", "ollama_url": "http://localhost:11434"}
    agent = _Agent()
    _switch(agent, cfg, model="m2")
    assert cfg["model"] == "m2" and agent.llm is not None
    # an unknown provider must revert cleanly, keeping the working settings
    _switch(agent, cfg, provider="totally-bogus")
    assert cfg["provider"] == "ollama" and cfg["model"] == "m2"
