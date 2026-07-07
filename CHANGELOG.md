# Changelog

## 1.1.0

Frontier feature wave. 125 tests, ruff-clean, CI (GitHub Actions + GitLab) on
both memory backends. **Validated live** end-to-end against Cloudflare Workers AI
(`@cf/qwen/qwen2.5-coder-32b-instruct`): the agent wrote real code, ran pytest,
self-corrected, passed, and banked lessons/skills across two tasks.

- **Fix**: coerce non-string message content (Cloudflare returns already-parsed
  dict content from its OpenAI-compatible endpoint) so the agent loop parses it.
- **Packaging**: `setup.py` shim for legacy/old-pip editable installs; the server
  locates the PWA `web/` from the working dir too (non-editable installs).
- **Robustness**: friendly errors (no tracebacks) when migrating to a missing
  backend or importing skills from a bad path; MIT LICENSE added.

- **Fair billing (`corvus plan`)**: entitlements encode the rule that *any* model
  provider works on the FREE plan with your own key — provider access is never
  gated; paid tiers only add hosted conveniences.
- **Repo indexing** (`search_code` tool): TF-IDF code retrieval over a project.
- **Surgical `edit_file`**: unique search/replace instead of whole-file rewrites.
- **Multi-language verification** (`corvus verify`): pytest + lint + npm/go/cargo,
  auto-detected; uninstalled tools skip rather than fail.
- **Multi-agent** (`corvus team`): planner → coder → reviewer.
- **Docker sandbox backend** with automatic subprocess fallback.
- **Observability** (`corvus stats`): per-run log (steps, time, tokens, success),
  plus model routing (cheap vs. strong) and an on-disk LLM cache.
- **Bench regression gate** (`corvus bench --check`): fails on a pass-rate drop.
- **Team layer**: API roles (owner/member/viewer), audit log, shared skill
  library sync (`/api/skills/export` + `/api/skills/import`).
- **Pluggable web search**: `web_search` now supports Brave / Tavily / SerpAPI
  (API keys) with a keyless DuckDuckGo fallback, selected via `search.provider`.
  Fixes the old DuckDuckGo-only scrape, which current anti-bot measures broke.
- **`corvus ship <dest>`**: graduate a verified sandbox project to a real folder
  (draft → verify → ship). Conflict-safe (won't overwrite without `--force`),
  `--dry-run` preview, optional `--git` init + commit; `/ship <dest>` in the REPL.

## 1.0.0

First stable release. Corvus is a self-improving autonomous coding agent that
runs in the terminal, over an HTTP API, and on mobile (PWA + native), on models
from Ollama, OpenAI, Anthropic, Cloudflare, and 9 other providers.

### Agent & models
- ReAct loop with a verified self-improvement cycle (see "Self-improvement").
- 13 providers incl. **Cloudflare Workers AI**; per-provider model picker with a
  type-your-own fallback (`/model`, `/models`, `corvus models`).
- **Native tool-calling** for OpenAI/Anthropic/Cloudflare, with a JSON-in-text
  fallback for Ollama/local models (`agent.native_tools: auto|true|false`).
- **Streaming**: token-by-token replies and a live `→ tool(args)` step trace in
  the terminal; an SSE endpoint streams the same trace to the apps.

### Self-improvement
- Attempt → verify with pytest (only when the task produced tests) → reflect →
  bank/reinforce/prune lessons → retry with critique on failure → harvest
  verified code into a skill library. Relevant lessons/notes/episodes/skills are
  injected into future prompts. No retraining.

### Working on your code
- **Real-repo mode**: point Corvus at an existing project (`corvus run --repo`,
  `/repo`), path-confined to that folder, with git auto-commit on verified passes
  and `corvus repo diff|log|revert`.
- File creation for coding tasks in a sandboxed workspace; opt-in **computer**
  tool to run commands on the host (off by default, per-command y/N, plus an
  **allowlist** that never auto-approves chained commands).

### Memory backends
- **chroma** (vector) or **lite** (pure-Python TF-IDF, zero native deps);
  auto-selected, or forced via `memory.backend` / `CORVUS_MEMORY_BACKEND`.
- `corvus memory info` and `corvus memory migrate --to lite|chroma` to move
  learned state between backends.

### Interfaces & platforms
- **HTTP API** (`corvus serve`, token auth) with a streaming task endpoint.
- Installable **PWA** and an **Expo native iOS/Android** app, both live-tracing.
- **Android/Termux**: runs the whole agent on-device (lite backend,
  `termux-install.sh`).
- Checkpoints, scheduler, skill export/import, and a `bench` suite.

### Security & robustness (from the initial review)
- Fixed a workspace path-confinement bypass; API keys are stripped from
  sandboxed code's environment; verification is gated so non-test tasks aren't
  falsely failed; per-task workspace reset; bounded prompt history; shared memory
  client; per-agent tool state; HTTP retry on 429/5xx; scheduler past-date guard.

### Quality
- 79+ tests, ruff-clean, CI runs the suite on **both** memory backends.
- Requires Python 3.10+.
