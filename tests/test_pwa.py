"""PWA asset + serving tests."""
import json
import os

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from server import create_app  # noqa: E402
from settings import load_config  # noqa: E402

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def test_pwa_files_exist():
    for f in ("index.html", "app.js", "manifest.webmanifest", "sw.js",
              "icon-192.png", "icon-512.png"):
        assert os.path.isfile(os.path.join(WEB, f)), f


def test_manifest_is_valid_and_installable():
    with open(os.path.join(WEB, "manifest.webmanifest")) as f:
        m = json.load(f)
    assert m["name"] and m["display"] == "standalone"
    sizes = {i["sizes"] for i in m["icons"]}
    assert {"192x192", "512x512"}.issubset(sizes)  # installability minimum


def test_service_worker_skips_api():
    with open(os.path.join(WEB, "sw.js")) as f:
        sw = f.read()
    assert "/api" in sw and "caches.open" in sw  # never caches API, caches shell


def test_server_serves_pwa_index():
    client = TestClient(create_app(config=load_config(), api_token=None))
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "Corvus" in r.text
