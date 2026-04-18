# SYSTEM_CONTEXT — Yavuz Topcu (Stand: April 2026)

## Wer bin ich
Platform Engineer bei Audi AG (seit März 2025).
Arbeite mit ROSA (Red Hat OpenShift on AWS), Kubernetes, Terraform, AWS.
Dieses Projekt ist mein lokales AI-Setup zum Lernen und Testen.

## Hardware
- MacBook Pro M5 Pro, 64GB Unified Memory, 1TB SSD
- Apple Silicon GPU (Metal) — Compiler: Clang (NICHT GCC)
- GPU Memory Limit: sudo sysctl iogpu.wired_limit_mb=52429
- Tailscale IP: 100.78.80.6

## Lokaler AI Stack

### llama-server
- Fork: TheTom/llama-cpp-turboquant (branch: feature/turboquant-kv-cache)
- Binary: ~/llama-cpp-turboquant/build/bin/llama-server
- Kompilieren: cd ~/llama-cpp-turboquant && cmake --build build --config Release -j$(sysctl -n hw.logicalcpu)
- Aktueller HEAD: 40b6f96 (Merge pull request #60 from TheTom/feature/alpha-scaling)
- Offizieller Release: tqp-v0.1.0 (tag auf eea498c) — TQ4_1S 3.5x faster, AMD RDNA4, Vulkan turbo3

### Kompilierte Commits (compiled_commits in agent_state.json)
| SHA | Beschreibung | Status |
|-----|-------------|--------|
| 40b6f96 | Merge alpha-scaling (aktueller HEAD) | ✅ kompiliert |
| 830eb54 | fix: cap map0 kernel shmem for 256-expert MoE | ✅ kompiliert |
| acad28d | feat: MoE expert count + TQ4_1S backend tests | ✅ kompiliert |
| cffcbf0 | (älterer Commit) | ✅ kompiliert |

### Modelle
| Alias | Modell | Größe | Pfad |
|-------|--------|-------|------|
| ai-llama | Llama 3.3 70B Q4_K_M | 40GB | ~/models/llama33-70b-q4km.gguf |
| ai-llama-fast | 70B + 8B Draft (Spec. Decoding) | 40+4.6GB | + ~/models/llama31-8b-draft.gguf |
| ai-gemma | Gemma 4 31B UD-Q4_K_XL | 17GB | ~/models/gemma4-31b/ |
| ai-qwen | Qwen 2.5 72B Q4_K_M | 44GB | ~/models/qwen25-72b/ |
| ai-mistral | Mistral 7B Q4_K_M | 4GB | ~/models/mistral-7b-q4km.gguf |

### TurboQuant Konfiguration
- Cache: --cache-type-k turbo4 --cache-type-v turbo4
- turbo4: 4.25 bit, 3.8x KV-Cache Kompression, +6.3% PPL-Verlust
- Sparse V: automatisch aktiv ("turbo3 sparse V dequant enabled" beim Start)
- Flash Attention: -fa on
- Kontext: 32768 tokens (32k)
- GPU Offload: -ngl 99

### Speculative Decoding (ai-llama-fast)
- Draft: Llama 3.1 8B, --draft-max 8 --draft-min 2
- Ergebnis: ~10 tok/s, 88% Acceptance Rate
- Draft KV-Cache: auch turbo4

### Performance Benchmarks
- Prompt Eval: 83.93 tok/s
- Decode: 8.31 tok/s
- KV-Cache bei 32k: ~2.7GB (turbo4) vs ~10.8GB (FP16)

## Netzwerk
- Loopback Alias: 10.254.254.254 (funktioniert ohne WLAN)
- Open WebUI URL in K8s: http://10.254.254.254:8080/v1
- Port-Forward: localhost:3000 → Open WebUI (--address 0.0.0.0)
- llama-server: MANUELL starten mit ai-llama-fast (NICHT automatisch)

## Kubernetes Infrastruktur
- Docker Desktop local, namespace: ollama
- Deployments: ollama-app-ollama, ollama-app-open-webui
- Monitoring: kube-prometheus-stack (Grafana: grafana.local, admin/newpassword123)
- ArgoCD GitOps: yavuzselim28/mac-setup
- Helm Charts: ~/mac-setup/charts/

## LaunchAgents (automatischer Start)
- com.yavuz.platform-agent → stündlicher Health Check
- com.yavuz.startup-terminal → Terminal mit Live-Log beim Login
- com.yavuz.port-forward → Port-Forward dauerhaft auf localhost:3000
- com.yavuz.dashboard → HTTP Server + Proxy auf localhost:8999

## Agent System

### Platform Agent (~/mac-setup/agent/platform_agent.py)
- check_updates: Open WebUI GitHub Release
- check_k8s_health: Pods überwachen, Restarts
- check_llama_server: Watchdog → Incident Agent
- check_system_health: GPU Limit, Disk, Port-Forward, Build-Commit auto-detect, MemPalace Update, intelligence.json compiled-Flags sync
- check_unsloth_models: neue GGUF-Versionen
- check_argocd_and_commits: ArgoCD Sync, TurboQuant Commits
- run_intelligence: Intelligence Agent aufrufen

### Build-Commit Auto-Detection (in check_system_health)
- Liest bei jedem Run: git -C ~/llama-cpp-turboquant rev-parse HEAD
- Schreibt HEAD automatisch in compiled_commits + compiled_sha in agent_state.json
- Aktualisiert performance.md mit "## Aktueller Build-Status" Block
- Synct intelligence.json compiled-Flags gegen compiled_commits bei jedem Run
- Kein manueller Eingriff nötig nach git pull + cmake

### Incident Agent (~/mac-setup/agent/incident_agent.py)
- Aktion A (K8s stoppen): DEAKTIVIERT — zu destruktiv
- Aktion C: llama-server neu starten (bevorzugt)
- Fallback: Llama 3.1 8B auf Port 8082
- Max Restarts: 3x pro Stunde
- Startup Lockfile: /tmp/platform-startup.lock

### Intelligence Agent (~/mac-setup/agent/intelligence_agent.py)
Beobachtete Repos:
- TheTom/llama-cpp-turboquant (feature/turboquant-kv-cache) — primär, kompilierbar
- milla-jovovich/mempalace — Memory System
- SharpAI/SwiftLM — Swift Server
- arozanov/turboquant-mlx — MLX Port

Stack-Grenzen: NUR TheTom Commits kompilierbar.
MLX Repos (arozanov, helgklaizar, rachittshah, SharpAI) = anderer Stack.

LLM-Analyse-Prompt enthält BUILD-STATUS Block:
- Aktuell kompilierter HEAD + Datum
- Liste compiled_commits
- Branch-Name + exakter cmake-Befehl

### Dashboard (~/mac-setup/agent/dashboard.html)
- URL: http://localhost:8999/dashboard.html
- Proxy: ~/mac-setup/agent/proxy.py (Port 8999)
- Run Agent Button: POST /run-agent → startet platform_agent.py als Subprocess, pollt /agent-status alle 2s
- explain-box: Antwort bleibt nach Refresh erhalten (explainCache im JS)
- Refresh Button: resettet Countdown korrekt (manualRefresh())
- compiled_commits Array-Check: zeigt ✅ kompiliert für alle bekannten SHAs
- Aktionen-Zähler: zählt nur echte Agent-Aktionen (neu gestartet, Sync, GPU)

### Proxy (~/mac-setup/agent/proxy.py)
Endpoints:
- POST /llm → leitet zu localhost:8080/v1/chat/completions (timeout 120s)
- POST /run-agent → startet platform_agent.py im Hintergrund (threading.Lock, kein Doppelstart)
- GET /agent-status → {running: bool, pid: int}
- GET /* → SimpleHTTPRequestHandler (statische Files aus ~/mac-setup/agent/)
Agent-Subprocess verwendet: /opt/homebrew/bin/python3 (absoluter Pfad wegen LaunchAgent PATH)

## MemPalace (Wissensbasis)
- Installiert: pip3 install mempalace
- Palace: ~/.mempalace/palace/ (ChromaDB backend)
- Knowledge: ~/mac-setup/agent/knowledge/ (decisions.md, incidents.md, performance.md)
- Suchen: mempalace search "deine Frage"
- performance.md enthält "## Aktueller Build-Status" — wird bei jedem Agent-Run überschrieben
- Force-Reindex nötig nach File-Änderungen: python3 chromadb direkt → col.delete(id) + col.add()
- Wing "platform" in ~/.mempalace/config.json nicht registriert (nur Default-Wings drin)

## Sudoers (NOPASSWD)
/etc/sudoers.d/yavuz-platform:
- /usr/sbin/sysctl
- /opt/homebrew/bin/kubectl
- /sbin/ifconfig

## .zshrc Aliases
- ai-llama-fast: Port 8080, turbo4, Speculative Decoding, --metrics, 32k Kontext
- monitoring-start/stop: Prometheus/Grafana/OpenCost

## Bekannte Lösungen & Fallstricke
- localhost ohne WLAN: /etc/hosts mit "127.0.0.1 localhost"
- Loopback nach Neustart: sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255
- git pull Konflikte: git merge --abort && git reset --hard origin/feature/turboquant-kv-cache
- Grafana Passwort reset: kubectl exec -n monitoring deployment/monitoring-grafana -c grafana -- grafana cli admin reset-admin-password NEUESPASSWORT
- sed -i auf macOS: keine unterschiedlich langen Strings möglich → python3 str.replace() verwenden
- LaunchAgent PATH: immer absolute Pfade in Subprocesses verwenden (/opt/homebrew/bin/python3)
- LaunchAgent neu laden: unload + load (bootstrap schlägt oft fehl mit Error 5, ignorieren)
- Port bereits belegt: kill $(lsof -ti:PORT)
- MemPalace "already filed": Force-Reindex via chromadb Python direkt
- Phantom-Commits: SHAs von GitHub API die nicht im Branch existieren → aus intelligence.json entfernen

## Offene TODOs
- [ ] tokens/sec korrekt messen (Metrics Endpoint Fix)
- [ ] RAM-Verlauf Chart im Dashboard
- [ ] Tailscale vollständig einrichten für Handy-Zugang
- [ ] explain()-Antwortqualität: Compile-Befehle statisch hardcoden statt LLM generieren lassen
- [ ] MemPalace Wing "platform" in ~/.mempalace/config.json registrieren
- [ ] Kubernetes Pods Badge zeigt falsche Zahl wenn Docker nicht läuft
