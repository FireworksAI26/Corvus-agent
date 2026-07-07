"""Web search tool with a pluggable backend.

Providers (set search.provider in config.yaml, or CORVUS_SEARCH_PROVIDER):
  - brave       Brave Search API      (BRAVE_API_KEY)
  - tavily      Tavily (LLM-oriented) (TAVILY_API_KEY)
  - serpapi     SerpAPI / Google      (SERPAPI_API_KEY)
  - duckduckgo  keyless HTML scrape (best-effort; DuckDuckGo often rate-limits
                or challenges automated requests, so results aren't guaranteed)
  - auto        (default) use whichever API key is set, else duckduckgo

API providers are reliable and return citations; the keyless backend is a
zero-setup fallback. web_search never raises - it returns a readable string.
"""
import os
import re
from html import unescape

import requests

_CONFIG = {"provider": "auto", "max_results": 5}


def configure(cfg: dict):
    if cfg:
        _CONFIG.update({k: cfg[k] for k in ("provider", "max_results") if k in cfg})


def _strip(html: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", html)).strip()


def _fmt(results: list) -> str:
    if not results:
        return "No results found."
    return "\n".join(f"{i + 1}. {r['title']}\n   {r['url']}\n   {r.get('snippet', '')}"
                     for i, r in enumerate(results))


def _brave(query: str, k: int) -> list:
    r = requests.get("https://api.search.brave.com/res/v1/web/search",
                     headers={"X-Subscription-Token": os.environ.get("BRAVE_API_KEY", ""),
                              "Accept": "application/json"},
                     params={"q": query, "count": k}, timeout=15)
    r.raise_for_status()
    web = r.json().get("web", {}).get("results", [])
    return [{"title": x.get("title", ""), "url": x.get("url", ""),
             "snippet": x.get("description", "")} for x in web[:k]]


def _tavily(query: str, k: int) -> list:
    r = requests.post("https://api.tavily.com/search",
                      json={"api_key": os.environ.get("TAVILY_API_KEY", ""),
                            "query": query, "max_results": k}, timeout=20)
    r.raise_for_status()
    return [{"title": x.get("title", ""), "url": x.get("url", ""),
             "snippet": x.get("content", "")} for x in r.json().get("results", [])[:k]]


def _serpapi(query: str, k: int) -> list:
    r = requests.get("https://serpapi.com/search",
                     params={"q": query, "api_key": os.environ.get("SERPAPI_API_KEY", ""),
                             "engine": "google", "num": k}, timeout=20)
    r.raise_for_status()
    return [{"title": x.get("title", ""), "url": x.get("link", ""),
             "snippet": x.get("snippet", "")} for x in r.json().get("organic_results", [])[:k]]


def _duckduckgo(query: str, k: int) -> list:
    """Best-effort keyless scrape. Returns [] if DuckDuckGo blocks the request."""
    for url in ("https://html.duckduckgo.com/html/", "https://lite.duckduckgo.com/lite/"):
        try:
            resp = requests.post(url, data={"q": query},
                                 headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"},
                                 timeout=15)
        except requests.RequestException:
            continue
        pairs = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                           resp.text, re.DOTALL)
        if pairs:
            snips = re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
            return [{"title": _strip(t), "url": u,
                     "snippet": _strip(snips[i]) if i < len(snips) else ""}
                    for i, (u, t) in enumerate(pairs[:k])]
    return []


_PROVIDERS = {"brave": _brave, "tavily": _tavily, "serpapi": _serpapi, "duckduckgo": _duckduckgo}


def _resolve_provider() -> str:
    pref = os.environ.get("CORVUS_SEARCH_PROVIDER") or _CONFIG.get("provider", "auto")
    if pref != "auto":
        return pref
    if os.environ.get("BRAVE_API_KEY"):
        return "brave"
    if os.environ.get("TAVILY_API_KEY"):
        return "tavily"
    if os.environ.get("SERPAPI_API_KEY"):
        return "serpapi"
    return "duckduckgo"


def web_search(query: str, max_results: int | None = None) -> str:
    """Search the web. Never raises - returns a readable result string."""
    k = max_results or _CONFIG.get("max_results", 5)
    provider = _resolve_provider()
    try:
        results = _PROVIDERS.get(provider, _duckduckgo)(query, k)
    except requests.RequestException as err:
        # An API provider failed (bad key, network) - fall back to keyless search.
        if provider != "duckduckgo":
            try:
                results = _duckduckgo(query, k)
            except requests.RequestException:
                return f"Search failed ({provider}): {err}"
        else:
            return f"Search failed: {err}"
    if not results and provider == "duckduckgo":
        return ("No results (the keyless DuckDuckGo backend was blocked or rate-limited). "
                "Set BRAVE_API_KEY, TAVILY_API_KEY, or SERPAPI_API_KEY and "
                "search.provider for reliable results.")
    return _fmt(results)
