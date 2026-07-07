"""Repo-scale code retrieval: index a project's source files and find the
chunks most relevant to a query. Pure-Python (reuses the lite TF-IDF ranker),
so it works everywhere including Termux. Powers the agent's `search_code` tool
and context injection in real-repo mode.
"""
import os

from memory.lite import _rank

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".pytest_cache",
             ".ruff_cache", "dist", "build", ".expo", ".memory", ".memory.backup",
             ".checkpoints"}
CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb",
            ".c", ".cpp", ".h", ".hpp", ".cs", ".php", ".swift", ".kt", ".scala",
            ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".css", ".html", ".sh"}
MAX_BYTES = 200_000
CHUNK_LINES = 40


def _iter_chunks(root: str):
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in files:
            if os.path.splitext(name)[1].lower() not in CODE_EXT:
                continue
            full = os.path.join(dirpath, name)
            try:
                if os.path.getsize(full) > MAX_BYTES:
                    continue
                with open(full, encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except OSError:
                continue
            rel = os.path.relpath(full, root)
            for start in range(0, len(lines) or 1, CHUNK_LINES):
                block = "".join(lines[start:start + CHUNK_LINES])
                if block.strip():
                    yield {"path": rel, "start": start + 1,
                           "end": min(start + CHUNK_LINES, len(lines)),
                           "document": f"{rel}\n{block}"}


def index_repo(root: str) -> list:
    return list(_iter_chunks(os.path.abspath(root)))


def search_code(query: str, root: str, k: int = 5) -> str:
    chunks = index_repo(root)
    if not chunks:
        return "No indexable source files found."
    ranked = _rank(query, chunks)[:k]
    out = []
    for dist, ch in ranked:
        body = ch["document"].split("\n", 1)[1] if "\n" in ch["document"] else ""
        snippet = "\n".join(body.splitlines()[:8])
        out.append(f"{ch['path']}:{ch['start']}-{ch['end']}  (score {1 - dist:.2f})\n{snippet}")
    return "\n\n".join(out)
