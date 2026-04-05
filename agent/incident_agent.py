import requests
import subprocess
import shutil
import re
import json
from datetime import datetime
from pathlib import Path
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

# ── Konfiguration ──────────────────────────────────────────────
LLAMA_SERVER  = "http://localhost:8080/v1"
LOG_FILE      = Path.home() / "mac-setup/agent/agent.log"
STATE_FILE    = Path.home() / "mac-setup/agent/agent_state.json"
LLAMA_DIR     = Path.home() / "llama-cpp-turboquant"

LLAMA_CMD_8K = [
    str(LLAMA_DIR / "build/bin/llama-server"),
    "-m", str(Path.home() / "models/llama33-70b-q4km.gguf"),
    "--cache-type-k", "turbo4",
    "--cache-type-v", "turbo4",
    "-ngl", "99", "-c", "8192",
    "-fa", "on", "--host", "0.0.0.0", "--port", "8080"
]

LLAMA_CMD_16K = [
    str(LLAMA_DIR / "build/bin/llama-server"),
    "-m", str(Path.home() / "models/llama33-70b-q4km.gguf"),
    "--model-draft", str(Path.home() / "models/llama31-8b-draft.gguf"),
    "--cache-type-k", "turbo4", "--cache-type-v", "turbo4",
    "--cache-type-k-draft", "turbo4", "--cache-type-v-draft", "turbo4",
    "-ngl", "99", "-c", "16384", "-np", "1",
    "-fa", "on", "--host", "0.0.0.0", "--port", "8080",
    "--draft-max", "8", "--draft-min", "2"
]

# ── State ──────────────────────────────────────────────────────
class IncidentState(TypedDict):
    incident_type: str          # was ist passiert
    system_context: dict        # gesammelter Systemzustand
    llm_analysis: str           # LLM Analyse
    recommended_action: str     # A/B/C/D
    action_risk: str            # niedrig/mittel/hoch
    action_taken: str           # was wurde gemacht
    resolved: bool              # gelöst?
    escalate: bool              # manuell prüfen?
    messages: list[str]         # Log-Nachrichten

# ── LLM ───────────────────────────────────────────────────────
llm = ChatOpenAI(
    base_url=LLAMA_SERVER,
    api_key="dummy",
    model="llama33-70b-q4km.gguf",
    temperature=0
)

FALLBACK_SERVER = "http://localhost:8082/v1"
FALLBACK_CMD = [
    str(LLAMA_DIR / "build/bin/llama-server"),
    "-m", str(Path.home() / "models/llama31-8b-draft.gguf"),
    "--cache-type-k", "turbo4",
    "--cache-type-v", "turbo4",
    "-ngl", "99",
    "-c", "4096",
    "-fa", "on",
    "--host", "0.0.0.0",
    "--port", "8082"
]

def get_llm():
    """Gibt Haupt-LLM zurück, falls down → startet Fallback-LLM"""
    try:
        requests.get("http://localhost:8080/health", timeout=3)
        return ChatOpenAI(
            base_url=LLAMA_SERVER,
            api_key="dummy",
            model="llama33-70b-q4km.gguf",
            temperature=0
        ), False
    except:
        log("  ⚠️ Haupt-LLM (70B) nicht erreichbar — starte Fallback (8B)...")
        # Fallback starten falls noch nicht läuft
        try:
            requests.get("http://localhost:8082/health", timeout=3)
            log("  ✅ Fallback-LLM bereits aktiv")
        except:
            log("  🚀 Starte Llama 3.1 8B auf Port 8082...")
            log_path = Path.home() / "mac-setup/agent/fallback-llm.log"
            with open(log_path, "a") as lf:
                subprocess.Popen(
                    FALLBACK_CMD,
                    stdout=lf, stderr=lf,
                    cwd=str(LLAMA_DIR)
                )
            import time
            log("  ⏳ Warte 20s bis 8B geladen...")
            time.sleep(20)

        return ChatOpenAI(
            base_url=FALLBACK_SERVER,
            api_key="dummy",
            model="llama31-8b-draft.gguf",
            temperature=0
        ), True

# ── Hilfsfunktionen ────────────────────────────────────────────
def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def run(cmd: list, cwd=None) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout + r.stderr
    except Exception as e:
        return 1, str(e)

def load_persistent() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"llama_restarts": [], "seen_commits": [], "seen_models": {}}

# ── Node 1: System-Kontext sammeln ─────────────────────────────
def collect_context(state: IncidentState) -> IncidentState:
    log("📊 Sammle System-Kontext...")
    ctx = {}

    # RAM gesamt
    total, used, free = shutil.disk_usage(Path.home())
    ctx["disk_free_gb"] = free // (1024**3)

    # RAM via vm_stat
    code, out = run(["vm_stat"])
    if code == 0:
        pages_free = re.search(r"Pages free:\s+(\d+)", out)
        pages_wired = re.search(r"Pages wired down:\s+(\d+)", out)
        if pages_free:
            ctx["ram_free_gb"] = round(int(pages_free.group(1)) * 16384 / (1024**3), 1)
        if pages_wired:
            ctx["ram_wired_gb"] = round(int(pages_wired.group(1)) * 16384 / (1024**3), 1)

    # llama-server Status
    code, out = run(["lsof", "-ti:8080"])
    ctx["llama_running"] = code == 0 and bool(out.strip())

    # Aktive Slots
    try:
        r = requests.get("http://localhost:8080/slots", timeout=5)
        if r.status_code == 200:
            slots = r.json()
            ctx["active_slots"] = sum(1 for s in slots if s.get("state") == 1)
            ctx["total_slots"] = len(slots)
            ctx["tokens_cached"] = sum(s.get("tokens_cached", 0) for s in slots)
        else:
            ctx["active_slots"] = 0
            ctx["total_slots"] = 0
            ctx["tokens_cached"] = 0
    except:
        ctx["active_slots"] = 0
        ctx["total_slots"] = 0
        ctx["tokens_cached"] = 0

    # K8s Pod Status
    code, out = run(["kubectl", "get", "pods", "-n", "ollama"])
    ctx["k8s_pods"] = out if code == 0 else "nicht erreichbar"

    # Crash-Historie
    persistent = load_persistent()
    ctx["crashes_last_hour"] = len(persistent.get("llama_restarts", []))

    # Prozess RAM
    code, out = run(["ps", "aux"])
    if code == 0:
        for line in out.split("\n"):
            if "llama-server" in line and "grep" not in line:
                parts = line.split()
                if len(parts) > 3:
                    ctx["llama_ram_pct"] = parts[3]
            if "docker" in line.lower() and "com.docker.backend" in line:
                parts = line.split()
                if len(parts) > 3:
                    ctx["docker_ram_pct"] = parts[3]

    log(f"  RAM frei: {ctx.get('ram_free_gb', '?')} GB")
    log(f"  Aktive Slots: {ctx.get('active_slots', 0)}/{ctx.get('total_slots', 0)}")
    log(f"  Cached Tokens: {ctx.get('tokens_cached', 0)}")
    log(f"  Crashes letzte Stunde: {ctx.get('crashes_last_hour', 0)}")

    state["system_context"] = ctx
    return state

# ── Node 2: LLM Analyse ────────────────────────────────────────
def analyze_incident(state: IncidentState) -> IncidentState:
    log("🤔 LLM analysiert Incident...")
    ctx = state["system_context"]

    prompt = f"""Du bist ein erfahrener Platform Engineer der einen Incident auf einer lokalen KI-Plattform analysiert.

INCIDENT: {state["incident_type"]}

SYSTEM-ZUSTAND:
- Freier RAM: {ctx.get("ram_free_gb", "?")} GB (von 64 GB total)
- RAM belegt durch Kernel/GPU: {ctx.get("ram_wired_gb", "?")} GB
- llama-server läuft: {ctx.get("llama_running", False)}
- Aktive Nutzer-Slots: {ctx.get("active_slots", 0)} von {ctx.get("total_slots", 0)}
- Gecachte Tokens: {ctx.get("tokens_cached", 0)}
- Crashes letzte Stunde: {ctx.get("crashes_last_hour", 0)}
- K8s Pods: {ctx.get("k8s_pods", "unbekannt")}

KONTEXT:
- Das Hauptmodell (Llama 3.3 70B) braucht ~40 GB GPU-RAM
- K8s (Docker) braucht ~6 GB RAM
- KV-Cache bei 16K Kontext: ~2 GB (turbo4)
- KV-Cache bei 8K Kontext: ~1 GB (turbo4)

MÖGLICHE AKTIONEN:
A) K8s Pods auf 0 skalieren (spart 6GB RAM, unterbricht WebUI temporär) — sicher wenn keine aktiven Nutzer
B) llama-server mit 8K statt 16K Kontext neu starten (spart 1GB, kurze Unterbrechung) — sicher wenn aktive Tokens < 8000
C) llama-server neu starten ohne Änderungen (behebt Speicherlecks, kurze Unterbrechung)
D) Nichts tun — Problem eskalieren (wenn Ursache unklar oder Risiko hoch)

WICHTIGE REGELN:
- Wenn aktive Nutzer vorhanden: KEINE Kontext-Reduzierung
- Wenn Crashes > 3x in letzter Stunde: IMMER eskalieren
- Wenn RAM frei > 8 GB: wahrscheinlich kein RAM-Problem, andere Ursache suchen
- Wenn Ursache unklar: IMMER eskalieren

Antworte EXAKT in diesem Format:
URSACHE: [ein Satz was die Ursache ist]
AKTION: [A oder B oder C oder D]
BEGRÜNDUNG: [ein Satz warum diese Aktion]
RISIKO: [niedrig oder mittel oder hoch]"""

    active_llm, is_fallback = get_llm()
    if is_fallback:
        log("  📝 Analyse läuft mit Fallback-LLM (Llama 3.1 8B)")
    response = active_llm.invoke(prompt)
    analysis = response.content.strip()
    log(f"  LLM Antwort:\n{analysis}")

    # Parse LLM Antwort
    action_match = re.search(r"AKTION:\s*([ABCD])", analysis)
    risk_match = re.search(r"RISIKO:\s*(niedrig|mittel|hoch)", analysis, re.IGNORECASE)

    state["llm_analysis"] = analysis
    state["recommended_action"] = action_match.group(1) if action_match else "D"
    state["action_risk"] = risk_match.group(1).lower() if risk_match else "hoch"

    return state

# ── Node 3: Sicherheitscheck ───────────────────────────────────
def safety_check(state: IncidentState) -> IncidentState:
    log("🛡️ Sicherheitscheck...")
    ctx = state["system_context"]

    must_escalate = False
    reason = ""

    # Harte Regeln die LLM überschreiben
    if ctx.get("crashes_last_hour", 0) >= 3:
        must_escalate = True
        reason = f"Zu viele Crashes ({ctx['crashes_last_hour']}x in 1h)"

    # Aktion A niemals beim Startup — K8s Pods nicht stoppen
    if state["recommended_action"] == "A":
        must_escalate = True
        reason = "Aktion A (K8s stoppen) zu destruktiv — eskaliere stattdessen"

    if state["action_risk"] == "hoch":
        must_escalate = True
        reason = "LLM bewertet Risiko als hoch"

    if state["recommended_action"] == "B" and ctx.get("tokens_cached", 0) > 8000:
        must_escalate = True
        reason = f"Kontext-Reduzierung würde aktive Session zerstören ({ctx['tokens_cached']} tokens cached)"

    if state["recommended_action"] in ["A", "B"] and ctx.get("active_slots", 0) > 0:
        must_escalate = True
        reason = f"Aktive Nutzer vorhanden ({ctx['active_slots']} slots) — keine unterbrechenden Aktionen"

    if must_escalate:
        log(f"  ⚠️ Eskalation erzwungen: {reason}")
        state["escalate"] = True
        state["recommended_action"] = "D"
    else:
        log(f"  ✅ Sicherheitscheck bestanden — Aktion {state['recommended_action']} ist sicher")
        state["escalate"] = False

    return state

# ── Node 4: Aktion ausführen ───────────────────────────────────
def execute_action(state: IncidentState) -> IncidentState:
    if state["escalate"]:
        state["action_taken"] = "Eskaliert — keine automatische Aktion"
        return state

    action = state["recommended_action"]
    log(f"🚀 Führe Aktion {action} aus...")

    if action == "A":
        # K8s Pods auf 0
        run(["kubectl", "scale", "deployment", "ollama-app-ollama",
             "-n", "ollama", "--replicas=0"])
        run(["kubectl", "scale", "deployment", "ollama-app-open-webui",
             "-n", "ollama", "--replicas=0"])
        state["action_taken"] = "K8s Pods auf 0 skaliert"
        log("  ✅ K8s Pods gestoppt — 6 GB RAM freigegeben")

    elif action == "B":
        # llama-server mit 8K neu starten
        run(["lsof", "-ti:8080"])  # PID holen
        subprocess.run(["bash", "-c", "lsof -ti:8080 | xargs kill -9 2>/dev/null"])
        import time
        time.sleep(2)
        log_path = Path.home() / "mac-setup/agent/llama-server.log"
        with open(log_path, "a") as lf:
            proc = subprocess.Popen(LLAMA_CMD_8K, stdout=lf, stderr=lf, cwd=str(LLAMA_DIR))
        state["action_taken"] = f"llama-server mit 8K Kontext neu gestartet (PID {proc.pid})"
        log(f"  ✅ llama-server neu gestartet mit 8K Kontext")

    elif action == "C":
        # llama-server einfach neu starten
        subprocess.run(["bash", "-c", "lsof -ti:8080 | xargs kill -9 2>/dev/null"])
        import time
        time.sleep(2)
        log_path = Path.home() / "mac-setup/agent/llama-server.log"
        with open(log_path, "a") as lf:
            proc = subprocess.Popen(LLAMA_CMD_16K, stdout=lf, stderr=lf, cwd=str(LLAMA_DIR))
        state["action_taken"] = f"llama-server neu gestartet (PID {proc.pid})"
        log(f"  ✅ llama-server neu gestartet")

    elif action == "D":
        state["action_taken"] = "Keine Aktion — Eskalation"
        log("  ⚠️ Keine automatische Aktion")

    return state

# ── Node 5: Verifikation ───────────────────────────────────────
def verify_resolution(state: IncidentState) -> IncidentState:
    if state["escalate"] or state["recommended_action"] == "D":
        state["resolved"] = False
        return state

    log("🔍 Prüfe ob Problem gelöst...")
    import time
    time.sleep(5)  # kurz warten

    code, out = run(["lsof", "-ti:8080"])
    server_ok = code == 0 and bool(out.strip())

    code2, out2 = run(["kubectl", "get", "pods", "-n", "ollama"])
    k8s_ok = "Running" in out2 or state["recommended_action"] == "A"

    if server_ok:
        log("  ✅ llama-server läuft wieder")
        state["resolved"] = True
    else:
        log("  ❌ llama-server noch nicht bereit (lädt noch...)")
        state["resolved"] = False  # lädt noch, ist OK

    return state

# ── Node 6: Abschlussbericht ───────────────────────────────────
def final_report(state: IncidentState) -> IncidentState:
    log("📋 Incident Report:")
    log(f"  Incident:  {state['incident_type']}")
    log(f"  Analyse:   {state['llm_analysis'].split(chr(10))[0]}")
    log(f"  Aktion:    {state['action_taken']}")
    log(f"  Eskaliert: {state['escalate']}")
    log(f"  Gelöst:    {state['resolved']}")

    if state["escalate"]:
        log("  🚨 MANUELLE PRÜFUNG ERFORDERLICH")
    elif state["resolved"]:
        log("  ✅ Incident automatisch gelöst")
    else:
        log("  ⏳ Lösung in Arbeit (Server lädt)")

    log("─" * 60)
    return state

# ── Routing ────────────────────────────────────────────────────
def should_escalate(state: IncidentState) -> Literal["execute_action", "final_report"]:
    if state["escalate"]:
        return "final_report"
    return "execute_action"

# ── Graph ──────────────────────────────────────────────────────
def build_incident_graph():
    graph = StateGraph(IncidentState)

    graph.add_node("collect_context", collect_context)
    graph.add_node("analyze_incident", analyze_incident)
    graph.add_node("safety_check", safety_check)
    graph.add_node("execute_action", execute_action)
    graph.add_node("verify_resolution", verify_resolution)
    graph.add_node("final_report", final_report)

    graph.set_entry_point("collect_context")
    graph.add_edge("collect_context", "analyze_incident")
    graph.add_edge("analyze_incident", "safety_check")
    graph.add_conditional_edges("safety_check", should_escalate)
    graph.add_edge("execute_action", "verify_resolution")
    graph.add_edge("verify_resolution", "final_report")
    graph.add_edge("final_report", END)

    return graph.compile()

# ── Öffentliche Funktion für platform_agent.py ─────────────────
def handle_incident(incident_type: str) -> dict:
    agent = build_incident_graph()
    return agent.invoke({
        "incident_type": incident_type,
        "system_context": {},
        "llm_analysis": "",
        "recommended_action": "",
        "action_risk": "",
        "action_taken": "",
        "resolved": False,
        "escalate": False,
        "messages": []
    })

# ── Main (standalone Test) ─────────────────────────────────────
if __name__ == "__main__":
    import sys
    incident = sys.argv[1] if len(sys.argv) > 1 else "llama-server nicht erreichbar"
    log("=" * 60)
    log(f"🚨 Incident Response Agent gestartet: {incident}")
    result = handle_incident(incident)
    log("🚨 Incident Response Agent beendet")
