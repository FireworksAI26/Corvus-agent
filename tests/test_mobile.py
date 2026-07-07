"""Validate the Expo mobile scaffold (config validity + expected files)."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOBILE = os.path.join(ROOT, "mobile")


def test_mobile_files_exist():
    for f in ("package.json", "app.json", "App.js", "src/api.js", "README.md", ".gitignore"):
        assert os.path.isfile(os.path.join(MOBILE, f)), f


def test_package_json_valid_and_has_expo():
    with open(os.path.join(MOBILE, "package.json")) as f:
        pkg = json.load(f)
    assert "expo" in pkg["dependencies"]
    assert "@react-native-async-storage/async-storage" in pkg["dependencies"]
    assert pkg["scripts"]["ios"] and pkg["scripts"]["android"]


def test_app_json_valid_and_targets_both_platforms():
    with open(os.path.join(MOBILE, "app.json")) as f:
        cfg = json.load(f)["expo"]
    assert cfg["ios"]["bundleIdentifier"] and cfg["android"]["package"]


def test_api_client_points_at_corvus_endpoints():
    with open(os.path.join(MOBILE, "src", "api.js")) as f:
        src = f.read()
    for path in ("/health", "/api/task", "/api/lessons", "/api/checkpoint"):
        assert path in src
