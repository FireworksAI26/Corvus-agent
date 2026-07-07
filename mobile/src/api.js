// Corvus API client - talks to the `corvus serve` HTTP API.
import AsyncStorage from "@react-native-async-storage/async-storage";

const KEYS = { base: "corvus.base", token: "corvus.token" };

export async function getConfig() {
  const [base, token] = await Promise.all([
    AsyncStorage.getItem(KEYS.base),
    AsyncStorage.getItem(KEYS.token),
  ]);
  return { base: base || "http://10.0.2.2:8000", token: token || "" };
}

export async function setConfig({ base, token }) {
  await AsyncStorage.multiSet([
    [KEYS.base, base || ""],
    [KEYS.token, token || ""],
  ]);
}

async function request(path, options = {}) {
  const { base, token } = await getConfig();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = "Bearer " + token;
  const res = await fetch(base.replace(/\/$/, "") + path, { ...options, headers });
  if (!res.ok) throw new Error("HTTP " + res.status + (res.status === 401 ? " (check token)" : ""));
  return res.json();
}

export const api = {
  health: () => request("/health"),
  lessons: () => request("/api/lessons"),
  memories: () => request("/api/memories"),
  skills: () => request("/api/skills"),
  checkpoints: () => request("/api/checkpoints"),
  runTask: (task) => request("/api/task", { method: "POST", body: JSON.stringify({ task }) }),
  saveCheckpoint: (name) =>
    request("/api/checkpoint", { method: "POST", body: JSON.stringify({ name }) }),
};

// Live-stream a task's steps via SSE. Uses XMLHttpRequest incremental parsing,
// which works in React Native (no EventSource) and in browsers. Calls
// onEvent({type:'step'|'done'|'error', ...}) as events arrive.
export async function streamTask(task, onEvent) {
  const { base, token } = await getConfig();
  const url = base.replace(/\/$/, "") + "/api/task/stream?task=" +
    encodeURIComponent(task) + (token ? "&token=" + encodeURIComponent(token) : "");
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let seen = 0;
    let buffer = "";
    xhr.open("GET", url);
    xhr.onreadystatechange = () => {
      if (xhr.readyState >= 3) {
        buffer += xhr.responseText.slice(seen);
        seen = xhr.responseText.length;
        let i;
        while ((i = buffer.indexOf("\n\n")) >= 0) {
          const line = buffer.slice(0, i).trim();
          buffer = buffer.slice(i + 2);
          if (line.startsWith("data:")) {
            try { onEvent(JSON.parse(line.slice(5).trim())); } catch (e) { /* ignore */ }
          }
        }
      }
      if (xhr.readyState === 4) resolve();
    };
    xhr.onerror = () => reject(new Error("stream failed"));
    xhr.send();
  });
}
