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
- Aktueller HEAD: 8590cbff9 (Merge PR #62 Vulkan turbo3 + Metal TurboFlash attention kernel)
- Offizieller Release: tqp-v0.1.0 (tag auf eea498c) — TQ4_1S 3.5x faster, AMD RDNA4, Vulkan turbo3

### TurboFlash V4 — NICHT kompilieren (Stand April 2026)
- Commits: 6946763 (TurboFlash V4 SIMD-per-token) + b0b8dde (simd_shuffle_xor WHT pass 2)
- Branch wurde force-pushed mehrfach (zuletzt auf 8590cbff9)
- Problem: kIOGPUCommandBufferCallbackErrorOutOfMemory auf M5 Pro
- Ursache: neue SIMD-per-token Architektur auf M5 Pro noch nicht stabil (nur M5 Max getestet)
- Workaround: git reset --hard 8590cbff9 → zurück auf stabilen Stand
- Beobachten: GitHub Issues zu TurboFlash V4 auf M5 Pro abwarten

#### V4-Hybrid Patch — fehlgeschlagen (2026-04-09)
- Diagnose: Register-Spill durch o_state[DV_PER_LANE] + v_decoded[DV_PER_LANE] in Token-Loop
- Fix-Versuch: o_state + v_decoded von Registern → Shared Memory (1024 Bytes, 2×DV×float)
- Script: ~/mac-setup/apply-v4-hybrid.sh (Commit f471df4b4, Backup: backup/pre-v4-hybrid-20260409-020927)
- Ergebnis: OOM bleibt — Patch hat nicht geholfen
- Fazit: Register-Druck war nicht die einzige Ursache — tieferes M5 Pro Problem
- Rollback: git reset --hard 40b6f96 + cmake neu bauen

### Kompilierte Commits (compiled_commits in agent_state.json)
| SHA | Beschreibung | Status |
|-----|-------------|--------|
| 8590cbff9 | Merge PR #62 Vulkan turbo3 + Metal TurboFlash kernel (aktueller HEAD, STABIL) | ✅ kompiliert |
| 40b6f96 | Merge alpha-scaling | ✅ kompiliert |
| 830eb54 | fix: cap map0 kernel shmem for 256-expert MoE | ✅ kompiliert |
| acad28d | feat: MoE expert count + TQ4_1S backend tests | ✅ kompiliert |
| cffcbf0 | (älterer Commit) | ✅ kompiliert |
| 6946763 | TurboFlash V4 SIMD-per-token | ❌ OOM auf M5 Pro |
| b0b8dde | simd_shuffle_xor WHT pass 2 | ❌ OOM auf M5 Pro |

### Modelle
| Alias | Modell | Größe | Pfad |
|-------|--------|-------|------|
| ai-llama | Llama 3.3 70B Q4_K_M | 40GB | ~/models/llama33-70b-q4km.gguf |
| ai-llama-fast | 70B + 8B Draft (Spec. Decoding) | 40+4.6GB | + ~/models/llama31-8b-draft.gguf |
| ai-gemma | Gemma 4 31B UD-Q4_K_XL | 17GB | ~/models/gemma4-31b/ |
| ai-qwen | Qwen 2.5 72B Q4_K_M | 44GB | ~/models/qwen25-72b/ |
| ai-mistral | Mistral 7B Q4_K_M | 4GB | ~/models/mistral-7b-q4km.gguf |

### Modell-Empfehlung (Stand April 2026)
- Default für Platform Engineering Tasks: ai-gemma (17GB, 141 tok/s Prefill, Qualität ~Llama 70B)
- Heavy Reasoning / komplexe Tasks: ai-llama-fast (40GB, Speculative Decoding)
- Gemma 4 Benchmark vs Llama 70B: Prefill 1.7x schneller, Decode 22% schneller, 2.5x kleiner

### TurboQuant Konfiguration
- Cache: --cache-type-k q8_0 --cache-type-v turbo4 (asymmetrisch — K präzise, V komprimiert)
- Begründung: K-Präzision dominiert Qualität via Softmax, V-Kompression ist "free" (+3% decode speed)
- turbo4: 4.25 bit, 3.8x KV-Cache Kompression, +6.3% PPL-Verlust
- Sparse V: automatisch aktiv ("turbo3 sparse V dequant enabled" beim Start)
- Flash Attention: -fa on
- Kontext: 32768 tokens (32k)
- GPU Offload: -ngl 99

### Speculative Decoding (ai-llama-fast)
- Draft: Llama 3.1 8B, --draft-max 8 --draft-min 2
- Ergebnis: ~10 tok/s, 88% Acceptance Rate
- Draft KV-Cache: --cache-type-k-draft q8_0 --cache-type-v-draft turbo4

### Performance Benchmarks (8590cbff9, asymmetrisch q8_0/turbo4)
- pp512: 108.05 tok/s
- tg128: 6.25 tok/s
- KV-Cache bei 32k: ~2.7GB (turbo4 V) vs ~10.8GB (FP16)

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
- Docker Desktop Memory: 20GB (erhöht am 2026-04-18 für kagent)

## kagent — AI Platform Operator (Phase 0, Stand April 2026)

### Was ist kagent
Kubernetes-nativer AI-Agent-Runtime. CNCF Sandbox Projekt (seit KubeCon EU 2025).
Erstellt von Solo.io. Contributors: Google, Red Hat, IBM, Microsoft, SAP, Amazon.
Lizenz: Apache 2.0 — kostenlos auch für Konzerne, kein Vendor Lock-in.

### Architektur (Lokal)
```
Nutzer (Dashboard / CLI)
        ↓
LangGraph Agent (platform_agent_lg.py) — Orchestration / Intent Router
        ↓
kagent Runtime — K8s-nativ, CRDs, Controller
        ↓
MCP Tool Servers — kubectl, Helm, Argo, Prometheus, Grafana
        ↓
Kubernetes Cluster (Docker Desktop lokal)
```

### Installation (lokal, Stand April 2026)
```bash
# CLI installieren
brew install kagent  # Version 0.8.6

# CRDs installieren
helm install kagent-crds \
  oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds \
  --namespace kagent --create-namespace

# kagent installieren mit Ollama
helm install kagent \
  oci://ghcr.io/kagent-dev/kagent/helm/kagent \
  --namespace kagent \
  --set providers.default=ollama \
  --set providers.ollama.baseUrl=http://host.docker.internal:11434 \
  --set providers.ollama.model=gemma3:27b
```

Wichtig: `helm repo add kagent https://kagent-dev.github.io/kagent` funktioniert NICHT (404).
Immer OCI Registry verwenden: `oci://ghcr.io/kagent-dev/kagent/helm/...`

### LLM Provider
- Lokal: Ollama + Gemma 4 31B (gemma3:27b in Ollama)
- Ollama läuft auf Port 11434
- kagent verbindet via `host.docker.internal:11434` (Docker Desktop Bridge)
- kagent erkennt automatisch die Ollama ModelConfig beim Start

### Bekannte Probleme & Lösungen
- `--set` Flag: kagent CLI unterstützt kein `--set` → Helm direkt verwenden
- ImagePullBackOff `unexpected EOF`: Netzwerkfehler → `docker pull IMAGE` dann Pods neu starten
- `Insufficient memory`: Docker Desktop Memory zu niedrig → auf 20GB erhöht
- Demo-Profil startet zu viele Agents → RAM-Überlastung → unnötige Agents löschen:
  `kubectl -n kagent delete agent cilium-debug-agent cilium-manager-agent ...`
- Tool Server API Version: `v1alpha2` nicht `v1alpha1`
- RemoteMCPServer spec hat kein `spec.config` → ursprüngliche Helm-Resource verwenden

### Pods (minimales Setup, Stand April 2026)
```
kagent-controller        1/1 Running  — Kubernetes Controller
kagent-postgresql        1/1 Running  — State / Session Storage
kagent-ui                1/1 Running  — Web Dashboard
kagent-tools             1/1 Running  — Built-in MCP Tool Server
kagent-grafana-mcp       1/1 Running  — Grafana MCP Integration
kagent-kmcp-controller   1/1 Running  — MCP Controller
kagent-querydoc          1/1 Running  — Documentation Agent
k8s-agent                1/1 Running  — Kubernetes Expert Agent
```

### Dashboard
```bash
kagent dashboard
# → http://localhost:8082
# oder:
kubectl -n kagent port-forward svc/kagent-ui 8080:8080
# → http://localhost:8080
```

### Tool Server (bereits von Helm erstellt)
Name: `kagent-tool-server` (RemoteMCPServer, v1alpha2)
URL: `http://kagent-tools.kagent:8084/mcp`
Tools: 100+ Tools für kubectl, Helm, Argo, Cilium, Istio, Prometheus, Grafana

Wichtig: Helm erstellt `kagent-tool-server` automatisch als RemoteMCPServer.
NICHT manuell neu anlegen — Konflikte durch `spec.config` vs. `spec.url` Struktur.

### Built-in Agents (demo Profil — zu viele für lokalen Cluster)
Für Phase 0 nur behalten:
- `k8s-agent` — kubectl, describe, logs, scale, rollout
- `observability-agent` — Prometheus + Grafana
- `promql-agent` — PromQL aus natürlicher Sprache generieren

Rest löschen um RAM zu sparen:
```bash
kubectl -n kagent delete agent \
  cilium-debug-agent cilium-manager-agent cilium-policy-agent \
  helm-agent istio-agent kgateway-agent observability-agent \
  promql-agent argo-rollouts-conversion-agent
```

### CRD Übersicht
```
agents.kagent.dev           — Agent Definitionen
mcpservers.kagent.dev       — MCP Server
memories.kagent.dev         — Agent Memory
modelconfigs.kagent.dev     — LLM Provider Configs
modelproviderconfigs.kagent.dev
remotemcpservers.kagent.dev — Remote MCP Server (v1alpha2)
toolservers.kagent.dev      — Tool Server
```

### Nächste Schritte kagent (Phase 1)
- [ ] k8s-agent Tools validieren — Agent soll kubectl wirklich ausführen, nicht nur erklären
- [ ] LangGraph als Runtime in kagent deployen (platform_agent_lg.py als kagent Agent)
- [ ] Intent Router bauen (cluster_info → k8s-agent, metrics → observability-agent)
- [ ] Human-in-the-loop für destruktive Aktionen (delete, scale down)
- [ ] Approval Flow: dry-run → confirm → execute
- [ ] Teams/Slack Bot Interface (Phase 4)
- [ ] ROSA-Delta dokumentieren (Lokal vs. ROSA Unterschiede)

### ROSA-Delta (Lokal → ROSA)
| Komponente | Lokal | ROSA |
|---|---|---|
| LLM | Ollama (gemma3:27b) | Azure OpenAI / Anthropic API |
| RBAC | K8s RBAC | ROSA RBAC + Entra ID |
| Policy | Kyverno | OPA Gatekeeper |
| Audit | OTel lokal | OTel → Splunk |
| Ingress | NGINX | AWS ALB / ROSA Router |
| Secrets | K8s Secrets | AWS Secrets Manager |
| mTLS | Standard | OSSM (bereits aktiv auf ROSA) |
| Multi-Tenant | Namespace-basiert | PSF-Modell |

### Warum kagent (Entscheidungsbegründung)
- CNCF Sandbox → Procurement-fähig für Audi AG
- Red Hat ist Contributor → ROSA-Nähe
- Apache 2.0 → 0€ Lizenz, kein Vendor Lock-in
- LangGraph nativ unterstützt → platform_agent_lg.py direkt deploybar
- Built-in Tools für gesamten Stack (kubectl, Helm, Argo, Prometheus, Grafana)
- Alternative zu Kubiya ohne Vendor-Risiko ($12M Seed-Startup)
- Solo Enterprise optional für Enterprise-Governance (mTLS, OIDC, Agent Identity)
  → bei Audi nicht nötig: OSSM für mTLS, Splunk für Audit, ROSA RBAC für Identity

## Observability Stack

### Säulen-Status
| Säule | Tool | Status |
|-------|------|--------|
| Metrics | Prometheus + Grafana | ✅ aktiv, eigene Rules deployed |
| Logging | Loki + Promtail | ✅ aktiv, Datasource in Grafana verbunden |
| Tracing | Langfuse (installiert) | ⏳ blockiert durch Python 3.14 Inkompatibilität |

### Prometheus
- Stack: kube-prometheus-stack (21d, namespace: monitoring)
- Scrape Interval: 15s (default)
- Zugriff: kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
- PrometheusRule Selector: matchLabels: release: monitoring
  → Alle eigenen Rules MÜSSEN dieses Label haben sonst werden sie ignoriert

### Eigene PrometheusRules
Datei: ~/mac-setup/charts/tenant-quota-alerts.yaml

| Rule | Expr | For | Severity |
|------|------|-----|----------|
| TenantCPUQuotaNearLimit | CPU Usage / CPU Quota Limit > 0.8 per namespace | 15m | warning |

Wichtig: kube_resourcequota{type="hard", resource="limits.cpu"} heißt korrekt
kube_resourcequota{type="hard", resource="limits.cpu"} — NICHT kube_resourcequota_limit_cpu

Deployen: kubectl apply -f ~/mac-setup/charts/tenant-quota-alerts.yaml
Prüfen: kubectl get prometheusrule -n monitoring tenant-quota-alerts

### AlertManager
- Konfiguration: via Kubernetes Secret (direkt, nicht via Helm wegen PVC-Konflikt)
- Secret Name: alertmanager-monitoring-kube-prometheus-alertmanager
- Konfiguration updaten:
  kubectl create secret generic alertmanager-monitoring-kube-prometheus-alertmanager \
    -n monitoring \
    --from-literal=alertmanager.yaml='...' \
    --dry-run=client -o yaml | kubectl apply -f -
- AlertManager UI: kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-alertmanager 9093:9093 → http://localhost:9093
- Aktueller Receiver: webhook-test → https://webhook.site/db9c390d-4f07-421c-a3c7-7a6a0043c6d1
- Config:
  route:
    receiver: "webhook-test"
    group_wait: 30s
    group_interval: 5m
    repeat_interval: 1h
- Fallstrick: Helm upgrade schlägt wegen PVC Field Manager Konflikt fehl → Secret-Methode verwenden
- Professioneller Weg: AlertManager von Anfang an in values.yaml definieren, dann kein Konflikt

### Helm values — kube-prometheus-stack
Datei: ~/mac-setup/charts/kube-prometheus-stack-values.yaml
Enthält: Grafana persistence, Prometheus storage, AlertManager webhook config
Deployen: helm upgrade monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring -f charts/kube-prometheus-stack-values.yaml

### Grafana
- URL: http://grafana.local
- Login: admin / newpassword123
- Datasources: Prometheus (default), Loki
- Dashboards: Platform Tenant Overview (eigenes), diverse kube-prometheus defaults

### Loki
- Stack: loki-stack (namespace: monitoring)
- Datasource URL: http://loki.monitoring.svc.cluster.local:3100 (NICHT nur http://loki:3100)
- image.tag: 2.9.0 (loki-stack 2.6.1 inkompatibel mit neuem Grafana → manuell gesetzt)

### Nützliche PromQL Queries
- CPU Usage per Namespace: sum by (namespace) (rate(container_cpu_usage_seconds_total[5m]))
- Memory Usage per Pod: container_memory_working_set_bytes{container!=""}
- P99 Latenz: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))
- Metriken erkunden: Prometheus UI Autocomplete oder helm show values / kube-state-metrics Doku

### Helm Best Practices (gelernt)
- Vor Installation: helm show values CHART | grep -A 5 "feature:" — Optionen verstehen
- Immer vollständige values.yaml von Anfang an — nie nachträglich erweitern
- Vor Upgrade: helm upgrade --dry-run — Fehler vorher sehen
- Alle values.yaml ins Git: ~/mac-setup/charts/

### Nächste Schritte Observability
- [ ] AlertManager Routing — verschiedene Alerts zu verschiedenen Receivern (critical vs warning)
- [ ] Eigene Application Metrics aus Platform Agent exposen (prometheus_client, Port 9090)
- [ ] Grafana Tempo für Tracing (OpenTelemetry SDK in Platform Agent)
- [ ] Langfuse Tracing aktivieren sobald Python 3.14 supportet wird

## LaunchAgents (automatischer Start)
- com.yavuz.platform-agent → stündlicher Health Check (startet startup.sh)
- com.yavuz.startup-terminal → Terminal mit Live-Log beim Login
- com.yavuz.port-forward → Port-Forward dauerhaft auf localhost:3000
- com.yavuz.dashboard → HTTP Server + Proxy auf localhost:8999

### startup.sh (~/mac-setup/scripts/startup.sh)
- Startet beim Login: Loopback Alias, GPU Limit, K8s Pods, Platform Agent einmalig
- Agent-Aufruf: /opt/homebrew/bin/python3 ~/mac-setup/agent/platform_agent_lg.py
- WICHTIG: War zuvor platform_agent.py (alter Agent mit aktivem LLM-Call) → verursachte RAM-Spike auf 60GB
- Fix: 2026-04-13, Commit d8e6854

## Agent System

### Platform Agent — LangGraph (~/mac-setup/agent/platform_agent_lg.py)
Ersetzt: platform_agent.py + incident_agent.py
Framework: LangGraph StateGraph mit SqliteSaver Checkpointer

Graph-Nodes (in Reihenfolge):
- check_k8s: Pod-Status, Restart-Counts (Threshold: >100 Restarts = Issue)
- check_llama: Watchdog Port 8080, alive/tok/s, Restart-Counter
- incident: Entscheidungsnode wenn llama down (→ restart / fallback / give_up)
- do_restart: llama-server neu starten, max 3x/h
- do_fallback: Llama 3.1 8B auf Port 8082
- check_updates: Open WebUI GitHub Release
- check_unsloth: neue GGUF-Modelle HuggingFace
- check_system: GPU Limit, Disk, Build-SHA auto-detect, Port-Forward
- run_intelligence: DEAKTIVIERT — gibt {"skipped": True} zurück, kein LLM-Call
- update_mempalace: incidents.md updaten, mempalace index
- build_report: Markdown-Report → agent_state.json

State: PlatformState TypedDict (kein manuelles JSON im Agent-Code)
Checkpointer: SqliteSaver → ~/mac-setup/agent/checkpoint.db
Log: ~/mac-setup/agent/platform_agent.log (tail -f zum Live-Verfolgen)

### Build-Commit Auto-Detection (in check_system)
- Liest bei jedem Run: git -C ~/llama-cpp-turboquant rev-parse HEAD
- Schreibt HEAD automatisch in compiled_commits + compiled_sha in agent_state.json
- Aktualisiert performance.md mit "## Aktueller Build-Status" Block
- Kein manueller Eingriff nötig nach git pull + cmake

### Incident Agent — integriert in LangGraph
- Aktion A (K8s stoppen): DEAKTIVIERT — zu destruktiv
- Aktion C: llama-server neu starten (bevorzugt)
- Fallback: Llama 3.1 8B auf Port 8082
- Max Restarts: 3x pro Stunde (über restart_history im State)
- Startup Lockfile: /tmp/platform-startup.lock

### Intelligence Agent (~/mac-setup/agent/intelligence_agent.py)
- Status: DEAKTIVIERT — node_run_intelligence gibt früh {"skipped": True} zurück
- Kein LLM-Call mehr, weder manuell noch stündlich
- Code bleibt erhalten, kann jederzeit reaktiviert werden

### Dashboard (~/mac-setup/agent/dashboard.html)
- URL: http://localhost:8999/dashboard.html
- Proxy: ~/mac-setup/agent/proxy.py (Port 8999)
- Run Agent Button: POST /run-agent → startet platform_agent_lg.py als Subprocess
- "Wie kompiliere ich das?" Button: DEAKTIVIERT (style="display:none")
- compiled_commits Array-Check: zeigt ✅ kompiliert für alle bekannten SHAs
- Aktionen-Zähler: zählt nur echte Agent-Aktionen

### Proxy (~/mac-setup/agent/proxy.py)
Endpoints:
- POST /llm → leitet zu localhost:8080/v1/chat/completions (timeout 120s)
- POST /run-agent → startet platform_agent_lg.py im Hintergrund
- GET /agent-status → {running: bool, pid: int}
- GET /* → SimpleHTTPRequestHandler (statische Files aus ~/mac-setup/agent/)
Agent-Subprocess verwendet: /opt/homebrew/bin/python3 (absoluter Pfad wegen LaunchAgent PATH)

## Langfuse (Tracing — teilweise)
- Docker Compose: ~/mac-setup/langfuse/docker-compose.yml
- URL: http://localhost:3001
- Status: läuft, aber Tracing nicht aktiv
- Problem: langfuse Python Package v4 inkompatibel mit Python 3.14
- Workaround: abwarten bis langfuse Python 3.14 supportet
- Starten: cd ~/mac-setup/langfuse && docker compose up -d

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
- ai-llama: Port 8080, q8_0/turbo4 asymmetrisch, 32k Kontext
- ai-llama-fast: Port 8080, q8_0/turbo4 asymmetrisch, Speculative Decoding, --metrics, 32k Kontext
- ai-gemma: Port 8080, turbo4/turbo4, 32k Kontext (Default-Modell für alltägliche Tasks)
- monitoring-start/stop: Prometheus/Grafana/OpenCost
- Langfuse Umgebungsvariablen: LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

## Bekannte Lösungen & Fallstricke
- localhost ohne WLAN: /etc/hosts mit "127.0.0.1 localhost"
- Loopback nach Neustart: sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255
- git pull Konflikte: git merge --abort && git reset --hard origin/feature/turboquant-kv-cache
- Branch force-pushed: git merge schlägt fehl → git merge --abort && git reset --hard origin/...
- Grafana Passwort reset: kubectl exec -n monitoring deployment/monitoring-grafana -c grafana -- grafana cli admin reset-admin-password NEUESPASSWORT
- sed -i auf macOS: keine unterschiedlich langen Strings möglich → python3 str.replace() verwenden
- LaunchAgent PATH: immer absolute Pfade in Subprocesses verwenden (/opt/homebrew/bin/python3)
- LaunchAgent neu laden: unload + load (bootstrap schlägt oft fehl mit Error 5, ignorieren)
- Port bereits belegt: kill $(lsof -ti:PORT)
- MemPalace "already filed": Force-Reindex via chromadb Python direkt
- SHA nicht lokal gefunden: erst git fetch --all — Branch könnte force-pushed worden sein
- TurboFlash V4 OOM: git reset --hard 8590cbff9 + cmake neu bauen
- cmake baut nicht neu nach git reset: cmake --build build --config Release -j... --clean-first
- K8s Restart-Threshold: >100 Restarts = Issue (Docker Desktop akkumuliert Restarts bei jedem Neustart)
- LangGraph SqliteSaver: SqliteSaver(conn) mit sqlite3.connect(..., check_same_thread=False)
- Langfuse Helm Chart v3+: braucht salt.value, nextauth.secret.value, encryption.key.value (verschachtelt)
- Langfuse Python v4: kein .trace(), kein CallbackHandler — inkompatibel mit Python 3.14
- Grafana PromQL Division: immer sum by (namespace) verwenden — Extra-Labels verhindern sonst Division
- PrometheusRule wird nicht geladen: Label release: monitoring fehlt → kubectl get prometheusrule prüfen
- Grafana Dashboard verloren: unsaved State geht bei Navigation verloren → sofort nach Erstellen speichern
- AlertManager Helm Upgrade fehlgeschlagen: PVC Field Manager Konflikt → Secret direkt patchen
- Loki health check failed (parse error): loki-stack 2.6.1 inkompatibel mit neuem Grafana → image.tag: 2.9.0
- Loki Datasource URL: http://loki:3100 reicht nicht → http://loki.monitoring.svc.cluster.local:3100
- startup.sh startet alten platform_agent.py → RAM-Spike 60GB: sed -i '' 's/platform_agent\.py/platform_agent_lg.py/g' ~/mac-setup/scripts/startup.sh
- kagent Helm Repo: helm repo add funktioniert NICHT → OCI Registry verwenden
- kagent ImagePullBackOff: docker pull IMAGE dann kubectl rollout restart deployment
- kagent Demo-Profil: zu viele Agents → RAM-Überlastung → unnötige Agents löschen
- kagent Tool Server: Helm erstellt automatisch kagent-tool-server als RemoteMCPServer
- kagent API Version: immer v1alpha2 für RemoteMCPServer und Agent CRDs
- kagent CLI --set: wird NICHT unterstützt → helm direkt mit --set verwenden
- Docker Desktop Memory für kagent: mindestens 20GB (Gemma 27B + kagent Pods)

## Offene TODOs
- [ ] tokens/sec korrekt messen (Metrics Endpoint Fix)
- [ ] RAM-Verlauf Chart im Dashboard
- [ ] Tailscale vollständig einrichten für Handy-Zugang
- [ ] MemPalace Wing "platform" in ~/.mempalace/config.json registrieren
- [ ] Kubernetes Pods Badge zeigt falsche Zahl wenn Docker nicht läuft
- [ ] Langfuse Tracing aktivieren sobald Python 3.14 supportet wird
- [ ] TurboFlash V4 nochmal testen wenn M5 Pro Fix von TheTom kommt
- [ ] AlertManager Routing konfigurieren (critical vs warning → verschiedene Receiver)
- [ ] Eigene Metriken aus Platform Agent exposen (prometheus_client, Port 9090)
- [ ] Grafana Tempo für Tracing einrichten (OpenTelemetry SDK)
- [ ] kagent Phase 1: LangGraph als Runtime in kagent deployen
- [ ] kagent Phase 1: Intent Router bauen
- [ ] kagent Phase 1: Human-in-the-loop für destruktive Aktionen
- [ ] kagent Phase 2: RBAC Rollen definieren (viewer/operator/deployer/admin)
- [ ] kagent Phase 3: Prometheus + Grafana MCP vollständig konfigurieren
- [ ] kagent Phase 4: Teams/Slack Bot Interface
- [ ] kagent Phase 5: ROSA-Deployment + Entra ID + OPA Gatekeeper
- [ ] Blueprint ins Git pushen (~/mac-setup/)
- [ ] SYSTEM_CONTEXT.md ins Git pushen (~/mac-setup/)
