#!/data/data/com.termux/files/usr/bin/bash
# Corvus installer for Termux (Android). Installs the agent with the pure-Python
# "lite" memory backend so nothing needs to compile. Run from the repo root:
#   bash termux-install.sh
set -e

echo "==> Corvus / Termux installer"

if [ ! -f pyproject.toml ] || ! grep -q "corvus-agent" pyproject.toml 2>/dev/null; then
  echo "Run this from the Corvus repo root (where pyproject.toml lives)." >&2
  exit 1
fi

echo "==> Installing Python + git (via pkg)"
pkg update -y >/dev/null 2>&1 || true
pkg install -y python git >/dev/null 2>&1 || pkg install -y python git

echo "==> Installing Corvus (base deps only - no native builds)"
python -m pip install --upgrade pip >/dev/null
python -m pip install -e .

echo "==> Forcing the pure-Python memory backend"
python - <<'PY'
import os
from settings import load_config, write_default_config
write_default_config()
# Ensure backend: lite in config.yaml
import re, io
p = "config.yaml"
s = open(p).read()
if re.search(r'^\s*backend:', s, re.M):
    s = re.sub(r'backend:\s*"?\w+"?', 'backend: "lite"', s, count=1)
else:
    s = s.replace('path: ".memory"', 'path: ".memory"\n  backend: "lite"', 1)
open(p, "w").write(s)
print("   memory.backend = lite")
PY

cat <<'EOF'

==> Done. Next steps:

  # Option A - fully on-device model (heavier; needs a capable phone):
  pkg install ollama && ollama serve &      # in one Termux session
  ollama pull qwen2.5-coder:1.5b            # a small coder model
  # config.yaml already defaults to ollama

  # Option B - a hosted API (lighter on the phone):
  #   edit config.yaml -> provider: cloudflare|openai|anthropic|groq|...
  export OPENAI_API_KEY=...                 # (or the matching key)

  # Try it:
  corvus run "write a prime sieve with pytest tests and make them pass"

  # Or run the API + open the PWA in your phone browser:
  pip install -e ".[server]"
  export CORVUS_API_TOKEN=set-a-secret
  corvus serve --host 127.0.0.1 --port 8000
  #  then browse to http://127.0.0.1:8000 and "Add to Home Screen"

EOF
