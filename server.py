"""Corvus API server - the backend the mobile apps (PWA + native) talk to.

`corvus serve` runs the agent on your computer/server and exposes a small HTTP
API plus (if built) the PWA. Endpoints under /api require a bearer token when
one is configured (server.api_token in config.yaml or the CORVUS_API_TOKEN env
var); /health is always open.

FastAPI + uvicorn are an optional extra:  pip install -e ".[server]"
"""
import os

from settings import load_config


def create_app(config: dict | None = None, agent=None, api_token: str | None = None):
    from fastapi import Depends, FastAPI, Header, HTTPException
    from fastapi.middleware.cors import CORSMiddleware

    config = config or load_config()
    cors = config.get("server", {}).get("cors_origins", ["*"])
    state = {"agent": agent}

    app = FastAPI(title="Corvus API", version="1.0")
    app.add_middleware(CORSMiddleware, allow_origins=cors, allow_methods=["*"],
                       allow_headers=["*"])

    def get_agent():
        if state["agent"] is None:
            from agent.core import Agent
            state["agent"] = Agent(config)
        return state["agent"]

    import team

    def _role(authorization: str, token_q: str = "") -> str:
        # No auth configured at all -> open (dev/localhost).
        if not api_token and not config.get("team", {}).get("tokens"):
            return "owner"
        supplied = None
        if authorization and authorization.startswith("Bearer "):
            supplied = authorization[7:]
        elif token_q:
            supplied = token_q
        return team.role_for(supplied, config, owner_token=api_token)

    def require_read(authorization: str = Header(None)):
        role = _role(authorization)
        if role is None:
            raise HTTPException(status_code=401, detail="invalid or missing API token")
        return role

    def require_write(authorization: str = Header(None)):
        role = _role(authorization)
        if role is None:
            raise HTTPException(status_code=401, detail="invalid or missing API token")
        if not team.can_write(role):
            raise HTTPException(status_code=403, detail="this token is read-only (viewer)")
        return role

    @app.get("/health")
    def health():
        from memory._client import active_backend
        return {"status": "ok", "provider": config.get("provider"),
                "model": config.get("model"), "memory_backend": active_backend()}

    @app.get("/api/lessons")
    def lessons(_=Depends(require_read)):
        return {"lessons": get_agent().lessons.all()}

    @app.get("/api/memories")
    def memories(_=Depends(require_read)):
        return {"memories": get_agent().notes.all()}

    @app.get("/api/skills")
    def skills(_=Depends(require_read)):
        a = get_agent()
        return {"count": a.skills.count(), "named": a.skills.list_named()}

    @app.get("/api/skills/export")
    def export_skills(_=Depends(require_read)):
        return {"skills": get_agent().skills.export_named()}

    @app.post("/api/skills/import")
    def import_skills(body: dict, role=Depends(require_write)):
        added = get_agent().skills.import_entries((body or {}).get("skills", []))
        team.audit(config, role, "skills.import", f"added={added}")
        return {"added": added}

    @app.get("/api/checkpoints")
    def list_checkpoints(_=Depends(require_read)):
        import checkpoints
        return {"checkpoints": checkpoints.list_checkpoints()}

    @app.get("/api/audit")
    def audit_log(_=Depends(require_read)):
        return {"audit": team.read_audit(config)}

    @app.post("/api/task")
    def run_task(body: dict, role=Depends(require_write)):
        task = (body or {}).get("task", "").strip()
        if not task:
            raise HTTPException(status_code=400, detail="task is required")
        from agent.session import solve_and_learn
        team.audit(config, role, "task", task[:80])
        outcome, success, reflection = solve_and_learn(get_agent(), config, task)
        return {"task": task, "result": outcome["result"], "success": success,
                "steps": outcome["steps"], "lessons": reflection.get("lessons", [])}

    @app.get("/api/task/stream")
    def run_task_stream(task: str = "", token: str = "", authorization: str = Header(None)):
        # EventSource can't set headers, so accept the token as a query param too.
        role = _role(authorization, token)
        if role is None:
            raise HTTPException(status_code=401, detail="invalid or missing API token")
        if not team.can_write(role):
            raise HTTPException(status_code=403, detail="this token is read-only (viewer)")
        if not task.strip():
            raise HTTPException(status_code=400, detail="task is required")
        team.audit(config, role, "task.stream", task.strip()[:80])

        import json as _json
        import queue
        import threading
        from fastapi.responses import StreamingResponse
        from agent.session import solve_and_learn

        events: queue.Queue = queue.Queue()

        def on_step(step, observation):
            if "final_answer" in step:
                return
            events.put({"type": "step", "tool": step.get("tool"),
                        "args": step.get("args", {}),
                        "observation": (observation or "").splitlines()[0][:160]})

        def worker():
            try:
                outcome, success, refl = solve_and_learn(get_agent(), config, task.strip(),
                                                         on_step=on_step)
                events.put({"type": "done", "result": outcome["result"], "success": success,
                            "steps": outcome["steps"], "lessons": refl.get("lessons", [])})
            except Exception as err:  # surface failures to the client
                events.put({"type": "error", "message": str(err)})
            finally:
                events.put(None)

        threading.Thread(target=worker, daemon=True).start()

        def event_stream():
            while True:
                item = events.get()
                if item is None:
                    break
                yield f"data: {_json.dumps(item)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/api/checkpoint")
    def save_checkpoint(body: dict, role=Depends(require_write)):
        import checkpoints
        name = (body or {}).get("name", "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        checkpoints.save(name, config["memory"]["path"])
        team.audit(config, role, "checkpoint.save", name)
        return {"saved": name}

    # Serve the PWA if its assets are found. Check next to this module (source
    # checkout / editable install) and the current working dir (self-hosters run
    # `corvus serve` from the project dir even after a non-editable pip install).
    for candidate in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "web"),
                      os.path.join(os.getcwd(), "web")):
        if os.path.isdir(candidate):
            from fastapi.staticfiles import StaticFiles
            app.mount("/", StaticFiles(directory=candidate, html=True), name="web")
            break

    return app


def serve(host: str | None = None, port: int | None = None, config: dict | None = None):
    import uvicorn
    config = config or load_config()
    srv = config.get("server", {})
    host = host or srv.get("host", "127.0.0.1")
    port = port or srv.get("port", 8000)
    token = srv.get("api_token") or os.environ.get("CORVUS_API_TOKEN") or ""
    if not token:
        print("WARNING: no API token set (server.api_token / CORVUS_API_TOKEN). "
              "Bind to localhost only, or set a token before exposing this.")
    app = create_app(config=config, api_token=token or None)
    print(f"Corvus API -> http://{host}:{port}   (token {'set' if token else 'NOT set'})")
    uvicorn.run(app, host=host, port=port)
