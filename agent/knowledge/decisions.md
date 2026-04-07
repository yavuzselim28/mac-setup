# Platform Decisions — Yavuz Topcu (Audi AG Platform Engineer)

## Hardware
- MacBook Pro M5 Pro, 64GB Unified Memory, 1TB SSD
- Apple Silicon GPU (Metal/Clang — NICHT GCC)
- GPU Memory Limit: sudo sysctl iogpu.wired_limit_mb=52429 (52429 = ~90% von 64GB)

## LLM Stack Entscheidungen

### Modelle
- Hauptmodell: Llama 3.3 70B Q4_K_M (Unsloth) — 40GB, ~/models/llama33-70b-q4km.gguf
- Draft-Modell: Llama 3.1 8B Q4_K_M — 4.6GB, ~/models/llama31-8b-draft.gguf
- Gemma 4 31B UD-Q4_K_XL — 17GB, ~/models/gemma4-31b/
- Qwen 2.5 72B Q4_K_M — 44GB, ~/models/qwen25-72b/
- Mistral 7B Q4_K_M — 4GB, ~/models/mistral-7b-q4km.gguf

### TurboQuant Konfiguration
- ENTSCHEIDUNG: turbo4 (nicht turbo3) für 70B Q4_K_M
  - turbo4: +6.3% PPL-Verlust, 3.8x KV-Cache Kompression
  - turbo3: +11.4% PPL-Verlust, 4.6-5.1x Kompression
  - Begründung: bessere Qualität wichtiger als maximale Kompression
- Cache: --cache-type-k turbo4 --cache-type-v turbo4
- Sparse V: automatisch aktiv in neuestem Build (turbo3 sparse V dequant enabled)

### Speculative Decoding
- ENTSCHEIDUNG: aktiviert mit Llama 3.1 8B als Draft
- Ergebnis: ~10 tok/s, 88% Acceptance Rate
- Flags: --draft-max 8 --draft-min 2
- Draft KV-Cache: auch turbo4

### Kontext
- ENTSCHEIDUNG: 32768 tokens (32k) — mit turbo4 + 64GB machbar
- KV-Cache Größe bei 32k mit turbo4: ~2.7GB statt ~10.8GB bei FP16

### Flash Attention
- ENTSCHEIDUNG: aktiviert (-fa on)

### llama-server starten
- ENTSCHEIDUNG: manuell per `ai-llama-fast` — NICHT automatisch beim Boot
- Begründung: RAM-Konflikte beim Startup wenn K8s und Docker noch laden
- Wartezeit vor Start: 60 Sekunden nach K8s bereit

## Infrastruktur Entscheidungen

### Kubernetes
- Docker Desktop local, namespace: ollama
- Deployments: ollama-app-ollama, ollama-app-open-webui
- ArgoCD GitOps: yavuzselim28/mac-setup

### Networking
- Loopback Alias: 10.254.254.254 (funktioniert ohne WLAN)
- Open WebUI URL: http://10.254.254.254:8080/v1
- Port-Forward: localhost:3000 → Open WebUI (--address 0.0.0.0 für Tailscale)
- Tailscale IP: 100.78.80.6

### LaunchAgents
- com.yavuz.platform-agent: stündlicher Health Check
- com.yavuz.startup-terminal: Terminal mit Live-Log beim Login
- com.yavuz.port-forward: Port-Forward dauerhaft auf 3000
- com.yavuz.dashboard: HTTP Server auf 8999

## Agent System Entscheidungen

### Platform Agent (7 Nodes)
- check_updates: Open WebUI GitHub Release
- classify_and_decide: LLM klassifiziert PATCH/MINOR/MAJOR
- check_k8s_health: crashende Pods neu starten
- check_llama_server: Watchdog → Incident Agent bei Crash
- check_system_health: GPU Limit, Disk, Port-Forward
- check_unsloth_models: HF API neue GGUF-Versionen
- run_intelligence: Intelligence Agent aufrufen

### Incident Agent
- ENTSCHEIDUNG: Aktion A (K8s stoppen) DEAKTIVIERT — zu destruktiv
- Fallback: Llama 3.1 8B auf Port 8082 wenn 70B down
- Max Restarts: 3x pro Stunde
- Startup Lockfile: /tmp/platform-startup.lock

### Intelligence Agent (4 beobachtete Repos)
- TheTom/llama-cpp-turboquant (feature/turboquant-kv-cache) — primär
- milla-jovovich/mempalace — Memory System, beobachten
- SharpAI/SwiftLM — Swift Server mit TurboQuant
- arozanov/turboquant-mlx — MLX Port

### Stack-Grenzen
- NUR TheTom/llama-cpp-turboquant Commits können kompiliert werden
- MLX Repos (arozanov, helgklaizar, rachittshah, SharpAI) = anderer Stack, nicht kompilierbar
- Kompilierung: cd ~/llama-cpp-turboquant && cmake --build build --config Release -j$(sysctl -n hw.logicalcpu)
