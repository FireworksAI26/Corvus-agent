"""Verify local checkpoint save/load of an agent's LEARNED STATE.

Runs each phase in a SEPARATE process (like the real `corvus checkpoint ...`
commands) so it faithfully reflects how a user snapshots an agent they like
and starts fresh conversations from it. Uses the real chromadb stores.
"""
import os
import subprocess
import sys
import tempfile

ROOT = tempfile.mkdtemp(prefix="corvus_ckpt_")
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = sys.executable


def run(code):
    r = subprocess.run([PY, "-c", code], cwd=ROOT,
                       env={**os.environ, "PYTHONPATH": REPO},
                       capture_output=True, text=True)
    out = "\n".join(ln for ln in r.stdout.splitlines()
                    if "MiniLM" not in ln and "%|" not in ln)
    if r.returncode != 0:
        print(out)
        print(r.stderr[-1500:])
        raise SystemExit("phase failed")
    return out.strip()


print("PHASE 1  train an agent: bank a lesson + a built skill, then snapshot it")
print(run(r"""
from memory.lessons import LessonStore
from memory.skills import SkillStore
LessonStore('.memory').add('Prefer pathlib over os.path for new code.')
SkillStore('.memory').add_built('slugify','make a url slug','def slugify(s): return s.lower().replace(" ","-")')
import checkpoints
checkpoints.save('my-favorite-agent')
print('  saved checkpoint; lessons=1 skills=1')
"""))

print("\nPHASE 2  keep working (memory drifts), then LOAD the snapshot back")
print(run(r"""
from memory.lessons import LessonStore
LessonStore('.memory').add('A throwaway lesson learned after the snapshot.')
before = LessonStore('.memory').col.count()
import checkpoints
checkpoints.list_checkpoints()
checkpoints.load('my-favorite-agent')
print(f'  lessons before load = {before} (snapshot had 1)')
"""))

print("\nPHASE 3  fresh process reads restored .memory -> exact saved state")
print(run(r"""
from memory.lessons import LessonStore
from memory.skills import SkillStore
lessons = LessonStore('.memory').all()
skills = SkillStore('.memory').list_named()
print('  restored lessons :', lessons)
print('  restored skills  :', skills)
assert len(lessons) == 1 and 'pathlib' in lessons[0], lessons
assert any('slugify' in s for s in skills), skills
import os
assert os.path.isdir('.memory.backup'), 'post-snapshot state should be backed up, not lost'
print('  backup of drifted state kept at .memory.backup :', os.path.isdir('.memory.backup'))
print('  CHECKPOINTS OK')
"""))

import shutil  # noqa: E402
shutil.rmtree(ROOT, ignore_errors=True)
