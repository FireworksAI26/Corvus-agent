// Corvus native app (iOS + Android) - a thin client over the corvus serve API.
import { useEffect, useState } from "react";
import {
  ActivityIndicator, SafeAreaView, ScrollView, StyleSheet, Text,
  TextInput, TouchableOpacity, View,
} from "react-native";
import { StatusBar } from "expo-status-bar";
import { api, getConfig, setConfig, streamTask } from "./src/api";

const C = {
  bg: "#0e0e14", panel: "#171722", panel2: "#1f1f2e", line: "#2a2a3c",
  ink: "#e9e9f2", dim: "#9a9ab0", accent: "#7c6cff", ok: "#2ecc71", bad: "#ff6b6b",
};
const TABS = ["lessons", "memories", "skills", "checkpoints"];

export default function App() {
  const [base, setBase] = useState("");
  const [token, setToken] = useState("");
  const [status, setStatus] = useState({ ok: false, text: "not connected" });
  const [task, setTask] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [trace, setTrace] = useState([]);
  const [tab, setTab] = useState("lessons");
  const [items, setItems] = useState([]);

  useEffect(() => {
    getConfig().then((c) => { setBase(c.base); setToken(c.token); connect(); });
  }, []);

  async function connect() {
    try {
      const h = await api.health();
      setStatus({ ok: true, text: `${h.provider} · ${h.model}` });
      loadTab(tab);
    } catch {
      setStatus({ ok: false, text: "not connected" });
    }
  }

  async function saveAndConnect() {
    await setConfig({ base, token });
    connect();
  }

  async function runTask() {
    if (!task.trim()) return;
    setRunning(true); setResult(null); setTrace([]);
    try {
      await streamTask(task.trim(), (ev) => {
        if (ev.type === "step") {
          const args = Object.entries(ev.args || {}).map(([k, v]) => `${k}=${String(v).slice(0, 30)}`).join(", ");
          setTrace((t) => [...t, `→ ${ev.tool}(${args})`]);
        } else if (ev.type === "done") {
          setResult(ev);
          if (tab === "lessons") loadTab("lessons");
        } else if (ev.type === "error") {
          setResult({ error: ev.message });
        }
      });
    } catch (e) {
      // fall back to the non-streaming endpoint
      try { setResult(await api.runTask(task.trim())); }
      catch (e2) { setResult({ error: e2.message }); }
    } finally {
      setRunning(false);
    }
  }

  async function loadTab(t) {
    setTab(t); setItems([]);
    try {
      if (t === "lessons") setItems((await api.lessons()).lessons);
      else if (t === "memories") setItems((await api.memories()).memories);
      else if (t === "skills") {
        const s = await api.skills();
        setItems([`${s.count} skills in the library`, ...(s.named || [])]);
      } else if (t === "checkpoints") setItems((await api.checkpoints()).checkpoints);
    } catch (e) {
      setItems([`Could not load: ${e.message}`]);
    }
  }

  return (
    <SafeAreaView style={s.root}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={s.scroll}>
        <View style={s.header}>
          <View style={s.logo} />
          <View style={{ flex: 1 }}>
            <Text style={s.brand}>Corvus</Text>
            <Text style={s.sub}>self-improving coding agent</Text>
          </View>
          <View style={[s.dot, { backgroundColor: status.ok ? C.ok : C.bad }]} />
        </View>
        <Text style={s.status}>{status.text}</Text>

        <View style={s.card}>
          <Text style={s.h2}>CONNECTION</Text>
          <Text style={s.label}>API base URL</Text>
          <TextInput style={s.input} value={base} onChangeText={setBase}
            autoCapitalize="none" autoCorrect={false} placeholder="http://10.0.2.2:8000"
            placeholderTextColor={C.dim} />
          <Text style={s.label}>API token</Text>
          <TextInput style={s.input} value={token} onChangeText={setToken}
            autoCapitalize="none" secureTextEntry placeholder="CORVUS_API_TOKEN"
            placeholderTextColor={C.dim} />
          <TouchableOpacity style={s.btn} onPress={saveAndConnect}>
            <Text style={s.btnText}>Save & connect</Text>
          </TouchableOpacity>
        </View>

        <View style={s.card}>
          <Text style={s.h2}>GIVE CORVUS A TASK</Text>
          <TextInput style={[s.input, { minHeight: 84 }]} value={task} onChangeText={setTask}
            multiline placeholder="Write a prime sieve with pytest tests and make them pass"
            placeholderTextColor={C.dim} />
          <TouchableOpacity style={[s.btn, running && { opacity: 0.5 }]} onPress={runTask} disabled={running}>
            {running ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>Run task</Text>}
          </TouchableOpacity>
          {trace.map((line, i) => <Text key={i} style={s.traceLine}>{line}</Text>)}
          {result && (
            <View style={s.out}>
              {result.error
                ? <Text style={s.err}>Error: {result.error}</Text>
                : <>
                    <Text style={{ color: result.success ? C.ok : C.bad, fontWeight: "700" }}>
                      {result.success ? "verified ✓" : "unverified"}  ·  {result.steps} steps
                    </Text>
                    <Text style={s.outText}>{result.result}</Text>
                    {(result.lessons || []).map((l, i) => (
                      <Text key={i} style={s.lesson}>• {l}</Text>
                    ))}
                  </>}
            </View>
          )}
        </View>

        <View style={s.card}>
          <View style={s.tabs}>
            {TABS.map((t) => (
              <TouchableOpacity key={t} onPress={() => loadTab(t)}
                style={[s.tab, tab === t && s.tabActive]}>
                <Text style={[s.tabText, tab === t && { color: "#fff" }]}>{t}</Text>
              </TouchableOpacity>
            ))}
          </View>
          {items.length === 0
            ? <Text style={s.dim}>Nothing here yet.</Text>
            : items.map((x, i) => <Text key={i} style={s.item}>{x}</Text>)}
        </View>
        <Text style={s.footer}>Corvus runs on your computer via `corvus serve`. This app is a client.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  scroll: { padding: 16, paddingBottom: 40 },
  header: { flexDirection: "row", alignItems: "center", gap: 12, marginTop: 8 },
  logo: { width: 34, height: 34, borderRadius: 17, backgroundColor: C.accent },
  brand: { color: C.ink, fontSize: 20, fontWeight: "700" },
  sub: { color: C.dim, fontSize: 12 },
  dot: { width: 11, height: 11, borderRadius: 6 },
  status: { color: C.dim, fontSize: 12, marginTop: 4, marginBottom: 12 },
  card: { backgroundColor: C.panel, borderColor: C.line, borderWidth: 1, borderRadius: 16, padding: 16, marginBottom: 16 },
  h2: { color: C.dim, fontSize: 12, letterSpacing: 1.5, marginBottom: 10, fontWeight: "600" },
  label: { color: C.dim, fontSize: 12, marginBottom: 5, marginTop: 6 },
  input: { backgroundColor: C.panel2, borderColor: C.line, borderWidth: 1, borderRadius: 12, color: C.ink, padding: 12 },
  btn: { backgroundColor: C.accent, borderRadius: 12, padding: 14, alignItems: "center", marginTop: 12 },
  btnText: { color: "#fff", fontWeight: "700" },
  out: { backgroundColor: C.panel2, borderColor: C.line, borderWidth: 1, borderRadius: 12, padding: 14, marginTop: 12 },
  outText: { color: C.ink, marginTop: 8 },
  lesson: { color: C.dim, marginTop: 6, fontSize: 13 },
  traceLine: { color: C.accent, fontSize: 12, marginTop: 8, fontFamily: "monospace" },
  err: { color: C.bad },
  tabs: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginBottom: 12 },
  tab: { paddingVertical: 8, paddingHorizontal: 13, borderRadius: 999, backgroundColor: C.panel2, borderColor: C.line, borderWidth: 1 },
  tabActive: { borderColor: C.accent, backgroundColor: "rgba(124,108,255,0.16)" },
  tabText: { color: C.dim, fontSize: 13 },
  item: { color: C.ink, backgroundColor: C.panel2, borderColor: C.line, borderWidth: 1, borderRadius: 10, padding: 10, marginBottom: 8, fontSize: 13 },
  dim: { color: C.dim },
  footer: { color: C.dim, fontSize: 12, textAlign: "center", marginTop: 4 },
});
