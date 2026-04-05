import requests
import subprocess
import yaml
import re
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

# ── Konfiguration ─────────────────────────────────────────────
LLAMA_SERVER  = "http://localhost:8080/v1"
VALUES_YAML   = Path.home() / "mac-setup/charts/ollama/values.yaml"
LOG_FILE      = Path.home() / "mac-setup/agent/agent.log"
MAC_SETUP_DIR = Path.home() / "mac-setup"
MODELS_DIR    = Path.home() / "models"
LLAMA_DIR     = Path.home() / "llama-cpp-turboquant"
DISK_WARN_GB  = 50
GPU_LIMIT_MB  = 52429

LLAMA_CMD = [
    str(LLAMA_DIR / "build/bin/llama-server"),
    "-m", str(Path.home() / "models/llama33-70b-q4km.gguf"),
    "--model-draft", str(Path.home() / "models/llama31-8b-draft.gguf"),
    "--cache-type-k", "turbo4",
    "--cache-type-v", "turbo4",
    "--cache-type-k-draft", "turbo4",
    "--cache-type-v-draft", "turbo4",
    "-ngl", "99",
    "-c", "16384",
    "-fa", "on",
    "--host", "0.0.0.0",
    "--port", "8080",
    "--draft-max", "8",
    "--draft-min", "2"
]

WATCH_REPOS = {
    "open-webui": {
        "github": "open-webui/open-webui",
        "values_key": "openWebui.image",
        "type": "operational"
    },
    "turboquant": {
        "github": "TheTom/llama-cpp-turboquant",
        "type": "performance"
    }
}

# ── State ──────────────────────────────────────────────────────
class AgentState(TypedDict):
    checks: list
    updates: list
    actions_taken: list
    notifications: list
    current_check: str

# ── LLM ───────────────────────────────────────────────────────
llm = ChatOpenAI(
    base_url=LLAMA_SERVER,
    api_key="dummy",
    model="llama33-70b-q4km.gguf",
    temperature=0
)

# ── Hilfsfunktionen ────────────────────────────────────────────
def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def run(cmd: list, cwd=None) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr
    except Exception as e:
        return 1, str(e)

def get_github_latest(repo: str) -> str | None:
    try:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("tag_name", "").lstrip("v")
    except Exception as e:
        log(f"GitHub API Fehler für {repo}: {e}")
    return None

def get_current_version_from_values(key: str) -> str | None:
    try:
        with open(VALUES_YAML) as f:
            content = yaml.safe_load(f)
        keys = key.split(".")
        val = content
        for k in keys:
            val = val[k]
        match = re.search(r":v?([\d.]+)", val)
        if match:
            return match.group(1)
    except Exception as e:
        log(f"Fehler beim Lesen von values.yaml: {e}")
    return None

def update_values_yaml(new_version: str) -> bool:
    try:
        with open(VALUES_YAML) as f:
            content = f.read()
        updated = re.sub(
            r"(open-webui:v?)[\d.]+",
            f"open-webui:v{new_version}",
            content
        )
        with open(VALUES_YAML, "w") as f:
            f.write(updated)
        return True
    except Exception as e:
        log(f"Fehler beim Update von values.yaml: {e}")
        return False

def git_commit_and_push(message: str) -> bool:
    code, out = run(["git", "add", "charts/ollama/values.yaml"], cwd=MAC_SETUP_DIR)
    code, out = run(["git", "commit", "-m", message], cwd=MAC_SETUP_DIR)
    if code != 0 and "nothing to commit" in out:
        return True
    code, out = run(["git", "push"], cwd=MAC_SETUP_DIR)
    return code == 0

# ── Node 1: GitHub Updates ─────────────────────────────────────
def check_updates(state: AgentState) -> AgentState:
    log("🔍 [1/5] GitHub Update-Check...")
    updates = []

    for name, config in WATCH_REPOS.items():
        latest = get_github_latest(config["github"])
        if not latest:
            continue

        if config["type"] == "operational" and "values_key" in config:
            current = get_current_version_from_values(config["values_key"])
            log(f"  {name}: aktuell=v{current}, latest=v{latest}")
            if current and latest != current:
                updates.append({
                    "name": name,
                    "current": current,
                    "latest": latest,
                    "type": config["type"],
                    "values_key": config.get("values_key"),
                })
        else:
            log(f"  {name}: v{latest} (performance-relevant, nur monitoring)")
            state["notifications"].append(
                f"📊 {name}: v{latest} verfügbar — manuelle Prüfung empfohlen"
            )

    state["updates"] = updates
    return state

# ── Node 2: LLM Klassifikation ─────────────────────────────────
def classify_and_decide(state: AgentState) -> AgentState:
    if not state["updates"]:
        log("  ✅ Keine operationalen Updates.")
        return state

    for update in state["updates"]:
        log(f"🤔 LLM klassifiziert: {update['name']} v{update['current']} → v{update['latest']}")

        curr = [int(x) for x in update["current"].split(".")]
        new  = [int(x) for x in update["latest"].split(".")]
        if new[0] > curr[0]:
            version_type = "MAJOR"
        elif new[1] > curr[1]:
            version_type = "MINOR"
        else:
            version_type = "PATCH"

        prompt = f"""Du bist ein Platform Operations Agent.
Regeln:
- PATCH Updates: IMMER JA
- MINOR Updates: JA wenn operational
- MAJOR Updates: NEIN

Update: {update['name']} {update['current']} → {update['latest']} ({version_type})
Antworte NUR mit JA oder NEIN."""

        response = llm.invoke(prompt)
        if "JA" in response.content.strip().upper()[:10]:
            update["action"] = "execute"
            log(f"  → JA — wird eingespielt")
        else:
            update["action"] = "notify_only"
            log(f"  → NEIN — nur Benachrichtigung")
            state["notifications"].append(
                f"⚠️ {update['name']} v{update['latest']}: manuelle Prüfung empfohlen"
            )

    return state

# ── Node 3: Updates ausführen ──────────────────────────────────
def execute_updates(state: AgentState) -> AgentState:
    for update in state["updates"]:
        if update.get("action") != "execute":
            continue
        log(f"🚀 Update: {update['name']} v{update['current']} → v{update['latest']}")
        if update_values_yaml(update["latest"]):
            log("  ✅ values.yaml aktualisiert")
            if git_commit_and_push(f"chore: update {update['name']} to v{update['latest']}"):
                log("  ✅ Git push — ArgoCD deployt automatisch")
                state["actions_taken"].append(f"Updated {update['name']} → v{update['latest']}")
                state["notifications"].append(
                    f"✅ AUTO-UPDATE: {update['name']} auf v{update['latest']}"
                )
    return state

# ── Node 4: K8s Health ─────────────────────────────────────────
def check_k8s_health(state: AgentState) -> AgentState:
    log("🏥 [2/5] K8s Health Check...")
    code, out = run(["kubectl", "get", "pods", "-n", "ollama"])

    if code != 0:
        log("  ⚠️ K8s nicht erreichbar — Docker läuft wahrscheinlich nicht")
        state["notifications"].append("⚠️ K8s nicht erreichbar")
        return state

    lines = out.strip().split("\n")[1:]  # Header überspringen
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        name, ready, status, restarts = parts[0], parts[1], parts[2], parts[3]

        if status in ["CrashLoopBackOff", "Error", "OOMKilled"]:
            log(f"  ❌ Pod {name} ist {status} — starte neu...")
            code2, out2 = run(["kubectl", "rollout", "restart",
                               f"deployment/{name.rsplit('-', 2)[0]}", "-n", "ollama"])
            if code2 == 0:
                log(f"  ✅ Pod {name} neu gestartet")
                state["actions_taken"].append(f"Pod {name} neu gestartet ({status})")
                state["notifications"].append(f"🔄 Pod {name} war {status} — neu gestartet")
            else:
                log(f"  ❌ Neustart fehlgeschlagen: {out2}")

        elif status == "Running":
            log(f"  ✅ {name}: {status} (restarts: {restarts})")
        else:
            log(f"  ⚠️ {name}: {status}")
            state["notifications"].append(f"⚠️ Pod {name}: {status}")

    return state

# ── Node 5: llama-server Watchdog ─────────────────────────────
def check_llama_server(state: AgentState) -> AgentState:
    log("🧠 [3/5] llama-server Watchdog...")

    code, out = run(["lsof", "-ti:8080"])
    is_running = code == 0 and out.strip()

    if is_running:
        log("  ✅ llama-server läuft auf Port 8080")
    else:
        log("  ❌ llama-server nicht aktiv — starte neu...")
        log_path = Path.home() / "mac-setup/agent/llama-server.log"
        with open(log_path, "a") as lf:
            proc = subprocess.Popen(
                LLAMA_CMD,
                stdout=lf,
                stderr=lf,
                cwd=str(LLAMA_DIR)
            )
        log(f"  ✅ llama-server gestartet (PID {proc.pid})")
        state["actions_taken"].append("llama-server neu gestartet")
        state["notifications"].append("🔄 llama-server war down — automatisch neu gestartet")

    return state

# ── Node 6: GPU Memory + Disk ──────────────────────────────────
def check_system_health(state: AgentState) -> AgentState:
    log("💻 [4/5] System Health...")

    # GPU Memory Limit prüfen
    code, out = run(["sysctl", "iogpu.wired_limit_mb"])
    if code == 0:
        match = re.search(r"iogpu\.wired_limit_mb:\s*(\d+)", out)
        if match:
            current_limit = int(match.group(1))
            if current_limit < GPU_LIMIT_MB:
                log(f"  ⚠️ GPU Limit zu niedrig ({current_limit} MB) — setze auf {GPU_LIMIT_MB} MB...")
                code2, _ = run(["sudo", "sysctl", f"iogpu.wired_limit_mb={GPU_LIMIT_MB}"])
                if code2 == 0:
                    log(f"  ✅ GPU Limit gesetzt: {GPU_LIMIT_MB} MB")
                    state["actions_taken"].append(f"GPU Memory Limit auf {GPU_LIMIT_MB} MB gesetzt")
                else:
                    log("  ❌ GPU Limit konnte nicht gesetzt werden (sudo nötig)")
            else:
                log(f"  ✅ GPU Memory Limit: {current_limit} MB")

    # Disk Space prüfen
    total, used, free = shutil.disk_usage(Path.home())
    free_gb = free // (1024**3)
    models_size = sum(
        f.stat().st_size for f in MODELS_DIR.rglob("*") if f.is_file()
    ) // (1024**3) if MODELS_DIR.exists() else 0

    log(f"  💾 Freier Speicher: {free_gb} GB | Modelle: {models_size} GB")

    if free_gb < DISK_WARN_GB:
        msg = f"⚠️ Wenig Speicher: nur {free_gb} GB frei (Limit: {DISK_WARN_GB} GB)"
        log(f"  {msg}")
        state["notifications"].append(msg)
    else:
        log(f"  ✅ Speicher OK")

    return state

# ── Node 7: ArgoCD Sync ────────────────────────────────────────
def check_argocd(state: AgentState) -> AgentState:
    log("🔄 [5/5] ArgoCD Sync Check...")

    code, out = run(["kubectl", "get", "applications", "-n", "argocd",
                     "-o", "jsonpath={.items[*].status.sync.status}"])

    if code != 0:
        log("  ⚠️ ArgoCD nicht erreichbar")
        return state

    statuses = out.strip().split()
    for i, status in enumerate(statuses):
        if status == "OutOfSync":
            log(f"  ⚠️ App {i} ist OutOfSync — triggere Sync...")
            run(["kubectl", "patch", "application", "-n", "argocd",
                 "--type", "merge", "-p",
                 '{"operation": {"initiatedBy": {"username": "agent"}, "sync": {}}}'])
            state["actions_taken"].append("ArgoCD Sync getriggert")
            state["notifications"].append("🔄 ArgoCD OutOfSync — Sync getriggert")
        elif status == "Synced":
            log(f"  ✅ ArgoCD: Synced")

    return state

# ── Node 8: Zusammenfassung ────────────────────────────────────
def notify(state: AgentState) -> AgentState:
    log("📋 Zusammenfassung:")
    if not state["notifications"] and not state["actions_taken"]:
        log("  ✅ Alles gesund — keine Änderungen.")
    for n in state["notifications"]:
        log(f"  {n}")
    if state["actions_taken"]:
        log("  Aktionen:")
        for a in state["actions_taken"]:
            log(f"    → {a}")
    log("─" * 60)
    return state

# ── Graph ──────────────────────────────────────────────────────
def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("check_updates", check_updates)
    graph.add_node("classify_and_decide", classify_and_decide)
    graph.add_node("execute_updates", execute_updates)
    graph.add_node("check_k8s_health", check_k8s_health)
    graph.add_node("check_llama_server", check_llama_server)
    graph.add_node("check_system_health", check_system_health)
    graph.add_node("check_argocd", check_argocd)
    graph.add_node("notify", notify)

    graph.set_entry_point("check_updates")
    graph.add_edge("check_updates", "classify_and_decide")
    graph.add_edge("classify_and_decide", "execute_updates")
    graph.add_edge("execute_updates", "check_k8s_health")
    graph.add_edge("check_k8s_health", "check_llama_server")
    graph.add_edge("check_llama_server", "check_system_health")
    graph.add_edge("check_system_health", "check_argocd")
    graph.add_edge("check_argocd", "notify")
    graph.add_edge("notify", END)

    return graph.compile()

# ── Main ───────────────────────────────────────────────────────
if __name__ == "__main__":
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log("=" * 60)
    log("🤖 Platform Agent v2 gestartet")

    agent = build_graph()
    result = agent.invoke({
        "checks": [],
        "updates": [],
        "actions_taken": [],
        "notifications": [],
        "current_check": ""
    })

    log("🤖 Platform Agent v2 beendet")
