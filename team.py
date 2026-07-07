"""Team layer for the API server: role-based access + an audit log.

Roles: owner (the main api_token), member (read + write), viewer (read only).
Extra tokens and their roles come from config `team.tokens` ({token: role}).
Every write action is appended to an audit log. SSO isn't code here - deploy the
server behind your IdP/proxy and map identities to tokens; the roles below then
gate what each caller can do.
"""
import json
import os
import time

WRITE_ROLES = ("owner", "member")


def role_for(token: str, config: dict, owner_token: str = None) -> str | None:
    if not token:
        return None
    if owner_token and token == owner_token:
        return "owner"
    return config.get("team", {}).get("tokens", {}).get(token)


def can_write(role: str) -> bool:
    return role in WRITE_ROLES


def _audit_path(config: dict) -> str:
    return os.path.join(config.get("memory", {}).get("path", ".memory"), "audit.jsonl")


def audit(config: dict, role: str, action: str, detail: str = "") -> dict:
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "role": role, "action": action, "detail": str(detail)[:200]}
    try:
        path = _audit_path(config)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass
    return rec


def read_audit(config: dict, limit: int = 50) -> list:
    path = _audit_path(config)
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows[-limit:]
