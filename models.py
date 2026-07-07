"""Curated model suggestions per provider, plus the pure helpers the CLI uses
to render a picker and resolve a user's choice.

These lists are starting points, NOT exhaustive or guaranteed-current - model
availability changes over time. You can always type any model id your provider
supports; if it isn't in the list, just type it in.
"""

# Ordered so the terminal shows providers in a sensible sequence.
PROVIDERS = [
    "ollama", "openai", "anthropic", "cloudflare", "codex",
    "groq", "mistral", "deepseek", "xai", "gemini",
    "openrouter", "together", "openai-compatible",
]

PROVIDER_MODELS = {
    "ollama": ["qwen2.5-coder:14b", "qwen2.5-coder:32b", "hermes3",
               "llama3.3", "deepseek-coder-v2"],
    "openai": ["gpt-4o", "gpt-4o-mini", "o3-mini", "o1"],
    "anthropic": ["claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-1"],
    "cloudflare": ["@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                   "@cf/meta/llama-3.1-8b-instruct",
                   "@cf/qwen/qwen2.5-coder-32b-instruct",
                   "@cf/deepseek-ai/deepseek-coder-6.7b-instruct-awq"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant",
             "qwen-2.5-coder-32b", "deepseek-r1-distill-llama-70b"],
    "mistral": ["codestral-latest", "mistral-large-latest", "mistral-small-latest"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"],
    "xai": ["grok-3", "grok-3-mini", "grok-2"],
    "gemini": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
    # Aggregators / custom endpoints are inherently open-ended - a couple of
    # examples, then type whatever id you want.
    "openrouter": ["anthropic/claude-sonnet-4.5", "openai/gpt-4o",
                   "meta-llama/llama-3.3-70b-instruct", "qwen/qwen-2.5-coder-32b-instruct"],
    "together": ["meta-llama/Llama-3.3-70B-Instruct-Turbo",
                 "Qwen/Qwen2.5-Coder-32B-Instruct", "deepseek-ai/DeepSeek-V3"],
    "codex": [],              # uses your ChatGPT subscription; model is optional
    "openai-compatible": [],  # whatever your endpoint serves
}


def models_for(provider: str) -> list:
    return PROVIDER_MODELS.get(provider, [])


# Task words that signal a hard problem worth routing to the stronger model.
_HARD_HINTS = ("refactor", "architecture", "debug", "optimize", "design",
               "concurren", "security", "performance", "algorithm", "migrate")


def route(task: str, cheap: str, strong: str, threshold: int = 200) -> str:
    """Pick the cheap model for simple/short tasks, the strong one for hard/long
    tasks. A tiny, transparent heuristic - no extra model call."""
    t = (task or "").lower()
    hard = len(task or "") > threshold or any(h in t for h in _HARD_HINTS)
    return strong if hard else cheap


def resolve_model_choice(raw: str, options: list) -> str:
    """Map a picker response to a model id.

    A bare in-range number selects from `options`; anything else is returned
    verbatim so users can type any model id. An out-of-range number returns ""
    to signal an invalid pick.
    """
    raw = (raw or "").strip()
    if raw.isdigit():
        idx = int(raw) - 1
        return options[idx] if 0 <= idx < len(options) else ""
    return raw


def render_model_menu(provider: str, current: str | None = None) -> str:
    lines = [f"Models for provider '{provider}':"]
    options = models_for(provider)
    if options:
        for i, m in enumerate(options, 1):
            lines.append(f"  {i}. {m}" + ("   <- current" if m == current else ""))
    else:
        lines.append("  (no preset list for this provider - type any model id it serves)")
    lines.append("Pick a number, or type any model id to use your own.")
    return "\n".join(lines)


def render_provider_menu(current: str | None = None) -> str:
    lines = ["Providers:"]
    for i, p in enumerate(PROVIDERS, 1):
        lines.append(f"  {i}. {p}" + ("   <- current" if p == current else ""))
    lines.append("Pick a number, or type any provider name.")
    return "\n".join(lines)


def resolve_provider_choice(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.isdigit():
        idx = int(raw) - 1
        return PROVIDERS[idx] if 0 <= idx < len(PROVIDERS) else ""
    return raw
