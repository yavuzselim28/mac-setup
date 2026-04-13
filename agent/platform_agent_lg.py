#!/opt/homebrew/bin/python3
"""
platform_agent_lg.py — LangGraph-basierter Platform Agent
Ersetzt: platform_agent.py + incident_agent.py
Behält:  intelligence_agent.py (als Tool), proxy.py, dashboard.html, LaunchAgents

Abhängigkeiten:
    pip3 install langgraph langchain-core langfuse requests pyyaml --break-system-packages
"""

import json
import subprocess
import time
import datetime
import os
import sys
import shutil
import logging
from pathlib import Path
from typing import TypedDict, Annotated, Literal
import operator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

# ── Optionales Langfuse Tracing (self-hosted, kein LangSmith nötig) ──────────
try:
    from langfuse.callback import CallbackHandler as LangfuseCallback
    LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://langfuse.local")
    langfuse_handler = LangfuseCallback(
        public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
        secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
        host=LANGFUSE_HOST,
    )
    TRACING = True
except Exception:
    langfuse_handler = None
    TRACING = False

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_FILE = Path.home() / "mac-setup" / "agent" / "platform_agent.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("platform_agent_lg")

# ── Pfade ─────────────────────────────────────────────────────────────────────
HOME             = Path.home()
AGENT_DIR        = HOME / "mac-setup" / "agent"
STATE_FILE       = AGENT_DIR / "agent_state.json"
KNOWLEDGE_DIR    = AGENT_DIR / "knowledge"
LLAMA_CPP_DIR    = HOME / "llama-cpp-turboquant"
LLAMA_SERVER_BIN = LLAMA_CPP_DIR / "build" / "bin" / "llama-server"
STARTUP_LOCK     = Path("/tmp/platform-startup.lock")
MAX_RESTARTS_PER_HOUR = 3

# ── State Definition ───────────────────────────────────────────────────────────
# Alles was früher über agent_state.json und globale Variablen lief,
# ist jetzt typsicher und automatisch persistiert via LangGraph Checkpointer.
class PlatformState(TypedDict):
    # Ergebnisse der einzelnen Check-Nodes
    k8s_health:       dict          # Pod-Status, Restart-Counts
    llama_status:     dict          # alive, port, tok/s, restart_count
    system_health:    dict          # GPU, Disk, Port-Forward, Build-SHA
    updates:          dict          # Open WebUI neue Version?
    unsloth_models:   dict          # neue GGUFs verfügbar?
    intelligence:     dict          # TurboQuant-Commits, neue Features

    # Incident-State (früher manuell in JSON + Counter)
    incident_action:  str           # "none" | "restart" | "fallback" | "give_up"
    restart_count:    int           # Resets stündlich via Checkpointer
    restart_history:  Annotated[list, operator.add]  # append-only log

    # Aggregiertes Ergebnis
    actions_taken:    Annotated[list, operator.add]
    errors:           Annotated[list, operator.add]
    report_md:        str

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def run(cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Shell-Kommando ausführen, (returncode, stdout, stderr) zurück."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", f"timeout after {timeout}s"
    except Exception as e:
        return 1, "", str(e)

def load_state_file() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}

def save_state_file(data: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2, default=str))

def restart_count_this_hour(state_file: dict) -> int:
    """Wie oft wurde llama-server in der letzten Stunde neugestartet?"""
    cutoff = time.time() - 3600
    history = state_file.get("restart_history", [])
    return sum(1 for ts in history if ts > cutoff)

# ── Nodes ──────────────────────────────────────────────────────────────────────

def node_check_k8s(state: PlatformState) -> dict:
    """K8s Pod Health — ersetzt check_k8s_health()"""
    log.info("Node: check_k8s — prüfe Pod-Status")
    kubectl = "/opt/homebrew/bin/kubectl"
    rc, out, err = run(
        f"{kubectl} get pods -A --no-headers "
        f"-o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,"
        f"STATUS:.status.phase,RESTARTS:.status.containerStatuses[0].restartCount'",
        timeout=15,
    )
    pods = []
    issues = []
    if rc == 0:
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                ns, name, status, restarts = parts[0], parts[1], parts[2], parts[3]
                try:
                    r = int(restarts)
                except ValueError:
                    r = 0
                pods.append({"ns": ns, "name": name, "status": status, "restarts": r})
                if status not in ("Running", "Completed", "Succeeded") or r > 500:
                    issues.append(f"{ns}/{name}: {status}, restarts={r}")
    else:
        issues.append(f"kubectl error: {err}")

    result = {"pods": pods, "issues": issues, "ok": len(issues) == 0}
    actions = [f"k8s: {len(issues)} issue(s)"] if issues else []
    log.info(f"  → {len(pods)} Pods, {len(issues)} Issues")
    return {"k8s_health": result, "actions_taken": actions}


def node_check_llama(state: PlatformState) -> dict:
    """llama-server Watchdog — ersetzt check_llama_server()"""
    log.info("Node: check_llama — prüfe llama-server auf Port 8080")
    import urllib.request
    alive = False
    tok_s = None
    try:
        with urllib.request.urlopen("http://localhost:8080/health", timeout=5) as r:
            alive = r.status == 200
    except Exception:
        pass

    # Metrics auslesen wenn alive
    if alive:
        try:
            with urllib.request.urlopen("http://localhost:8080/metrics", timeout=5) as r:
                for line in r.read().decode().splitlines():
                    if "llamacpp:tokens_per_second" in line and not line.startswith("#"):
                        tok_s = float(line.split()[-1])
        except Exception:
            pass

    sf = load_state_file()
    rc_hour = restart_count_this_hour(sf)

    result = {
        "alive": alive,
        "tok_s": tok_s,
        "restart_count_this_hour": rc_hour,
    }
    log.info(f"  → alive={alive}, tok/s={tok_s}, restarts/h={rc_hour}")
    return {"llama_status": result}


def node_incident(state: PlatformState) -> dict:
    """
    Incident Response — ersetzt incident_agent.py.
    LangGraph Conditional Edge entscheidet die Route statt if/else-Kaskaden.
    """
    log.info("Node: incident — llama-server DOWN, entscheide Aktion")
    status = state.get("llama_status", {})
    if status.get("alive", True):
        return {"incident_action": "none"}

    sf = load_state_file()
    rc_hour = restart_count_this_hour(sf)

    if rc_hour >= MAX_RESTARTS_PER_HOUR:
        log.warning(f"Max Restarts ({MAX_RESTARTS_PER_HOUR}/h) erreicht — gebe auf")
        return {
            "incident_action": "give_up",
            "errors": [f"llama-server tot, {rc_hour} Restarts diese Stunde — kein weiterer Versuch"],
        }

    # Startup-Lock prüfen (verhindert Race-Condition beim System-Boot)
    if STARTUP_LOCK.exists():
        age = time.time() - STARTUP_LOCK.stat().st_mtime
        if age < 120:
            log.info("Startup-Lock aktiv, warte")
            return {"incident_action": "none"}

    return {"incident_action": "restart"}


def node_do_restart(state: PlatformState) -> dict:
    """Aktion C: llama-server neu starten."""
    log.info("Node: do_restart — starte llama-server neu")
    # Alten Prozess beenden
    run("pkill -f llama-server", timeout=10)
    time.sleep(3)

    # ai-llama-fast Alias aus .zshrc auslesen (oder hardcoded Fallback)
    cmd = (
        f"{LLAMA_SERVER_BIN} "
        f"-m {HOME}/models/llama33-70b-q4km.gguf "
        f"--draft-model {HOME}/models/llama31-8b-draft.gguf "
        f"--draft-max 8 --draft-min 2 "
        f"--cache-type-k turbo4 --cache-type-v turbo4 "
        f"-fa -ngl 99 -c 32768 --port 8080 --metrics "
        f">> {LOG_FILE} 2>&1 &"
    )
    rc, _, err = run(cmd, timeout=10)

    time.sleep(8)  # Startzeit abwarten

    # Erfolg prüfen
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:8080/health", timeout=8) as r:
            success = r.status == 200
    except Exception:
        success = False

    now = time.time()
    sf = load_state_file()
    history = sf.get("restart_history", [])
    history.append(now)
    sf["restart_history"] = history
    save_state_file(sf)

    if success:
        log.info("llama-server erfolgreich neugestartet")
        return {
            "incident_action": "restarted",
            "actions_taken": [f"llama-server neugestartet ({datetime.datetime.now().strftime('%H:%M')})"],
            "restart_history": [now],
        }
    else:
        log.error("Neustart fehlgeschlagen — Fallback 8B")
        return {"incident_action": "fallback"}


def node_do_fallback(state: PlatformState) -> dict:
    """Fallback: Llama 3.1 8B auf Port 8082."""
    log.info("Node: do_fallback — starte 8B Fallback auf Port 8082")
    run("pkill -f 'llama-server.*8082'", timeout=5)
    time.sleep(2)
    cmd = (
        f"{LLAMA_SERVER_BIN} "
        f"-m {HOME}/models/llama31-8b-draft.gguf "
        f"-ngl 99 -c 8192 --port 8082 "
        f">> {LOG_FILE} 2>&1 &"
    )
    run(cmd, timeout=10)
    return {
        "incident_action": "fallback_started",
        "actions_taken": ["Fallback 8B auf Port 8082 gestartet"],
        "errors": ["llama-server 70B tot — Fallback aktiv"],
    }


def node_check_system(state: PlatformState) -> dict:
    """GPU Limit, Disk, Port-Forward, Build-SHA — ersetzt check_system_health()"""
    log.info("Node: check_system — GPU, Disk, Build-SHA, Port-Forward")
    result = {}
    actions = []

    # GPU Wired Limit
    rc, out, _ = run("sudo /usr/sbin/sysctl iogpu.wired_limit_mb", timeout=5)
    if rc == 0:
        try:
            current = int(out.split("=")[-1].strip())
            result["gpu_limit_mb"] = current
            if current != 52429:
                run("sudo /usr/sbin/sysctl -w iogpu.wired_limit_mb=52429", timeout=5)
                actions.append("GPU Limit auf 52429 MB gesetzt")
                result["gpu_limit_mb"] = 52429
        except ValueError:
            pass

    # Disk
    rc, out, _ = run("df -h / | tail -1", timeout=5)
    if rc == 0:
        parts = out.split()
        result["disk_used"] = parts[2] if len(parts) > 2 else "?"
        result["disk_avail"] = parts[3] if len(parts) > 3 else "?"

    # Port-Forward (3000 → Open WebUI)
    rc, out, _ = run("lsof -ti:3000", timeout=5)
    result["port_forward_ok"] = rc == 0 and bool(out.strip())

    # Build-SHA Auto-Detection
    rc, sha, _ = run(f"git -C {LLAMA_CPP_DIR} rev-parse HEAD", timeout=10)
    if rc == 0 and sha:
        sha = sha[:7]
        result["current_build_sha"] = sha
        # In agent_state.json eintragen
        sf = load_state_file()
        compiled = sf.get("compiled_commits", [])
        if sha not in compiled:
            compiled.append(sha)
            sf["compiled_commits"] = compiled
            actions.append(f"Neuer Build-SHA {sha} in compiled_commits eingetragen")
        sf["compiled_sha"] = sha
        sf["last_check"] = datetime.datetime.now().isoformat()
        save_state_file(sf)

        # performance.md updaten
        perf_file = KNOWLEDGE_DIR / "performance.md"
        if perf_file.exists():
            content = perf_file.read_text()
            block = (
                f"\n## Aktueller Build-Status\n"
                f"- SHA: {sha}\n"
                f"- Datum: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"- Compile-Befehl: cd ~/llama-cpp-turboquant && "
                f"cmake --build build --config Release -j$(sysctl -n hw.logicalcpu)\n"
            )
            # Alten Block ersetzen
            import re
            content = re.sub(r'\n## Aktueller Build-Status\n.*?(?=\n## |\Z)', block, content, flags=re.DOTALL)
            if "## Aktueller Build-Status" not in content:
                content += block
            perf_file.write_text(content)

    return {"system_health": result, "actions_taken": actions}


def node_check_updates(state: PlatformState) -> dict:
    """Open WebUI GitHub Release prüfen — ersetzt check_updates()"""
    log.info("Node: check_updates — prüfe Open WebUI GitHub Release")
    import urllib.request, json as _json
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/open-webui/open-webui/releases/latest",
            headers={"User-Agent": "platform-agent/2.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = _json.loads(r.read())
            latest = data.get("tag_name", "?")
            return {"updates": {"open_webui_latest": latest}}
    except Exception as e:
        return {"updates": {"error": str(e)}}


def node_check_unsloth(state: PlatformState) -> dict:
    """Neue GGUF-Modelle bei Unsloth — ersetzt check_unsloth_models()"""
    log.info("Node: check_unsloth — prüfe neue GGUF-Modelle")
    import urllib.request, json as _json
    models = []
    try:
        req = urllib.request.Request(
            "https://huggingface.co/api/models?author=unsloth&sort=lastModified&limit=5",
            headers={"User-Agent": "platform-agent/2.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = _json.loads(r.read())
            for m in data:
                models.append({"id": m.get("modelId"), "modified": m.get("lastModified")})
    except Exception as e:
        return {"unsloth_models": {"error": str(e)}}
    return {"unsloth_models": {"models": models}}


def node_run_intelligence(state: PlatformState) -> dict:
    """Intelligence Agent deaktiviert."""
    log.info("Node: run_intelligence — deaktiviert, wird übersprungen")
    return {"intelligence": {"skipped": True}}
    intel_script = AGENT_DIR / "intelligence_agent.py"
    if not intel_script.exists():
        return {"intelligence": {"error": "intelligence_agent.py nicht gefunden"}}
    rc, out, err = run(
        f"/opt/homebrew/bin/python3 {intel_script}",
        timeout=120,
    )
    if rc == 0:
        try:
            result = json.loads(out)
        except Exception:
            result = {"raw": out[:500]}
    else:
        result = {"error": err[:200]}
    return {"intelligence": result}


def node_update_mempalace(state: PlatformState) -> dict:
    """MemPalace mit neuem Wissen befüllen."""
    log.info("Node: update_mempalace — Wissen indexieren")
    # incidents.md updaten wenn Incident aufgetreten
    action = state.get("incident_action", "none")
    if action not in ("none", ""):
        incident_file = KNOWLEDGE_DIR / "incidents.md"
        entry = (
            f"\n### {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"- Aktion: {action}\n"
            f"- llama_status: {state.get('llama_status', {})}\n"
        )
        if incident_file.exists():
            incident_file.write_text(incident_file.read_text() + entry)
    # Reindex MemPalace (silent, Fehler ignorieren)
    run("/opt/homebrew/bin/python3 -m mempalace index", timeout=30)
    return {}


def node_build_report(state: PlatformState) -> dict:
    """Markdown-Report für Dashboard generieren."""
    log.info("Node: build_report — Markdown-Report generieren")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"# Platform Agent Report\n_{now}_\n"]

    # System
    sh = state.get("system_health", {})
    lines.append(f"## System\n- GPU Limit: {sh.get('gpu_limit_mb', '?')} MB")
    lines.append(f"- Disk: {sh.get('disk_used', '?')} used, {sh.get('disk_avail', '?')} frei")
    lines.append(f"- Port-Forward: {'✅' if sh.get('port_forward_ok') else '❌'}")
    if sh.get("current_build_sha"):
        lines.append(f"- Build SHA: `{sh['current_build_sha']}`")

    # llama-server
    ls = state.get("llama_status", {})
    lines.append(f"\n## llama-server\n- Status: {'✅ alive' if ls.get('alive') else '❌ down'}")
    if ls.get("tok_s"):
        lines.append(f"- Speed: {ls['tok_s']:.1f} tok/s")
    lines.append(f"- Restarts/h: {ls.get('restart_count_this_hour', 0)}")

    # K8s
    k8s = state.get("k8s_health", {})
    lines.append(f"\n## Kubernetes\n- Pods: {len(k8s.get('pods', []))}")
    if k8s.get("issues"):
        lines.append("- Issues:")
        for i in k8s["issues"]:
            lines.append(f"  - {i}")

    # Updates
    upd = state.get("updates", {})
    if upd.get("open_webui_latest"):
        lines.append(f"\n## Updates\n- Open WebUI latest: `{upd['open_webui_latest']}`")

    # Actions
    actions = state.get("actions_taken", [])
    if actions:
        lines.append(f"\n## Aktionen ({len(actions)})")
        for a in actions:
            lines.append(f"- {a}")

    # Errors
    errors = state.get("errors", [])
    if errors:
        lines.append(f"\n## Fehler")
        for e in errors:
            lines.append(f"- ⚠️ {e}")

    report = "\n".join(lines)

    # In agent_state.json persistieren (für Dashboard)
    sf = load_state_file()
    sf["last_report"] = report
    sf["last_run"] = now
    sf["actions_count"] = len(actions)
    save_state_file(sf)

    return {"report_md": report}


# ── Conditional Edges (Router-Funktionen) ─────────────────────────────────────

def route_after_llama_check(state: PlatformState) -> Literal["incident", "check_updates"]:
    """Wenn llama-server tot → Incident Node, sonst weiter."""
    if not state.get("llama_status", {}).get("alive", True):
        return "incident"
    return "check_updates"


def route_after_incident(state: PlatformState) -> Literal["do_restart", "do_fallback", "check_updates"]:
    """Incident-Entscheidung als expliziter Router — kein if/else im Code."""
    action = state.get("incident_action", "none")
    if action == "restart":
        return "do_restart"
    if action in ("fallback", "give_up"):
        return "do_fallback"
    return "check_updates"


def route_after_restart(state: PlatformState) -> Literal["do_fallback", "check_updates"]:
    """Nach Restart: Fallback wenn fehlgeschlagen."""
    if state.get("incident_action") == "fallback":
        return "do_fallback"
    return "check_updates"


# ── Graph Aufbau ──────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    g = StateGraph(PlatformState)

    # Nodes registrieren
    g.add_node("check_k8s",        node_check_k8s)
    g.add_node("check_llama",      node_check_llama)
    g.add_node("incident",         node_incident)
    g.add_node("do_restart",       node_do_restart)
    g.add_node("do_fallback",      node_do_fallback)
    g.add_node("check_updates",    node_check_updates)
    g.add_node("check_unsloth",    node_check_unsloth)
    g.add_node("check_system",     node_check_system)
    g.add_node("run_intelligence", node_run_intelligence)
    g.add_node("update_mempalace", node_update_mempalace)
    g.add_node("build_report",     node_build_report)

    # Entry Point: K8s + llama parallel starten
    g.set_entry_point("check_k8s")

    # Sequenz + Parallelisierung
    # K8s → llama check
    g.add_edge("check_k8s", "check_llama")

    # Nach llama check: Incident oder direkt weiter
    g.add_conditional_edges(
        "check_llama",
        route_after_llama_check,
        {"incident": "incident", "check_updates": "check_updates"},
    )

    # Incident Routing
    g.add_conditional_edges(
        "incident",
        route_after_incident,
        {
            "do_restart":    "do_restart",
            "do_fallback":   "do_fallback",
            "check_updates": "check_updates",
        },
    )

    # Nach Restart
    g.add_conditional_edges(
        "do_restart",
        route_after_restart,
        {"do_fallback": "do_fallback", "check_updates": "check_updates"},
    )

    # Fallback → weiter
    g.add_edge("do_fallback", "check_updates")

    # Parallele Checks nach Incident-Pfad
    g.add_edge("check_updates", "check_unsloth")
    g.add_edge("check_unsloth", "check_system")
    g.add_edge("check_system",  "run_intelligence")
    g.add_edge("run_intelligence", "update_mempalace")
    g.add_edge("update_mempalace", "build_report")
    g.add_edge("build_report", END)

    return g


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=== Platform Agent (LangGraph) gestartet ===")

    # Lockfile check (LaunchAgent Race-Condition)
    if STARTUP_LOCK.exists():
        age = time.time() - STARTUP_LOCK.stat().st_mtime
        if age < 60:
            log.info("Startup-Lock aktiv — beende früh")
            sys.exit(0)

    graph = build_graph()

    # Memory Checkpointer — State wird zwischen Runs gespeichert
    import sqlite3
    conn = sqlite3.connect(str(AGENT_DIR / "checkpoint.db"), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    app = graph.compile(checkpointer=checkpointer)

    # Config für diesen Run (thread_id = Hostname für Multi-Machine-Support)
    import socket
    config = {
        "configurable": {"thread_id": socket.gethostname()},
        "callbacks": [langfuse_handler] if TRACING and langfuse_handler else [],
    }

    # Initiales State (leere Werte — LangGraph merged das mit vorherigem Checkpoint)
    initial_state: PlatformState = {
        "k8s_health":     {},
        "llama_status":   {},
        "system_health":  {},
        "updates":        {},
        "unsloth_models": {},
        "intelligence":   {},
        "incident_action": "none",
        "restart_count":  0,
        "restart_history": [],
        "actions_taken":  [],
        "errors":         [],
        "report_md":      "",
    }

    try:
        result = app.invoke(initial_state, config=config)
        log.info("=== Agent-Run abgeschlossen ===")
        if result.get("report_md"):
            print(result["report_md"])
        if result.get("errors"):
            log.warning(f"Fehler: {result['errors']}")
    except Exception as e:
        log.error(f"Graph-Fehler: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
