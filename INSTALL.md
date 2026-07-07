# Installing Corvus

Corvus runs anywhere Python 3.10+ runs — Linux, macOS, Windows, and Android
(Termux). The base install has **no native dependencies**, so it won't fail on a
fresh machine.

- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Install options](#install-options)
- [Windows](#windows)
- [Android / Termux](#android--termux)
- [Pick a model provider](#pick-a-model-provider)
- [First run](#first-run)
- [API server + mobile apps](#api-server--mobile-apps)
- [Troubleshooting](#troubleshooting)

## Requirements

- **Python 3.10 or newer** (`python3 --version`)
- **git** (to clone) — optional if you install from a release zip
- A model: either a hosted API key (OpenAI, Anthropic, Cloudflare, Groq, …) or
  [Ollama](https://ollama.com) for fully local, private models

## Quick start

```bash
git clone https://github.com/FireworksAI26/corvus-agent.git
cd corvus-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e .          # base install (pure-Python "lite" memory)
corvus init               # writes config.yaml
export OPENAI_API_KEY=sk-...          # or any provider key; Ollama needs none
corvus run "write a prime sieve in primes.py with pytest tests and make them pass"
```

## Install options

| Command | What you get |
|---|---|
| `pip install -e .` | Base: terminal agent + pure-Python **lite** memory. Zero native builds. |
| `pip install -e ".[full]"` | Adds **chromadb** (faster vector memory) for desktop/server. |
| `pip install -e ".[server]"` | Adds **FastAPI + uvicorn** for `corvus serve` and the PWA. |
| `pip install -e ".[full,server]"` | Everything. |

Installing from a **release zip** instead of git:

```bash
unzip corvus-agent.zip && cd corvus-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Memory backend auto-selects: **chroma** if installed, otherwise **lite**. Force
it with `memory.backend: auto|chroma|lite` in `config.yaml`, or the
`CORVUS_MEMORY_BACKEND` env var.

## Windows

```powershell
git clone https://github.com/FireworksAI26/corvus-agent.git
cd corvus-agent
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
corvus init
```

## Android / Termux

Corvus runs **on the phone itself** — the agent, not just a client. Install
Termux from **F-Droid** (not the Play Store), then:

```bash
pkg install python git
git clone https://github.com/FireworksAI26/corvus-agent.git
cd corvus-agent
bash termux-install.sh    # installs the lite backend, no compilation
```

Then either run a small on-device model (`pkg install ollama`) or point
`config.yaml` at a hosted API. You can also `corvus serve` and open the PWA in
your phone's browser.

## Pick a model provider

Set `provider` + `model` in `config.yaml` (or switch live with `/provider` and
`/model`), and export the matching key:

| provider | example model | env var |
|---|---|---|
| `ollama` | `qwen2.5-coder:14b` | *(none — local)* |
| `openai` | `gpt-4o` | `OPENAI_API_KEY` |
| `anthropic` | `claude-sonnet-4-5` | `ANTHROPIC_API_KEY` |
| `cloudflare` | `@cf/qwen/qwen2.5-coder-32b-instruct` | `CLOUDFLARE_API_TOKEN` (+ `cloudflare.account_id`) |
| `groq` | `llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| `mistral` / `deepseek` / `xai` / `gemini` / `openrouter` / `together` | see README | `*_API_KEY` |
| `codex` | ChatGPT subscription (no key) | — |

Any provider works on the free/self-hosted install with your own key — provider
access is never gated (`corvus plan`).

## First run

```bash
corvus                               # interactive terminal
corvus run "Build a CLI todo app with tests"   # drafts + verifies in the sandbox
corvus ship ~/projects/todo --git    # graduate the verified project to a real folder
corvus run --repo ~/projects/todo "add a search command"   # or edit an existing repo
corvus team "Refactor the parser and add tests"            # planner -> coder -> reviewer
corvus bench                         # measure improvement over time
```

## API server + mobile apps

```bash
pip install -e ".[server]"
export CORVUS_API_TOKEN=your-secret  # required before exposing beyond localhost
corvus serve --host 0.0.0.0 --port 8000
```

- **PWA**: open the served URL on your phone → "Add to Home Screen". (Run
  `python web/gen_icons.py` once to generate the app icons.)
- **Native app**: `cd mobile && npm install && npm start`; build store binaries
  with `eas build`. See `mobile/README.md`.

## Troubleshooting

- **`corvus: command not found`** — activate the venv (`source .venv/bin/activate`),
  or run `python -m cli` from the project directory.
- **Old pip can't do `pip install -e .`** — upgrade pip (`pip install -U pip`);
  a `setup.py` shim is included for legacy toolchains.
- **`str | None` / syntax error on import** — you're on Python 3.9 or older;
  install 3.10+.
- **chromadb fails to build** (e.g., on a phone) — you don't need it; the base
  install uses the pure-Python `lite` backend. Use `memory.backend: lite`.
- **Web search returns nothing** — the keyless DuckDuckGo backend is often
  rate-limited; set `BRAVE_API_KEY`, `TAVILY_API_KEY`, or `SERPAPI_API_KEY` and
  `search.provider` for reliable results.
- **First run downloads a model** — with the chroma backend, the embedding model
  (~80MB) downloads once; the lite backend needs no download.
