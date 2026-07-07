/* Corvus PWA client - talks to the `corvus serve` HTTP API. Vanilla JS, no deps. */
const $ = (id) => document.getElementById(id);
const store = {
  get base() { return localStorage.getItem("corvus.base") || location.origin; },
  set base(v) { localStorage.setItem("corvus.base", v); },
  get token() { return localStorage.getItem("corvus.token") || ""; },
  set token(v) { localStorage.setItem("corvus.token", v); },
};
let activeTab = "lessons";

function headers() {
  const h = { "Content-Type": "application/json" };
  if (store.token) h["Authorization"] = "Bearer " + store.token;
  return h;
}
async function api(path, opts = {}) {
  const res = await fetch(store.base.replace(/\/$/, "") + path, { headers: headers(), ...opts });
  if (!res.ok) throw new Error("HTTP " + res.status + (res.status === 401 ? " (check token)" : ""));
  return res.json();
}
function setStatus(ok, text) {
  $("dot").className = "dot " + (ok ? "on" : "off");
  $("statusText").textContent = text;
}

async function connect() {
  try {
    const h = await api("/health");
    setStatus(true, `${h.provider} · ${h.model}`);
    loadTab(activeTab);
    return true;
  } catch (e) {
    setStatus(false, "not connected");
    return false;
  }
}

function showResult(r) {
  const badge = r.success
    ? '<span class="badge ok">verified ✓</span>'
    : '<span class="badge bad">unverified</span>';
  const lessons = (r.lessons || []).map((l) => "• " + l).join("\n");
  $("result").className = "out";
  $("result").innerHTML =
    `${badge} <span class="muted small">${r.steps} steps</span>\n\n` +
    `${escapeHtml(r.result)}` +
    (lessons ? `\n\n<span class="muted small">Lessons banked:</span>\n${escapeHtml(lessons)}` : "");
  if (activeTab === "lessons") loadTab("lessons");
}

function addTrace(ev) {
  const args = Object.entries(ev.args || {}).map(([k, v]) => `${k}=${String(v).slice(0, 40)}`).join(", ");
  const li = document.createElement("li");
  li.innerHTML = `<b>→ ${escapeHtml(ev.tool || "?")}</b>(${escapeHtml(args)})` +
    (ev.observation ? `<br><span class="muted small">${escapeHtml(ev.observation)}</span>` : "");
  $("trace").appendChild(li);
}

function runTask() {
  const task = $("task").value.trim();
  if (!task) return;
  $("run").disabled = true;
  $("runHint").textContent = "working…";
  $("trace").innerHTML = "";
  $("result").className = "out muted";
  $("result").textContent = "Running… watch the steps stream in below.";
  const done = () => { $("run").disabled = false; $("runHint").textContent = ""; };

  // Stream live via SSE (EventSource is GET-only, so the token rides as a query param).
  const url = store.base.replace(/\/$/, "") + "/api/task/stream" +
    "?task=" + encodeURIComponent(task) +
    (store.token ? "&token=" + encodeURIComponent(store.token) : "");
  try {
    const es = new EventSource(url);
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data);
      if (ev.type === "step") addTrace(ev);
      else if (ev.type === "done") { showResult(ev); es.close(); done(); }
      else if (ev.type === "error") { $("result").textContent = "Error: " + ev.message; es.close(); done(); }
    };
    es.onerror = () => { es.close(); done(); if (!$("trace").children.length) fallbackRun(task); };
  } catch (e) {
    fallbackRun(task);
  }
}

async function fallbackRun(task) {
  // Non-streaming fallback if EventSource is unavailable.
  try {
    showResult(await api("/api/task", { method: "POST", body: JSON.stringify({ task }) }));
  } catch (e) {
    $("result").className = "out"; $("result").textContent = "Error: " + e.message;
  } finally {
    $("run").disabled = false; $("runHint").textContent = "";
  }
}

async function loadTab(tab) {
  activeTab = tab;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.t === tab));
  const list = $("list");
  list.innerHTML = '<li class="muted">Loading…</li>';
  try {
    let items = [];
    if (tab === "lessons") items = (await api("/api/lessons")).lessons;
    else if (tab === "memories") items = (await api("/api/memories")).memories;
    else if (tab === "skills") {
      const s = await api("/api/skills");
      items = [`${s.count} skills in the library`, ...(s.named || [])];
    } else if (tab === "checkpoints") items = (await api("/api/checkpoints")).checkpoints;
    list.innerHTML = items.length
      ? items.map((x) => `<li>${escapeHtml(x)}</li>`).join("")
      : '<li class="muted">Nothing here yet.</li>';
  } catch (e) {
    list.innerHTML = `<li class="muted">Could not load: ${escapeHtml(e.message)}</li>`;
  }
}

async function snapshot() {
  const name = prompt("Checkpoint name (snapshot the agent's learned state):");
  if (!name) return;
  try { await api("/api/checkpoint", { method: "POST", body: JSON.stringify({ name }) }); loadTab("checkpoints"); }
  catch (e) { alert("Save failed: " + e.message); }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

// Wire up
$("apiBase").value = store.base;
$("apiToken").value = store.token;
$("saveConn").onclick = () => { store.base = $("apiBase").value.trim(); store.token = $("apiToken").value.trim(); $("settings").open = false; connect(); };
$("testConn").onclick = connect;
$("run").onclick = runTask;
$("refresh").onclick = () => loadTab(activeTab);
$("snapshot").onclick = snapshot;
$("tabs").addEventListener("click", (e) => { if (e.target.dataset.t) loadTab(e.target.dataset.t); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
connect();
