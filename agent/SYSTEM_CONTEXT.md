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
- Letzter kompilierter Commit: 830eb54 (fix: cap map0 kernel shmem)
- Ausstehend: a8de291 (KV-Cache Hardening), c30bc9e (Bounded Queries Fix)

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
- com.yavuz.dashboard → HTTP Server auf localhost:8999

## Agent System
### Platform Agent (7 Nodes, ~/mac-setup/agent/platform_agent.py)
- check_updates: Open WebUI GitHub Release
- check_k8s_health: Pods überwachen, Restarts
- check_llama_server: Watchdog → Incident Agent
- check_system_health: GPU Limit, Disk, Port-Forward
- check_unsloth_models: neue GGUF-Versionen
- check_argocd_and_commits: ArgoCD Sync, TurboQuant Commits
- run_intelligence: Intelligence Agent aufrufen

### Incident Agent (~/mac-setup/agent/incident_agent.py)
- Aktion A (K8s stoppen): DEAKTIVIERT — zu destruktiv
- Aktion C: llama-server neu starten (bevorzugt)
- Fallback: Llama 3.1 8B auf Port 8082
- Max Restarts: 3x pro Stunde
- Startup Lockfile: /tmp/platform-startup.lock

### Intelligence Agent (~/mac-setup/agent/intelligence_agent.py)
Beobachtete Repos:
- TheTom/llama-cpp-turboquant — primär, kompilierbar
- milla-jovovich/mempalace — Memory System
- SharpAI/SwiftLM — Swift Server
- arozanov/turboquant-mlx — MLX Port

Stack-Grenzen: NUR TheTom Commits kompilierbar.
MLX Repos (arozanov, helgklaizar, rachittshah) = anderer Stack.

### Dashboard
- URL: http://localhost:8999/dashboard.html
- Proxy Server: ~/mac-setup/agent/proxy.py
- Zeigt: LLM Status, RAM, Wochenbericht, TurboQuant Commits

## MemPalace (Wissensbasis)
- Installiert: pip3 install mempalace
- Palace: ~/.mempalace/palace/
- Knowledge: ~/mac-setup/agent/knowledge/ (decisions.md, incidents.md, performance.md)
- Suchen: mempalace search "deine Frage"
- Auto-Update: Intelligence Agent updatet nach Wochenbericht

## Sudoers (NOPASSWD)
/etc/sudoers.d/yavuz-platform:
- /usr/sbin/sysctl
- /opt/homebrew/bin/kubectl
- /sbin/ifconfig

## .zshrc Aliases
- ai-llama-fast: Port 8080, turbo4, Speculative Decoding, --metrics, 32k Kontext
- monitoring-start/stop: Prometheus/Grafana/OpenCost

## Bekannte Lösungen
- localhost ohne WLAN: /etc/hosts mit "127.0.0.1 localhost"
- Loopback nach Neustart: sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255
- git pull Konflikte: git merge --abort && git reset --hard origin/feature/turboquant-kv-cache
- Grafana Passwort: kubectl exec -n monitoring deployment/monitoring-grafana -c grafana -- grafana cli admin reset-admin-password NEUESPASSWORT

## Offene TODOs
- [ ] a8de291 + c30bc9e kompilieren (KV-Cache Hardening + Bounded Queries)
- [ ] Agent erkennt automatisch kompilierte Commits (compiled_commits in agent_state.json)
- [ ] tokens/sec korrekt messen (Metrics Endpoint Fix)
- [ ] RAM-Verlauf Chart im Dashboard
- [ ] Tailscale vollständig einrichten für Handy-Zugang
