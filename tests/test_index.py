"""Repo indexing + code retrieval."""
import index


def _make_repo(tmp_path):
    (tmp_path / "auth.py").write_text(
        "def login(user, password):\n    # verify credentials against the database\n"
        "    return check_password(user, password)\n")
    (tmp_path / "math_utils.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef factorial(n):\n"
        "    return 1 if n <= 1 else n * factorial(n - 1)\n")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "cache.py").write_text("class LRUCache:\n    def __init__(self, capacity):\n"
                                  "        self.capacity = capacity\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("login password database")  # must be skipped


def test_index_skips_vendor_dirs(tmp_path):
    _make_repo(tmp_path)
    chunks = index.index_repo(str(tmp_path))
    paths = {c["path"] for c in chunks}
    assert "auth.py" in paths and "pkg/cache.py" in paths
    assert not any("node_modules" in p for p in paths)


def test_search_code_finds_relevant_file(tmp_path):
    _make_repo(tmp_path)
    out = index.search_code("user login password authentication", str(tmp_path), k=2)
    assert "auth.py" in out
    assert out.index("auth.py") < (out.index("math_utils.py") if "math_utils.py" in out else 10**9)


def test_search_code_empty_repo(tmp_path):
    assert "No indexable" in index.search_code("anything", str(tmp_path))
