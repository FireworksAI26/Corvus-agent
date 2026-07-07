"""Lightweight observability: append one JSON line per task run, and summarize.

Records provider/model, step count, verified success, wall-clock seconds, and a
rough token estimate to <memory.path>/runs.jsonl. `corvus stats` aggregates it.
Best-effort - telemetry never breaks a run.
"""
import json
import os
import time


def _log_path(config: dict) -> str:
    return os.path.join(config.get("memory", {}).get("path", ".memory"), "runs.jsonl")


def estimate_tokens(*texts) -> int:
    return sum(len(t or "") for t in texts) // 4  # ~4 chars/token heuristic


def log_run(config: dict, task: str, outcome: dict, success: bool, seconds: float) -> dict:
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "provider": config.get("provider"), "model": config.get("model"),
           "task": str(task)[:200], "steps": outcome.get("steps"),
           "success": bool(success), "seconds": round(seconds, 2),
           "tokens_est": estimate_tokens(task, str(outcome.get("result", "")))}
    try:
        path = _log_path(config)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass
    return rec


def _read(config: dict) -> list:
    path = _log_path(config)
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def stats(config: dict) -> dict:
    rows = _read(config)
    n = len(rows)
    if not n:
        return {"runs": 0}
    by_model = {}
    for r in rows:
        m = f"{r.get('provider')}/{r.get('model')}"
        b = by_model.setdefault(m, {"runs": 0, "passed": 0})
        b["runs"] += 1
        b["passed"] += 1 if r.get("success") else 0
    return {"runs": n,
            "pass_rate": sum(r.get("success") for r in rows) / n,
            "avg_steps": sum(r.get("steps") or 0 for r in rows) / n,
            "avg_seconds": sum(r.get("seconds") or 0 for r in rows) / n,
            "tokens_est": sum(r.get("tokens_est") or 0 for r in rows),
            "by_model": by_model}
