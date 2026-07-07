"""Config loading with sensible defaults so the `corvus` command works anywhere.

A config.yaml in the current directory overrides defaults (deep-merged per
top-level section). Run `corvus init` to write a starter config.yaml.
"""
import os

import yaml

DEFAULT_CONFIG = {
    "provider": "ollama",
    "model": "qwen2.5-coder:14b",
    "ollama_url": "http://localhost:11434",
    "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
    "anthropic": {"base_url": "https://api.anthropic.com",
                  "api_key_env": "ANTHROPIC_API_KEY", "max_tokens": 4096},
    "cloudflare": {"account_id": "", "api_key_env": "CLOUDFLARE_API_TOKEN"},
    "agent": {"max_iterations": 12, "sandbox_timeout": 30, "max_history_messages": 24,
              "native_tools": "auto"},
    "memory": {"path": ".memory", "backend": "auto", "embedding": "hash",
               "lessons_top_k": 5, "episodes_top_k": 3, "notes_top_k": 5,
               "skills_top_k": 2, "lesson_dedup_distance": 0.15, "dedup_distance": 0.1},
    "improve": {"max_lessons": 200, "max_attempts": 2},
    "computer_control": {"enabled": False, "require_confirmation": True, "allowlist": []},
    "server": {"host": "127.0.0.1", "port": 8000, "api_token": "", "cors_origins": ["*"]},
    "team": {"tokens": {}},   # {token: "member"|"viewer"} - owner is server.api_token
    "repo": {"path": "", "autocommit": True},
    "search": {"provider": "auto", "max_results": 5},
    "verify": {"checks": ["auto"], "timeout": 120},
    "sandbox": {"backend": "subprocess", "image": "python:3.12"},
    "routing": {"enabled": False, "cheap": "", "strong": ""},
    "cache": {"enabled": False},
    "plan": "free",   # free = any model provider with your own key; never gated
}


def load_config(path: str = "config.yaml") -> dict:
    config = {k: (v.copy() if isinstance(v, dict) else v) for k, v in DEFAULT_CONFIG.items()}
    if os.path.exists(path):
        with open(path) as f:
            user = yaml.safe_load(f) or {}
        for key, value in user.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
    return config


def write_default_config(path: str = "config.yaml") -> bool:
    """Write a starter config.yaml. Returns False if one already exists."""
    if os.path.exists(path):
        return False
    with open(path, "w") as f:
        yaml.safe_dump(DEFAULT_CONFIG, f, sort_keys=False)
    return True
