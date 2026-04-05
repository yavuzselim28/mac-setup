import requests
import subprocess
import yaml
import re
from datetime import datetime
from pathlib import Path
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

LLAMA_SERVER  = "http://localhost:8080/v1"
VALUES_YAML   = Path.home() / "mac-setup/charts/ollama/values.yaml"
LOG_FILE      = Path.home() / "mac-setup/agent/agent.log"
MAC_SETUP_DIR = Path.home() / "mac-setup"

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

class AgentState(TypedDict):
    checks: list
    updates: list
    actions_taken: list
    notifications: list
    current_check: str

llm = ChatOpenAI(
    base_url=LLAMA_SERVER,
    api_key="dummy",
    model="llama33-70b-q4km.gguf",
    temperature=0
)

def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

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
    try:
        subprocess.run(["git", "add", "charts/ollama/values.yaml"],
                      cwd=MAC_SETUP_DIR, check=True)
        subprocess.run(["git", "commit", "-m", message],
                      cwd=MAC_SETUP_DIR, check=True)
        subprocess.run(["git", "push"],
                      cwd=MAC_SETUP_DIR, check=True)
        return True
    except Exception as e:
        log(f"Git Fehler: {e}")
        return False

def check_updates(state: AgentState) -> AgentState:
    log("🔍 Starte Update-Check...")
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
            log(f"  {name}: latest=v{latest} (performance-relevant, nur monitoring)")
            state["notifications"].append(
                f"📊 {name}: v{latest} verfügbar — manuelle Prüfung empfohlen"
            )

    state["updates"] = updates
    return state

def classify_and_decide(state: AgentState) -> AgentState:
    if not state["updates"]:
        log("✅ Keine operationalen Updates gefunden.")
        return state

    for update in state["updates"]:
        log(f"🤔 LLM klassifiziert: {update['name']} v{update['current']} → v{update['latest']}")

        # Versions-Typ bestimmen
        curr = [int(x) for x in update["current"].split(".")]
        new  = [int(x) for x in update["latest"].split(".")]

        if new[0] > curr[0]:
            version_type = "MAJOR"
        elif new[1] > curr[1]:
            version_type = "MINOR"
        else:
            version_type = "PATCH"

        prompt = f"""Du bist ein Platform Operations Agent für eine Kubernetes-Infrastruktur.

Regeln für automatische Updates:
- PATCH Updates (z.B. 0.8.11 → 0.8.12): IMMER automatisch einspielen, antworten mit JA
- MINOR Updates (z.B. 0.8.x → 0.9.0): automatisch einspielen wenn operational, antworten mit JA  
- MAJOR Updates (z.B. 0.x → 1.0): NIEMALS automatisch, antworten mit NEIN

Update-Details:
- Komponente: {update['name']} (Web-UI, kein Performance-Impact)
- Version: {update['current']} → {update['latest']}
- Typ: {version_type}

Antworte NUR mit JA oder NEIN."""

        response = llm.invoke(prompt)
        answer = response.content.strip().upper()

        if "JA" in answer[:10]:
            update["action"] = "execute"
            log(f"  → LLM: JA — Update wird eingespielt")
        else:
            update["action"] = "notify_only"
            log(f"  → LLM: NEIN — {response.content.strip()}")
            state["notifications"].append(
                f"⚠️ {update['name']} v{update['latest']}: LLM empfiehlt manuelle Prüfung"
            )

    return state

def execute_updates(state: AgentState) -> AgentState:
    for update in state["updates"]:
        if update.get("action") != "execute":
            continue

        log(f"🚀 Update: {update['name']} v{update['current']} → v{update['latest']}")

        if update_values_yaml(update["latest"]):
            log("  ✅ values.yaml aktualisiert")
            commit_msg = f"chore: update {update['name']} to v{update['latest']}"
            if git_commit_and_push(commit_msg):
                log("  ✅ Git commit + push erfolgreich")
                state["actions_taken"].append(
                    f"Updated {update['name']} {update['current']} → {update['latest']}"
                )
                state["notifications"].append(
                    f"✅ AUTO-UPDATE: {update['name']} auf v{update['latest']} — ArgoCD synct automatisch"
                )
            else:
                log("  ❌ Git push fehlgeschlagen")
        else:
            log("  ❌ values.yaml Update fehlgeschlagen")

    return state

def notify(state: AgentState) -> AgentState:
    log("📋 Zusammenfassung:")
    if not state["notifications"] and not state["actions_taken"]:
        log("  Alles aktuell, keine Änderungen.")
    for n in state["notifications"]:
        log(f"  {n}")
    log("─" * 60)
    return state

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("check_updates", check_updates)
    graph.add_node("classify_and_decide", classify_and_decide)
    graph.add_node("execute_updates", execute_updates)
    graph.add_node("notify", notify)
    graph.set_entry_point("check_updates")
    graph.add_edge("check_updates", "classify_and_decide")
    graph.add_edge("classify_and_decide", "execute_updates")
    graph.add_edge("execute_updates", "notify")
    graph.add_edge("notify", END)
    return graph.compile()

if __name__ == "__main__":
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log("=" * 60)
    log("🤖 Platform Agent gestartet")
    agent = build_graph()
    result = agent.invoke({
        "checks": [],
        "updates": [],
        "actions_taken": [],
        "notifications": [],
        "current_check": ""
    })
    log("🤖 Platform Agent beendet")
