"""Multi-provider LLM clients.

Supported providers (set in config.yaml):
  - ollama:            local open-source models (Hermes, Qwen-Coder, Llama, ...)
  - openai:            OpenAI API (ChatGPT models), key from OPENAI_API_KEY
  - anthropic:         Anthropic API (Claude models), key from ANTHROPIC_API_KEY
  - cloudflare:        Cloudflare Workers AI, token from CLOUDFLARE_API_TOKEN
  - openai-compatible: any OpenAI-compatible endpoint via openai.base_url

API keys are read from environment variables only - never hardcode keys.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time

import requests

_RETRY_STATUS = {429, 500, 502, 503, 504}


def parse_json_step(text) -> dict:
    """Extract one JSON step object from a text-mode model reply.

    Some OpenAI-compatible endpoints (e.g. Cloudflare Workers AI) return the
    message content as an already-parsed object rather than a string, so accept
    a dict directly and coerce anything else to text before matching.
    """
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in model output: {text[:200]}")
    return json.loads(match.group(0))


def _as_text(content) -> str:
    """Coerce an OpenAI-style message content (str | dict | list | None) to str."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content)


def _post_with_retry(url: str, *, retries: int = 2, backoff: float = 1.5, **kwargs):
    """POST with a few retries on transient network errors / 429 / 5xx."""
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, **kwargs)
            if resp.status_code in _RETRY_STATUS and attempt < retries:
                time.sleep(backoff ** attempt)
                continue
            return resp
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(backoff ** attempt)


class BaseLLM:
    # Providers that natively support structured tool-calling flip this on.
    native_tools = False

    def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        raise NotImplementedError

    def step(self, messages: list[dict]) -> dict:
        """Return one agent step: {"tool", "args"} or {"final_answer"}.

        Default is text mode: ask the model for a JSON step and parse it.
        Native-tool clients override this to use the provider's tool API.
        """
        return parse_json_step(self.chat(messages))

    def chat_stream(self, messages: list[dict], temperature: float = 0.2):
        """Yield reply text in chunks. Default: one chunk (no true streaming)."""
        yield self.chat(messages, temperature)


def stream_text(client: "BaseLLM", messages: list[dict], sink=None) -> str:
    """Consume a client's stream, optionally forwarding each chunk to `sink`
    (e.g. to print live), and return the full concatenated text."""
    parts = []
    for chunk in client.chat_stream(messages):
        if not chunk:
            continue
        parts.append(chunk)
        if sink:
            sink(chunk)
    return "".join(parts)


def _iter_sse(resp):
    """Yield decoded 'data:' payloads from a streamed SSE response."""
    for raw in resp.iter_lines():
        if not raw:
            continue
        line = raw.decode() if isinstance(raw, bytes) else raw
        if line.startswith("data:"):
            yield line[5:].strip()


class OllamaClient(BaseLLM):
    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        resp = _post_with_retry(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature},
            },
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def chat_stream(self, messages: list[dict], temperature: float = 0.2):
        resp = _post_with_retry(
            f"{self.base_url}/api/chat",
            json={"model": self.model, "messages": messages, "stream": True,
                  "options": {"temperature": temperature}},
            timeout=300, stream=True,
        )
        resp.raise_for_status()
        for raw in resp.iter_lines():
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            chunk = data.get("message", {}).get("content", "")
            if chunk:
                yield chunk
            if data.get("done"):
                break


class OpenAIClient(BaseLLM):
    """OpenAI API and any OpenAI-compatible endpoint (change base_url)."""

    def __init__(self, model: str, base_url: str = "https://api.openai.com/v1",
                 api_key_env: str = "OPENAI_API_KEY", use_tools: bool = False):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.native_tools = use_tools
        self.api_key = os.environ.get(api_key_env, "")
        if not self.api_key:
            raise RuntimeError(
                f"Missing API key: set the {api_key_env} environment variable, e.g.\n"
                f"  export {api_key_env}=sk-..."
            )

    def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        resp = _post_with_retry(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages, "temperature": temperature},
            timeout=300,
        )
        resp.raise_for_status()
        return _as_text(resp.json()["choices"][0]["message"].get("content"))

    def step(self, messages: list[dict]) -> dict:
        if not self.native_tools:
            return super().step(messages)
        from agent.tools import openai_tools
        resp = _post_with_retry(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages, "temperature": 0.2,
                  "tools": openai_tools(), "tool_choice": "auto"},
            timeout=300,
        )
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        calls = msg.get("tool_calls")
        if calls:
            fn = calls[0]["function"]
            args = json.loads(fn.get("arguments") or "{}")
            return {"thought": "", "tool": fn["name"], "args": args}
        return {"final_answer": _as_text(msg.get("content"))}

    def chat_stream(self, messages: list[dict], temperature: float = 0.2):
        resp = _post_with_retry(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages,
                  "temperature": temperature, "stream": True},
            timeout=300, stream=True,
        )
        resp.raise_for_status()
        for data in _iter_sse(resp):
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = obj.get("choices", [{}])[0].get("delta", {}).get("content")
            if delta:
                yield delta


class AnthropicClient(BaseLLM):
    """Anthropic Messages API (Claude models)."""

    def __init__(self, model: str, base_url: str = "https://api.anthropic.com",
                 api_key_env: str = "ANTHROPIC_API_KEY", max_tokens: int = 4096,
                 use_tools: bool = False):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.native_tools = use_tools
        self.api_key = os.environ.get(api_key_env, "")
        if not self.api_key:
            raise RuntimeError(
                f"Missing API key: set the {api_key_env} environment variable, e.g.\n"
                f"  export {api_key_env}=sk-ant-..."
            )

    def _split_system(self, messages):
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        chat_messages = [m for m in messages if m["role"] != "system"]
        return system, chat_messages

    def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        # Anthropic takes system prompts as a top-level field, not a message role
        system, chat_messages = self._split_system(messages)
        resp = _post_with_retry(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": system,
                "messages": chat_messages,
                "temperature": temperature,
            },
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    def step(self, messages: list[dict]) -> dict:
        if not self.native_tools:
            return super().step(messages)
        from agent.tools import anthropic_tools
        system, chat_messages = self._split_system(messages)
        resp = _post_with_retry(
            f"{self.base_url}/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            json={"model": self.model, "max_tokens": self.max_tokens, "system": system,
                  "messages": chat_messages, "temperature": 0.2, "tools": anthropic_tools()},
            timeout=300,
        )
        resp.raise_for_status()
        content = resp.json().get("content", [])
        for block in content:
            if block.get("type") == "tool_use":
                return {"thought": "", "tool": block["name"], "args": block.get("input", {})}
        text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        return {"final_answer": text}

    def chat_stream(self, messages: list[dict], temperature: float = 0.2):
        system, chat_messages = self._split_system(messages)
        resp = _post_with_retry(
            f"{self.base_url}/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            json={"model": self.model, "max_tokens": self.max_tokens, "system": system,
                  "messages": chat_messages, "temperature": temperature, "stream": True},
            timeout=300, stream=True,
        )
        resp.raise_for_status()
        for data in _iter_sse(resp):
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "content_block_delta":
                txt = obj.get("delta", {}).get("text", "")
                if txt:
                    yield txt


class CodexCLIClient(BaseLLM):
    """Uses the official OpenAI Codex CLI with a ChatGPT subscription login.

    Setup (one time):
        npm install -g @openai/codex
        codex login    # opens a browser for ChatGPT OAuth; tokens live in ~/.codex/

    This client shells out to `codex exec` per request, so no API key is
    needed - billing goes through the user's ChatGPT Plus/Pro subscription.
    """

    def __init__(self, model: str | None = None):
        self.model = model

    def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        # Codex CLI takes a single prompt, so flatten the chat history
        prompt = "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages)
        cmd = ["codex", "exec", "--skip-git-repo-check"]
        if self.model:
            cmd += ["-m", self.model]
        cmd.append(prompt)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except FileNotFoundError:
            raise RuntimeError(
                "Codex CLI not found. Install it with: npm install -g @openai/codex\n"
                "Then run: codex login"
            )
        if proc.returncode != 0:
            raise RuntimeError(f"codex CLI failed: {proc.stderr[:500]}")
        return proc.stdout.strip()


# Hosted providers with OpenAI-compatible APIs: export the key env var and go
OPENAI_COMPATIBLE_PRESETS = {
    "groq":       ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "mistral":    ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "deepseek":   ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "xai":        ("https://api.x.ai/v1", "XAI_API_KEY"),
    "gemini":     ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "together":   ("https://api.together.xyz/v1", "TOGETHER_API_KEY"),
}


def _resolve_use_tools(config: dict, provider_default: bool) -> bool:
    """agent.native_tools: true|false forces it; 'auto' (default) uses the
    provider's sensible default (on for hosted APIs, off for local servers)."""
    pref = config.get("agent", {}).get("native_tools", "auto")
    if pref in (True, "true", "on"):
        return True
    if pref in (False, "false", "off"):
        return False
    return provider_default


class CachingLLM(BaseLLM):
    """Wrap a client with an on-disk cache for chat() responses, keyed by
    model + messages. Skips repeated identical calls (e.g. re-reflection).
    Tool steps and streaming pass straight through."""

    def __init__(self, inner: BaseLLM, cache_dir: str):
        self.inner = inner
        self.native_tools = inner.native_tools
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _key(self, messages) -> str:
        import hashlib
        blob = getattr(self.inner, "model", "") + json.dumps(messages, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def chat(self, messages, temperature: float = 0.2) -> str:
        path = os.path.join(self.cache_dir, self._key(messages) + ".txt")
        if os.path.exists(path):
            with open(path) as f:
                return f.read()
        out = self.inner.chat(messages, temperature)
        try:
            with open(path, "w") as f:
                f.write(out)
        except OSError:
            pass
        return out

    def step(self, messages):
        return self.inner.step(messages)

    def chat_stream(self, messages, temperature: float = 0.2):
        return self.inner.chat_stream(messages, temperature)


def _maybe_cache(client: BaseLLM, config: dict) -> BaseLLM:
    if config.get("cache", {}).get("enabled"):
        cache_dir = os.path.join(config.get("memory", {}).get("path", ".memory"), "llm_cache")
        return CachingLLM(client, cache_dir)
    return client


def make_llm(config: dict) -> BaseLLM:
    """Build the right client from config.yaml."""
    return _maybe_cache(_build_llm(config), config)


def _build_llm(config: dict) -> BaseLLM:
    provider = config.get("provider", "ollama")
    model = config["model"]
    if provider in OPENAI_COMPATIBLE_PRESETS:
        base_url, key_env = OPENAI_COMPATIBLE_PRESETS[provider]
        return OpenAIClient(model, base_url, key_env, _resolve_use_tools(config, True))
    if provider == "codex":
        return CodexCLIClient(model or None)
    if provider == "ollama":
        return OllamaClient(model, config.get("ollama_url", "http://localhost:11434"))
    if provider in ("openai", "openai-compatible"):
        oc = config.get("openai", {})
        # Real OpenAI supports tools; arbitrary local endpoints often don't.
        default = provider == "openai"
        return OpenAIClient(model, oc.get("base_url", "https://api.openai.com/v1"),
                            oc.get("api_key_env", "OPENAI_API_KEY"),
                            _resolve_use_tools(config, default))
    if provider == "anthropic":
        ac = config.get("anthropic", {})
        return AnthropicClient(model, ac.get("base_url", "https://api.anthropic.com"),
                               ac.get("api_key_env", "ANTHROPIC_API_KEY"),
                               ac.get("max_tokens", 4096),
                               _resolve_use_tools(config, True))
    if provider == "cloudflare":
        # Cloudflare Workers AI exposes an OpenAI-compatible endpoint, but the
        # base URL is account-scoped, so it can't be a static preset.
        cf = config.get("cloudflare", {})
        key_env = cf.get("api_key_env", "CLOUDFLARE_API_TOKEN")
        account_id = cf.get("account_id") or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        if not account_id:
            raise RuntimeError(
                "Cloudflare needs your account id. Set cloudflare.account_id in "
                "config.yaml (or the CLOUDFLARE_ACCOUNT_ID env var), and export your "
                f"API token as {key_env}."
            )
        base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"
        return OpenAIClient(model, base_url, key_env, _resolve_use_tools(config, True))
    raise ValueError(
        f"Unknown provider: {provider}. Use ollama, openai, anthropic, codex, "
        f"cloudflare, openai-compatible, or one of: {', '.join(OPENAI_COMPATIBLE_PRESETS)}"
    )
