import requests
import subprocess
import yaml
import re
import os
import shutil
import json
import functools
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypedDict
from langgraph.graph import StateGraph, END
from incident_agent import handle_incident

# Cron läuft mit einem minimalen PATH ohne /opt/homebrew/bin — helm/kubectl/git
# wären sonst über subprocess.run() nicht auffindbar.
for _p in ("/opt/homebrew/bin", "/usr/local/bin"):
    if _p not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = _p + os.pathsep + os.environ.get("PATH", "")

# ── Konfiguration ─────────────────────────────────────────────
VALUES_YAML   = Path.home() / "mac-setup/charts/ollama/values.yaml"
LOG_FILE      = Path.home() / "mac-setup/agent/agent.log"
STATE_FILE    = Path.home() / "mac-setup/agent/agent_state.json"
MAC_SETUP_DIR = Path.home() / "mac-setup"
MODELS_DIR    = Path.home() / "models"
LLAMA_DIR     = Path.home() / "llama-cpp-turboquant"
DISK_WARN_GB  = 50
GPU_LIMIT_MB  = 52429
MAX_RESTARTS_PER_HOUR = 3
K8S_NAMESPACE = "phoenix"
HELM_RELEASE  = "ollama-app"
HELM_CHART    = Path.home() / "ollama-k8s/ollama-chart"

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
    "--spec-draft-n-max", "8",
    "--spec-draft-n-min", "2"
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

UNSLOTH_MODELS = {
    "gemma4-31b": {
        "hf_repo": "unsloth/gemma-4-31B-it-GGUF",
        "local_file": "gemma4-31b/gemma-4-31B-it-UD-Q4_K_XL.gguf",
        "pattern": "UD-Q4_K_XL"
    },
    "glm-4.7-flash": {
        "hf_repo": "unsloth/GLM-4.7-Flash-GGUF",
        "local_file": "glm-4.7-flash/GLM-4.7-Flash-UD-Q4_K_XL.gguf",
        "pattern": "UD-Q4_K_XL"
    }
}

# ── State ──────────────────────────────────────────────────────
class AgentState(TypedDict):
    checks: list
    updates: list
    actions_taken: list
    notifications: list
    current_check: str

# ── Persistenter State (für Neustart-Limit) ────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"llama_restarts": [], "seen_commits": [], "seen_models": {}}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

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

def get_github_latest_commit(repo: str, branch: str = "feature/turboquant-kv-cache") -> str | None:
    try:
        url = f"https://api.github.com/repos/{repo}/commits/{branch}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            sha = data["sha"][:7]
            msg = data["commit"]["message"].split("\n")[0][:60]
            return sha, msg
    except Exception as e:
        log(f"GitHub Commit Fehler für {repo}: {e}")
    return None, None

def get_hf_latest_update(repo_id: str) -> str | None:
    try:
        url = f"https://huggingface.co/api/models/{repo_id}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("lastModified", "")
    except Exception as e:
        log(f"HuggingFace API Fehler für {repo_id}: {e}")
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
        # Kein "v"-Präfix: ghcr.io/open-webui/open-webui taggt Images ohne "v"
        # (z.B. "0.10.2"), auch wenn der GitHub-Release-Tag "v0.10.2" heißt.
        updated = re.sub(
            r"open-webui:v?[\d.]+",
            f"open-webui:{new_version}",
            content
        )
        with open(VALUES_YAML, "w") as f:
            f.write(updated)
        return True
    except Exception as e:
        log(f"Fehler beim Update von values.yaml: {e}")
        return False

def git_commit_and_push(message: str) -> bool:
    run(["git", "add", "charts/ollama/values.yaml"], cwd=MAC_SETUP_DIR)
    code, out = run(["git", "commit", "-m", message], cwd=MAC_SETUP_DIR)
    if code != 0 and "nothing to commit" in out:
        return True
    code, _ = run(["git", "push"], cwd=MAC_SETUP_DIR)
    return code == 0

def safe_node(func):
    """Isoliert Node-Fehler: eine fehlschlagende Node darf die restliche Pipeline
    (Health-Checks, Watchdog, etc.) nicht mit runterreißen."""
    @functools.wraps(func)
    def wrapper(state: AgentState) -> AgentState:
        try:
            return func(state)
        except Exception as e:
            msg = f"⚠️ Node '{func.__name__}' fehlgeschlagen: {e}"
            log(msg)
            log(traceback.format_exc())
            state.setdefault("notifications", []).append(msg)
            return state
    return wrapper

# ── Node 1: GitHub Updates ─────────────────────────────────────
@safe_node
def check_updates(state: AgentState) -> AgentState:
    log("🔍 [1/6] GitHub Update-Check...")
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
            log(f"  {name}: v{latest} (performance-relevant)")
            state["notifications"].append(
                f"📊 {name}: v{latest} verfügbar — manuelle Prüfung empfohlen"
            )

    state["updates"] = updates
    return state

# ── Node 2: Klassifikation ──────────────────────────────────────
# Deterministisch statt LLM-Aufruf: die Regel selbst ist bereits eine feste
# Regel ("PATCH immer JA, MINOR JA wenn operational, MAJOR NEIN") und braucht
# kein LLM. Der vorherige llm.invoke() gegen localhost:8080 crashte die ganze
# Pipeline (inkl. aller nachgelagerten Health-Checks/Watchdog), sobald
# llama-server nicht lief — was hier der Regelfall war.
@safe_node
def classify_and_decide(state: AgentState) -> AgentState:
    if not state["updates"]:
        log("  ✅ Keine operationalen Updates.")
        return state

    for update in state["updates"]:
        curr = [int(x) for x in update["current"].split(".")]
        new  = [int(x) for x in update["latest"].split(".")]
        if new[0] > curr[0]:
            version_type = "MAJOR"
        elif new[1] > curr[1]:
            version_type = "MINOR"
        else:
            version_type = "PATCH"

        log(f"🤔 Klassifiziert: {update['name']} v{update['current']} → v{update['latest']} ({version_type})")

        if version_type == "PATCH":
            decision = True
        elif version_type == "MINOR":
            decision = update["type"] == "operational"
        else:
            decision = False

        if decision:
            update["action"] = "execute"
            log(f"  → JA — wird eingespielt")
        else:
            update["action"] = "notify_only"
            log(f"  → NEIN — nur Benachrichtigung")

    return state

# ── Node 3: Updates ausführen ──────────────────────────────────
@safe_node
def execute_updates(state: AgentState) -> AgentState:
    for update in state["updates"]:
        if update.get("action") != "execute":
            continue
        log(f"🚀 Update: {update['name']} v{update['current']} → v{update['latest']}")
        if not update_values_yaml(update["latest"]):
            continue
        log("  ✅ values.yaml aktualisiert")

        code, out = run([
            "helm", "upgrade", HELM_RELEASE, str(HELM_CHART),
            "-n", K8S_NAMESPACE, "-f", str(VALUES_YAML)
        ])
        if code != 0:
            msg = f"❌ helm upgrade für {update['name']} fehlgeschlagen: {out.strip()[-300:]}"
            log(f"  {msg}")
            state["notifications"].append(msg)
            continue
        log("  ✅ helm upgrade ausgeführt")

        deployment = f"ollama-app-{update['name']}"
        code, out = run([
            "kubectl", "rollout", "status", f"deployment/{deployment}",
            "-n", K8S_NAMESPACE, "--timeout=120s"
        ])
        if code != 0:
            msg = f"❌ Rollout für {deployment} fehlgeschlagen/timeout: {out.strip()[-300:]}"
            log(f"  {msg}")
            state["notifications"].append(msg)
            continue
        log("  ✅ Rollout erfolgreich")

        if git_commit_and_push(f"chore: update {update['name']} to v{update['latest']}"):
            log("  ✅ Git committed & gepusht")
            state["actions_taken"].append(f"Updated {update['name']} → v{update['latest']} (deployed + committed)")
            state["notifications"].append(
                f"✅ AUTO-UPDATE: {update['name']} auf v{update['latest']} — live deployed"
            )
        else:
            msg = f"⚠️ {update['name']} deployed, aber Git-Push fehlgeschlagen — values.yaml lokal geändert, nicht committed"
            log(f"  {msg}")
            state["notifications"].append(msg)
    return state

# ── Node 4: K8s Health ─────────────────────────────────────────
@safe_node
def check_k8s_health(state: AgentState) -> AgentState:
    log("🏥 [2/6] K8s Health Check...")
    code, out = run(["kubectl", "get", "pods", "-n", K8S_NAMESPACE])

    if code != 0:
        log("  ⚠️ K8s nicht erreichbar")
        state["notifications"].append("⚠️ K8s nicht erreichbar — Docker läuft evtl. nicht")
        return state

    lines = out.strip().split("\n")[1:]
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        name, ready, status, restarts = parts[0], parts[1], parts[2], parts[3]

        if status in ["CrashLoopBackOff", "Error", "OOMKilled"]:
            log(f"  ❌ Pod {name}: {status} — starte neu...")
            deploy = "-".join(name.split("-")[:-2])
            code2, _ = run(["kubectl", "rollout", "restart",
                            f"deployment/{deploy}", "-n", K8S_NAMESPACE])
            if code2 == 0:
                log(f"  ✅ {name} neu gestartet")
                state["actions_taken"].append(f"Pod {name} neu gestartet ({status})")
                state["notifications"].append(f"🔄 Pod {name} war {status} — neu gestartet")
        elif status == "Running":
            log(f"  ✅ {name}: Running (restarts: {restarts})")
        else:
            log(f"  ⚠️ {name}: {status}")
            state["notifications"].append(f"⚠️ Pod {name}: {status}")

    return state

# ── Node 5: llama-server Watchdog ─────────────────────────────
@safe_node
def check_llama_server(state: AgentState) -> AgentState:
    log("🧠 [3/6] llama-server Watchdog...")

    persistent = load_state()
    now = datetime.now().isoformat()

    # Neustart-History bereinigen (nur letzte Stunde)
    one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
    persistent["llama_restarts"] = [
        t for t in persistent["llama_restarts"] if t > one_hour_ago
    ]

    code, out = run(["lsof", "-ti:8080"])
    is_running = code == 0 and out.strip()

    if is_running:
        log("  ✅ llama-server läuft auf Port 8080")
    else:
        restarts_last_hour = len(persistent["llama_restarts"])

        if restarts_last_hour >= MAX_RESTARTS_PER_HOUR:
            msg = f"🚨 llama-server crasht wiederholt ({restarts_last_hour}x in 1h) — manuelle Prüfung nötig"
            log(f"  ❌ {msg}")
            state["notifications"].append(msg)
        else:
            log(f"  ❌ llama-server down — rufe Incident Agent auf...")
            import sys
            sys.path.insert(0, str(Path.home() / "mac-setup/agent"))
            from incident_agent import handle_incident
            result = handle_incident("llama-server nicht erreichbar — automatisch erkannt durch Watchdog")
            persistent["llama_restarts"].append(now)
            if result.get("resolved"):
                log("  ✅ Incident Agent hat Problem gelöst")
                state["actions_taken"].append("llama-server durch Incident Agent wiederhergestellt")
                state["notifications"].append("🔄 llama-server war down — Incident Agent hat ihn repariert")
            elif result.get("escalate"):
                log("  🚨 Incident Agent eskaliert — manuelle Prüfung nötig")
                state["notifications"].append("🚨 llama-server Incident eskaliert — manuelle Prüfung erforderlich")
            else:
                log("  ⏳ Incident Agent: Lösung in Arbeit")
                state["notifications"].append("⏳ llama-server wird wiederhergestellt")

    save_state(persistent)
    return state

# ── Node 6: System Health ──────────────────────────────────────
@safe_node
def check_system_health(state: AgentState) -> AgentState:
    log("💻 [4/6] System Health...")

    # GPU Memory Limit
    code, out = run(["sysctl", "iogpu.wired_limit_mb"])
    if code == 0:
        match = re.search(r"iogpu\.wired_limit_mb:\s*(\d+)", out)
        if match:
            current_limit = int(match.group(1))
            if current_limit < GPU_LIMIT_MB:
                log(f"  ⚠️ GPU Limit zu niedrig ({current_limit}) — setze auf {GPU_LIMIT_MB}...")
                run(["sudo", "sysctl", f"iogpu.wired_limit_mb={GPU_LIMIT_MB}"])
                state["actions_taken"].append("GPU Memory Limit neu gesetzt")
            else:
                log(f"  ✅ GPU Memory Limit: {current_limit} MB")

    # Disk Space
    total, used, free = shutil.disk_usage(Path.home())
    free_gb = free // (1024**3)
    models_size = sum(
        f.stat().st_size for f in MODELS_DIR.rglob("*") if f.is_file()
    ) // (1024**3) if MODELS_DIR.exists() else 0

    log(f"  💾 Frei: {free_gb} GB | Modelle: {models_size} GB")

    if free_gb < DISK_WARN_GB:
        msg = f"⚠️ Wenig Speicher: {free_gb} GB frei"
        log(f"  {msg}")
        state["notifications"].append(msg)
    else:
        log(f"  ✅ Speicher OK")

    # Port-Forward Check
    code, out = run(["lsof", "-ti:80"])
    if code == 0 and out.strip():
        log("  ✅ Port-Forward Port 80: aktiv")
    else:
        log("  ⚠️ Port-Forward Port 80: nicht aktiv — starte neu...")
        subprocess.Popen(
            ["sudo", "kubectl", "port-forward",
             "svc/ingress-nginx-controller", "80:80", "-n", "ingress-nginx"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        log("  ✅ Port-Forward neu gestartet")
        state["actions_taken"].append("Port-Forward Port 80 neu gestartet")

    # Aktuell kompilierten Commit erkennen und in State schreiben
    try:
        code, current_sha = run(["git", "-C", str(LLAMA_DIR), "rev-parse", "HEAD"])
        if code == 0 and current_sha.strip():
            short = current_sha.strip()[:7]
            persistent = load_state()
            compiled_commits = persistent.get("compiled_commits", [])
            if short not in compiled_commits:
                compiled_commits.insert(0, short)
                compiled_commits = compiled_commits[:20]
                persistent["compiled_commits"] = compiled_commits
                persistent["compiled_sha"] = short
                persistent["compiled_date"] = datetime.now().strftime("%Y-%m-%d")
                save_state(persistent)
                log(f"  ✅ Kompilierter Commit erkannt: {short}")
            else:
                log(f"  ✅ Build-Stand: {short} (bereits bekannt)")
    except Exception as e:
        log(f"  ⚠️ Build-Commit nicht lesbar: {e}")

    # MemPalace Build-Status aktualisieren
    try:
        persistent = load_state()
        compiled = persistent.get("compiled_commits", [])
        compiled_sha = persistent.get("compiled_sha", "?")
        compiled_date = persistent.get("compiled_date", "?")
        knowledge_file = Path.home() / "mac-setup/agent/knowledge/performance.md"
        with open(knowledge_file, "r") as f:
            perf_content = f.read()
        build_marker = "## Aktueller Build-Status"
        build_entry = f"""## Aktueller Build-Status
- HEAD: {compiled_sha} (kompiliert am {compiled_date})
- Branch: feature/turboquant-kv-cache
- Kompilierte Commits: {", ".join(compiled[:5])}
- Build-Befehl: cd ~/llama-cpp-turboquant && cmake --build build --config Release -j$(sysctl -n hw.logicalcpu)
- Letzte Aktualisierung: {datetime.now().strftime("%Y-%m-%d %H:%M")}
"""
        if build_marker in perf_content:
            import re as _re
            start = perf_content.index(build_marker)
            next_sec = perf_content.find("\n##", start + 1)
            if next_sec == -1:
                perf_content = perf_content[:start] + build_entry
            else:
                perf_content = perf_content[:start] + build_entry + perf_content[next_sec:]
        else:
            perf_content += "\n" + build_entry
        with open(knowledge_file, "w") as f:
            f.write(perf_content)
        subprocess.run(
            ["mempalace", "mine", str(knowledge_file.parent), "--wing", "platform"],
            capture_output=True, timeout=30
        )
        log(f"  ✅ MemPalace Build-Status aktualisiert ({compiled_sha})")
    except Exception as me:
        log(f"  ⚠️ MemPalace Build-Update: {me}")

    # intelligence.json compiled-Flags aktualisieren
    try:
        intel_file = Path.home() / "mac-setup/agent/intelligence.json"
        if intel_file.exists():
            intel = json.loads(intel_file.read_text())
            compiled_list = load_state().get("compiled_commits", [])
            for a in intel.get("analyses", []):
                a["compiled"] = a.get("short_sha", "") in compiled_list
            intel_file.write_text(json.dumps(intel, indent=2))
            log(f"  ✅ intelligence.json compiled-Flags aktualisiert")
    except Exception as e:
        log(f"  ⚠️ intelligence.json Update: {e}")

    return state

# ── Node 7: Unsloth Modell-Watcher ────────────────────────────
@safe_node
def check_unsloth_models(state: AgentState) -> AgentState:
    log("🤗 [5/6] Unsloth Modell-Watcher...")
    persistent = load_state()

    for model_name, config in UNSLOTH_MODELS.items():
        last_modified = get_hf_latest_update(config["hf_repo"])
        if not last_modified:
            continue

        previous = persistent["seen_models"].get(model_name, "")

        if previous and last_modified != previous:
            msg = f"🆕 {model_name}: Unsloth hat {config['hf_repo']} aktualisiert — neues GGUF verfügbar?"
            log(f"  {msg}")
            state["notifications"].append(msg)
        elif not previous:
            log(f"  📝 {model_name}: erstmals gesehen ({last_modified[:10]})")
        else:
            log(f"  ✅ {model_name}: keine Änderung")

        persistent["seen_models"][model_name] = last_modified

    save_state(persistent)
    return state

# ── Node 8: ArgoCD + TurboQuant Commits ───────────────────────
@safe_node
def check_argocd_and_commits(state: AgentState) -> AgentState:
    log("🔄 [6/6] ArgoCD + TurboQuant Commits...")

    # ArgoCD
    code, out = run(["kubectl", "get", "applications", "-n", "argocd",
                     "-o", "jsonpath={.items[*].status.sync.status}"])
    if code == 0 and out.strip():
        for status in out.strip().split():
            if status == "OutOfSync":
                log("  ⚠️ ArgoCD OutOfSync — triggere Sync...")
                run(["kubectl", "patch", "application", "-n", "argocd",
                     "--type", "merge", "-p",
                     '{"operation": {"initiatedBy": {"username": "agent"}, "sync": {}}}'])
                state["actions_taken"].append("ArgoCD Sync getriggert")
            elif status == "Synced":
                log("  ✅ ArgoCD: Synced")
    else:
        log("  ⚠️ ArgoCD nicht erreichbar")

    # TurboQuant neue Commits
    persistent = load_state()
    sha, msg = get_github_latest_commit("TheTom/llama-cpp-turboquant")
    if sha:
        last_seen = persistent.get("seen_commits", [])
        if sha not in last_seen:
            notification = f"🔬 TurboQuant neuer Commit: [{sha}] {msg}"
            log(f"  {notification}")
            state["notifications"].append(notification)
            persistent["seen_commits"] = ([sha] + last_seen)[:20]
            save_state(persistent)
        else:
            log(f"  ✅ TurboQuant: kein neuer Commit ({sha})")

    return state

# ── Node 9: Zusammenfassung ────────────────────────────────────
@safe_node
def notify(state: AgentState) -> AgentState:
    log("📋 Zusammenfassung:")
    if not state["notifications"] and not state["actions_taken"]:
        log("  ✅ Alles gesund — keine Änderungen.")
    for n in state["notifications"]:
        log(f"  {n}")
    if state["actions_taken"]:
        log("  Aktionen durchgeführt:")
        for a in state["actions_taken"]:
            log(f"    → {a}")
    log("─" * 60)
    return state


# ── Intelligence Agent Integration ────────────────────────────
@safe_node
def run_intelligence(state: AgentState) -> AgentState:
    log("🧠 [7/7] Intelligence Agent...")
    import sys
    sys.path.insert(0, str(Path.home() / "mac-setup/agent"))
    from intelligence_agent import build_graph as build_intel_graph

    intel_agent = build_intel_graph()
    result = intel_agent.invoke({
        "commits": [],
        "prs": [],
        "analyses": [],
        "weekly_report": "",
        "notifications": []
    })

    for n in result.get("notifications", []):
        state["notifications"].append(n)

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
    graph.add_node("check_unsloth_models", check_unsloth_models)
    graph.add_node("check_argocd_and_commits", check_argocd_and_commits)
    graph.add_node("notify", notify)

    graph.set_entry_point("check_updates")
    graph.add_edge("check_updates", "classify_and_decide")
    graph.add_edge("classify_and_decide", "execute_updates")
    graph.add_edge("execute_updates", "check_k8s_health")
    graph.add_edge("check_k8s_health", "check_llama_server")
    graph.add_edge("check_llama_server", "check_system_health")
    graph.add_edge("check_system_health", "check_unsloth_models")
    graph.add_edge("check_unsloth_models", "check_argocd_and_commits")
    graph.add_node("run_intelligence", run_intelligence)
    graph.add_edge("check_argocd_and_commits", "run_intelligence")
    graph.add_edge("run_intelligence", "notify")
    graph.add_edge("notify", END)

    return graph.compile()

# ── Main ───────────────────────────────────────────────────────
if __name__ == "__main__":
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log("=" * 60)
    log("🤖 Platform Agent v3 gestartet")

    agent = build_graph()
    result = agent.invoke({
        "checks": [],
        "updates": [],
        "actions_taken": [],
        "notifications": [],
        "current_check": ""
    })

    log("🤖 Platform Agent v3 beendet")
# Import wird oben eingefügt — separater Patch

