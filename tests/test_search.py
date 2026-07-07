"""Tests for the pluggable web_search backend (no real network calls)."""
import agent.search as search


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_provider_resolution_prefers_api_keys(monkeypatch):
    monkeypatch.delenv("CORVUS_SEARCH_PROVIDER", raising=False)
    for k in ("BRAVE_API_KEY", "TAVILY_API_KEY", "SERPAPI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    search.configure({"provider": "auto"})
    assert search._resolve_provider() == "duckduckgo"      # nothing set
    monkeypatch.setenv("TAVILY_API_KEY", "t")
    assert search._resolve_provider() == "tavily"
    monkeypatch.setenv("BRAVE_API_KEY", "b")
    assert search._resolve_provider() == "brave"           # brave wins the priority


def test_brave_backend_parses_results(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "b")
    search.configure({"provider": "brave"})
    payload = {"web": {"results": [
        {"title": "Asyncio docs", "url": "https://x/y", "description": "gather() runs..."}]}}
    monkeypatch.setattr(search.requests, "get", lambda *a, **k: _Resp(payload))
    out = search.web_search("asyncio gather")
    assert "Asyncio docs" in out and "https://x/y" in out and "gather()" in out


def test_tavily_backend_parses_results(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "t")
    search.configure({"provider": "tavily"})
    payload = {"results": [{"title": "T", "url": "https://t/1", "content": "snippet here"}]}
    monkeypatch.setattr(search.requests, "post", lambda *a, **k: _Resp(payload))
    out = search.web_search("q")
    assert "T" in out and "snippet here" in out


def test_api_failure_is_graceful(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "b")
    search.configure({"provider": "brave"})

    def boom(*a, **k):
        raise search.requests.RequestException("500")

    monkeypatch.setattr(search.requests, "get", boom)
    monkeypatch.setattr(search.requests, "post", boom)   # ddg fallback also fails
    out = search.web_search("q")
    assert out.startswith("Search failed") or "No results" in out   # never raises


def test_duckduckgo_blocked_returns_hint(monkeypatch):
    monkeypatch.delenv("CORVUS_SEARCH_PROVIDER", raising=False)
    for k in ("BRAVE_API_KEY", "TAVILY_API_KEY", "SERPAPI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    search.configure({"provider": "duckduckgo"})
    monkeypatch.setattr(search.requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(search.requests.RequestException("blocked")))
    out = search.web_search("q")
    assert "No results" in out and "API_KEY" in out    # points user to a real provider
