"""Verify (a) the opt-in 'computer' tool safety gates and that it can actually
run a command when granted, and (b) the skills system: build, export, import,
dedup, similarity retrieval, and importing the shipped community starter pack.
"""
import builtins
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.chdir(tempfile.mkdtemp(prefix="corvus_feat_"))

from agent.tools import ToolContext, build_tools  # noqa: E402
from memory.skills import SkillStore  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def banner(t):
    print(f"\n{'=' * 62}\n{t}\n{'=' * 62}")


# ---------------- Computer control ----------------
banner("COMPUTER CONTROL  (run tasks on the user's PC only if allowed)")

ctx = ToolContext(computer_enabled=False, computer_confirm=True)
computer = build_tools(ctx)["computer"]

# 1. OFF by default
r = computer("echo should-not-run")
print("  disabled by default        :", "disabled" in r.lower())
assert "disabled" in r.lower()

# 2. Granted + user confirms 'y' -> command actually runs
ctx.computer["enabled"], ctx.computer["confirm"] = True, True
builtins.input = lambda *_: "y"
r = computer("echo hello-from-your-pc")
print("  granted + 'y' runs command :", "hello-from-your-pc" in r and "exit_code=0" in r)
assert "hello-from-your-pc" in r and "exit_code=0" in r

# 3. Granted but user answers 'n' -> denied
builtins.input = lambda *_: "n"
r = computer("echo blocked")
print("  user 'n' blocks command    :", "denied" in r.lower())
assert "denied" in r.lower()

# 4. Unattended (no stdin) -> EOFError failsafe blocks the command
def _raise_eof(*_):
    raise EOFError
builtins.input = _raise_eof
r = computer("echo unattended")
print("  EOF failsafe blocks        :", "unavailable" in r.lower())
assert "unavailable" in r.lower()

# 5. Confirmation disabled -> runs without prompting
ctx.computer["confirm"] = False
r = computer("echo no-prompt")
print("  confirm=false runs direct  :", "no-prompt" in r)
assert "no-prompt" in r
ctx.computer["enabled"], ctx.computer["confirm"] = False, True  # reset

# ---------------- Skills system ----------------
banner("SKILLS  build / export / import / dedup / retrieve / starter pack")

store = SkillStore(".memory")
store.add_built("http_get", "GET json from a url", "import requests\ndef g(u): return requests.get(u).json()")
store.add("Write a CSV mean function", "stats.py", "def column_mean(t,c): ...")
print("  built + harvested add      :", store.count() == 2)
print("  list_named (built only)    :", store.list_named())
assert store.count() == 2 and any("http_get" in s for s in store.list_named())

# export -> import into a brand-new store round-trips
exported = store.export_named()
with open("exp.json", "w") as f:
    json.dump(exported, f)
store2 = SkillStore(".memory2")
added = store2.import_entries(json.load(open("exp.json")))
readded = store2.import_entries(json.load(open("exp.json")))  # dedup: should add 0
print(f"  export/import round-trip   : added={added} re-import={readded} (dedup works: {readded == 0})")
assert added == 1 and readded == 0

# import the shipped community starter pack
starter = json.load(open(os.path.join(REPO, "community", "skills-starter.json")))
n = store2.import_entries(starter)
print(f"  community starter imported : {n} skills ({[s['name'] for s in starter]})")
assert n == 2

# similarity retrieval returns injectable skill docs
hits = store2.similar("fetch json from an http endpoint", k=2)
print("  similarity retrieval       :", bool(hits) and "http" in " ".join(hits).lower())
assert hits

banner("ALL FEATURE CHECKS PASSED")
