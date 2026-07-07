# Corvus Agent

A self-improving autonomous coding agent with a terminal interface, an HTTP API,
and mobile apps (PWA + native iOS/Android).
Works with **open-source models** (via [Ollama](https://ollama.com)) or **hosted APIs**
(OpenAI, Anthropic Claude, Cloudflare Workers AI, Groq, Mistral, DeepSeek, xAI,
Gemini, OpenRouter, Together, your ChatGPT subscription via Codex CLI, or any
OpenAI-compatible endpoint). It uses **provider-native tool-calling** where
available (with a JSON fallback for local models) and **streams** its work live.

It gets better at coding tasks over time without retraining: after every task it
reflects on its attempt, distills lessons, and injects the most relevant lessons,
memories, and proven skills into future prompts (Reflexion-style continual improvement).

> Validated live against Cloudflare Workers AI (`@cf/qwen/qwen2.5-coder-32b-instruct`):
> the agent wrote real code, ran pytest, self-corrected to green, and reused what it
> learned on the next task. 125 tests, ruff-clean, CI on both memory backends.

## How self-improvement works

```
 task ──> agent loop (reason → tool → observe) ──> verify (pytest)
              │                                        │ fail? retry with critique
   next task prompt <── lessons + memories + skills <── reflect (self-critique)
```

1. **Attempt**: ReAct loop with tools (`write_file`, `edit_file`, `run_python`,
   `run_tests`, `web_search`, `search_code`, `remember`, ...)
2. **Verify**: tests are the ground truth (pytest + optional lint / JS / Go / Rust), not the model's opinion
3. **Auto-retry**: if verification fails, the agent's own critique is fed back and it tries again
4. **Reflect**: the model critiques its own transcript and proposes lessons
5. **Evolve**: lessons are deduped, scored, reinforced, and pruned in a vector store
6. **Self-managed memory**: `remember`/`recall` tools let the agent save insights
   to its own long-term memory mid-task, not just after reflection
7. **Skill library**: code from pytest-verified successes is banked and injected
   into similar future tasks (Voyager-style), so proven solutions get reused
8. **AI skill builder**: the agent can deliberately author named, documented skills
   with its `build_skill` tool - share them via `corvus skills export`
9. **Community skills**: import skill packs from files or URLs with
   `corvus skills import` (starter pack in `community/`)
10. **Checkpoints**: love how your agent has evolved? Snapshot its learned state
    with `corvus checkpoint save <name>` and start new conversations from it anytime

Run `corvus bench` periodically; `evals/history.json` tracks pass rate and step
count so you can see improvement objectively.

## Install

Requires **Python 3.10+**.

```bash
pip install -e .          # base install (pure-Python "lite" memory, runs anywhere)
pip install -e ".[full]"  # + chromadb for faster vector memory (desktop/server)
corvus init               # writes a starter config.yaml
```

The base install has **no native dependencies**, so it works on Termux/Android
too. Memory automatically uses the pure-Python `lite` backend unless chromadb is
present; pick explicitly with `memory.backend: auto|chroma|lite` (or the
`CORVUS_MEMORY_BACKEND` env var).

### Android / Termux

Corvus runs **on the phone itself** in Termux - the agent, not just a client:

```bash
pkg install python git
git clone <your-repo> corvus && cd corvus
bash termux-install.sh    # installs the lite backend, no compilation
```

Then use a small on-device model via `pkg install ollama`, or point `config.yaml`
at a hosted API (Cloudflare/OpenAI/Anthropic/Groq/…). You can also run
`corvus serve` and open the PWA right in your phone's browser.

## Pick a model provider

### Open-source models (default, free, private)

```bash
ollama pull qwen2.5-coder:14b   # or: hermes3, llama3.1, deepseek-coder-v2
```

### Hosted APIs (set provider + model in config.yaml, export the key)

| provider     | example model            | env var             |
|--------------|--------------------------|---------------------|
| `openai`     | gpt-4o                   | `OPENAI_API_KEY`    |
| `anthropic`  | claude-sonnet-4-5        | `ANTHROPIC_API_KEY` |
| `groq`       | llama-3.3-70b-versatile  | `GROQ_API_KEY`      |
| `mistral`    | codestral-latest         | `MISTRAL_API_KEY`   |
| `deepseek`   | deepseek-chat            | `DEEPSEEK_API_KEY`  |
| `xai`        | grok-3                   | `XAI_API_KEY`       |
| `gemini`     | gemini-2.5-pro           | `GEMINI_API_KEY`    |
| `openrouter` | any OpenRouter model id  | `OPENROUTER_API_KEY`|
| `together`   | any Together model id    | `TOGETHER_API_KEY`  |
| `cloudflare` | @cf/meta/llama-3.3-70b-instruct-fp8-fast | `CLOUDFLARE_API_TOKEN` |

Cloudflare Workers AI also needs your **account id** - set `cloudflare.account_id`
in `config.yaml` (or export `CLOUDFLARE_ACCOUNT_ID`). Then export the token and
select the provider in `config.yaml` (`provider: cloudflare`) or on the fly:

```bash
export CLOUDFLARE_API_TOKEN=...        # Workers AI token from the Cloudflare dashboard
corvus
corvus> /provider cloudflare
corvus> /model @cf/meta/llama-3.3-70b-instruct-fp8-fast
```

For anything else, use `openai-compatible` and set `openai.base_url`
(works with LM Studio, vLLM, llama.cpp server, etc.).

### ChatGPT subscription via Codex CLI (no API key)

ChatGPT Plus/Pro subscriptions do not expose an API key, but the official
Codex CLI signs in with your ChatGPT account via browser OAuth:

```bash
npm install -g @openai/codex
codex login        # opens a browser; tokens are stored locally in ~/.codex/
```

Then set `provider: codex` (or `/provider codex` in the terminal). Corvus shells
out to `codex exec`, so usage bills to your subscription. API keys for other
providers are only ever read from environment variables and never stored in the repo.

## Three ways to work

1. **Draft → verify → ship** (safest): Corvus builds and runs code in an isolated
   sandbox, fixing it until pytest passes, then you graduate the finished project
   to a real folder — nothing lands on your machine until it's verified.

   ```bash
   corvus run "Build a CLI todo app with tests"   # drafts + verifies in the sandbox
   corvus ship ~/projects/todo --git              # copy it out as a real git project
   corvus ship ~/projects/todo --dry-run          # preview first; --force to overwrite
   ```

2. **Real-repo mode**: edit an existing project in place (path-confined, git
   auto-commit on verified passes): `corvus run --repo ~/projects/todo "add search"`.

3. **Just chat**: `corvus` for an interactive terminal.

`ship` copies only source files (skips `__pycache__`/caches), refuses to
overwrite existing files without `--force`, and can `git init` + commit the new
project. In the terminal use `/ship <dest>` right after a run.

## Run it

```bash
corvus                          # interactive terminal
corvus run "Write a prime sieve with pytest tests and make them pass"
                              # ...then keep chatting with Corvus about the result
corvus ship ~/projects/sieve    # graduate the verified project to a real folder
corvus team "Build a rate limiter with tests"   # planner -> coder -> reviewer
corvus verify ~/projects/app    # run the project's checks (pytest/lint/js/go/rust)
corvus stats                    # run history: pass rate, steps, time, ~tokens
corvus plan                     # show plan entitlements (free = any provider, BYO key)
corvus bench                    # measure improvement over time
corvus bench --check            # ...and fail (exit 1) on a pass-rate regression
corvus memory info              # show the active memory backend + counts
corvus memory migrate --to lite # move learned state between chroma <-> lite

# Timed tasks: start at a certain time or date
corvus schedule "Refactor utils.py and add tests" --at "2026-07-08 09:00"
corvus schedule "Write tests for the parser" --in 2h     # 30m / 2h / 1d
corvus schedule --list
corvus scheduler                # start the loop that runs due tasks

# Skills: build, share, import
corvus skills list
corvus skills export my-skills.json
corvus skills import community/skills-starter.json    # or a URL

# Checkpoints: snapshot the agent's learned state
corvus checkpoint save my-best-agent
corvus checkpoint list
corvus checkpoint load my-best-agent
```

Inside the terminal:

```
corvus> Write a JSON config validator with tests
corvus> /lessons             # rules the agent learned from reflection
corvus> /memories            # facts the agent chose to remember itself
corvus> /skills              # verified reusable code in the skill library
corvus> /models              # model suggestions for the current provider
corvus> /model gpt-4o        # switch model (or /model with no arg to pick one)
corvus> /provider groq       # switch provider (or /provider to pick one)
corvus> /repo ~/projects/app # work on an existing project; /repo off to exit
corvus> /ship ~/projects/app # copy the verified sandbox project out (git-inits it)
corvus> /grant               # allow computer control (y/N per command)
corvus> /allow git *         # auto-approve matching single commands
corvus> /quit
```

## Project layout

```
cli.py       `corvus` command (chat/run/team/verify/ship/repo/memory/stats/plan/serve/...)
settings.py  config defaults + config.yaml loader
models.py    per-provider model catalog + picker + cheap/strong routing
scheduler.py timed tasks (run at a set time/date or after a delay)
repo.py      real-repo mode git helpers (auto-commit / diff / log / revert)
promote.py   `corvus ship`: copy a verified project out to a real folder
index.py     repo indexing + code retrieval (the search_code tool)
verifier.py  pluggable verification (pytest / lint / npm / go / cargo)
telemetry.py run log + `corvus stats` (steps, time, tokens, pass rate)
plan.py      plan entitlements (fair BYO-key billing)
team.py      API roles (owner/member/viewer) + audit log
server.py    `corvus serve` HTTP API + SSE stream (serves the PWA)
agent/       core.py (ReAct loop), tools.py, search.py, llm.py, session.py, orchestrator.py (team)
memory/      lessons/episodes/notes/skills + _client.py (chroma|lite) + lite.py (pure-Python)
improve/     reflect.py (self-critique), evolve.py (bank lessons, prune)
sandbox/     runner.py (subprocess or docker execution, secrets stripped)
evals/       benchmark.py + tasks.json (improvement tracking + regression gate)
web/         installable PWA client        mobile/  Expo iOS/Android app
tests/       suite run by CI (.gitlab-ci.yml: ruff + pytest on both backends)
workspace/   scratch dir where the agent drafts and runs code (gitignored)
```

## Computer control (opt-in, permission required)

Corvus has a `computer` tool that can run commands on your actual machine
(outside the sandbox). For safety it is **off by default**:

1. Grant permission with `/grant` in the terminal (or `computer_control.enabled: true` in config.yaml)
2. Even when granted, **every single command** shows a y/N prompt before it runs
3. Revoke anytime with `/revoke`

## How memory and self-improvement work

Corvus's improvement is stored as **retrievable memory**, not retrained model weights:

| store | what it holds | how it grows |
|---|---|---|
| Lessons | short imperative rules | distilled by self-critique after every task; reinforced when re-learned, pruned when weak |
| Episodes | past tasks, outcomes, critiques | added after every task, retrieved by similarity |
| Notes | facts the agent chose to save | the agent calls `remember` mid-task |
| Skills | working code (harvested / built / community) | banked on verified success, authored via `build_skill`, or imported |

Before each new task, the most relevant items from all four stores are injected
into the prompt, so the same base model behaves smarter over time. Because the
learned state lives in `.memory/`, a **checkpoint is a snapshot of that folder**:
save an agent you like, and any new conversation loaded from that checkpoint
starts with everything it had learned.

## API server & mobile apps

Corvus can run as an HTTP service that the mobile apps (and any client) talk to.
The agent runs on your computer/server; the phone is a client.

```bash
pip install -e ".[server]"          # adds FastAPI + uvicorn
export CORVUS_API_TOKEN=your-secret  # required before exposing beyond localhost
corvus serve --host 0.0.0.0 --port 8000
```

Endpoints: `GET /health` (open); reads `GET /api/lessons`, `/api/memories`,
`/api/skills`, `/api/skills/export`, `/api/checkpoints`, `/api/audit`; writes
`POST /api/task`, `GET /api/task/stream` (SSE live trace), `POST /api/checkpoint`,
`POST /api/skills/import`. If the PWA is present it's served at `/`.

**Roles**: the `api_token` is the owner. Add teammates in `team.tokens`
(`{token: "member"|"viewer"}`) — members can read + write, viewers are read-only,
and every write is recorded to an audit log (`GET /api/audit`).

**PWA** (`web/`): open the served URL on your phone and "Add to Home Screen" —
installs on iOS and Android, works offline for the app shell. Served automatically
by `corvus serve`.

**Native app** (`mobile/`): an Expo / React Native project for real iOS/Android
builds. `cd mobile && npm install && npm start` for development; build store
binaries with `eas build -p ios|android`. See `mobile/README.md`.

## Native tool-calling & streaming

- `agent.native_tools: auto` (config) uses each provider's structured tool API
  for OpenAI / Anthropic / Cloudflare / hosted models, and falls back to
  JSON-in-text for Ollama and local endpoints. Force with `true`/`false`.
- The terminal streams replies token-by-token and shows a live step trace
  (`→ tool(args)`) as the agent works.

## Computer-control allowlist

Beyond the master switch and per-command `y/N`, you can auto-approve trusted
commands: set `computer_control.allowlist` (e.g. `["git *", "npm run *"]`) or use
`/allow git *` in the terminal. Chained commands (`;`, `&&`, `|`, `>` …) are
**never** auto-approved, even if the leading command matches.

## Web search (pluggable, BYO key)

The `web_search` tool has swappable backends via `search.provider`:

| provider     | key                | notes                    |
|--------------|--------------------|--------------------------|
| `brave`      | `BRAVE_API_KEY`    | reliable, cited          |
| `tavily`     | `TAVILY_API_KEY`   | LLM-oriented results     |
| `serpapi`    | `SERPAPI_API_KEY`  | Google via SerpAPI       |
| `duckduckgo` | *(none)*           | keyless, best-effort     |
| `auto`       | —                  | use whichever key is set, else DuckDuckGo |

The keyless backend works with zero setup but is often rate-limited; set any one
key for dependable, cited search.

## Working on large repos

- `search_code` (tool): TF-IDF retrieval over the current project, so the agent
  finds the right files instead of guessing — scales to big codebases.
- `edit_file(path, find, replace)` (tool): a **surgical** edit that replaces an
  exact, unique snippet rather than rewriting whole files (safer on large files;
  refuses ambiguous matches).

## Verification (multi-language)

`corvus verify [path]` and the self-improvement loop use a pluggable verifier
that auto-detects the project and runs the right checks — **pytest**, **ruff**
lint, **npm test**, **go test**, **cargo test**. A check whose tool isn't
installed is skipped, not failed. Configure with `verify.checks` (`["auto"]`
detects, or list explicit checks).

## Multi-agent (`corvus team`)

`corvus team "<task>"` runs a **planner → coder → reviewer** team on top of the
single agent: the planner drafts steps, the coder executes them through the
verified loop, and the reviewer critiques the result and can request another pass.

## Observability, routing & caching

- `corvus stats` summarizes past runs (pass rate, avg steps, wall-clock time,
  rough token use, per-model breakdown) from a per-run log in `.memory/runs.jsonl`.
- **Model routing** (`routing.enabled` + `routing.cheap`/`routing.strong`): send
  simple/short tasks to a cheap model and hard/long ones to a strong model.
- **LLM cache** (`cache.enabled`): an on-disk cache of chat responses to skip
  repeated identical calls.

## Fair pricing (`corvus plan`)

`corvus plan` shows the entitlement model. The rule, enforced in code: **any
model provider works on the FREE plan with your own key (or local Ollama) —
provider access is never gated.** Paid tiers only add hosted conveniences
(memory sync, team library, RBAC/audit, SSO, compliance), never model access.

## Sandbox isolation (subprocess or docker)

Set `sandbox.backend`:

- `subprocess` (default): fast; API keys/secrets are stripped from the child env.
- `docker`: run each execution in a throwaway container (`--network=none`, memory
  cap, no host env). Falls back to subprocess with a warning if docker is absent.
  The image (`sandbox.image`) must contain your project's runtime/deps.

## Safety note

The sandbox uses subprocesses with timeouts, workspace path confinement, and
strips API keys / tokens / secrets from the environment of code it runs, so a
prompt-injected snippet cannot read your credentials. This is defence in depth,
**not** a true security boundary: subprocesses still share the host. For
untrusted tasks, run the whole agent inside a container:

```bash
docker run --rm -it -v $PWD:/app -w /app python:3.12 bash
```
