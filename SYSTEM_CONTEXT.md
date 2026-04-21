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
- Problem: kIOGPUCommandBufferCallbackErrorOutOfMemory auf M5 Pro
- Workaround: git reset --hard 8590cbff9 → zurück auf stabilen Stand

#### V4-Hybrid Patch — fehlgeschlagen (2026-04-09)
- Ergebnis: OOM bleibt — Rollback: git reset --hard 40b6f96 + cmake neu bauen

### Kompilierte Commits
| SHA | Beschreibung | Status |
|-----|-------------|--------|
| 8590cbff9 | Merge PR #62 Vulkan turbo3 + Metal TurboFlash kernel (STABIL) | ✅ |
| 40b6f96 | Merge alpha-scaling | ✅ |
| 830eb54 | fix: cap map0 kernel shmem | ✅ |
| acad28d | feat: MoE expert count | ✅ |
| 6946763 | TurboFlash V4 SIMD-per-token | ❌ OOM |
| b0b8dde | simd_shuffle_xor WHT pass 2 | ❌ OOM |

### Modelle (llama.cpp TurboQuant)
| Alias | Modell | Größe | Pfad |
|-------|--------|-------|------|
| ai-llama | Llama 3.3 70B Q4_K_M | 40GB | ~/models/llama33-70b-q4km.gguf |
| ai-llama-fast | 70B + 8B Draft | 40+4.6GB | + ~/models/llama31-8b-draft.gguf |
| ai-gemma | Gemma 4 31B UD-Q4_K_XL | 17GB | ~/models/gemma4-31b/ |
| ai-qwen | Qwen 2.5 72B Q4_K_M | 44GB | ~/models/qwen25-72b/ |
| ai-mistral | Mistral 7B Q4_K_M | 4GB | ~/models/mistral-7b-q4km.gguf |

### Modell-Empfehlung
- Default für Platform Engineering Tasks: ai-gemma (17GB, 141 tok/s Prefill)
- Heavy Reasoning: ai-llama-fast (40GB, Speculative Decoding)
- Für kagent: Ollama verwenden (nicht llama.cpp) — Tool Use funktioniert nur mit Ollama
- Für HolmesGPT: Gemma 4 via llama.cpp (Port 8080) ✅

## HolmesGPT — K8s Diagnose Tool (Stand April 2026)

### Was ist HolmesGPT
CLI-Tool für Kubernetes Root Cause Analysis. Nur Diagnose, keine Aktionen.
Installiert via: brew install holmesgpt (v0.24.4)

### Arbeitsteilung
| Tool | Use Case |
|------|----------|
| HolmesGPT | "Warum crasht Pod X?" / Root Cause Analysis |
| kagent k8s-agent | "Lege Namespace Y an" / Aktionen |
| kagent release-agent | "Was ändert sich in Version Z?" |

### Konfiguration
- Config: ~/.holmes/config.yaml
```yaml
model: "openai/gemma"
api_key: "dummy"
api_base: "http://localhost:8080/v1"
max_steps: 10
```
- Wichtig: llama-server muss laufen (ai-gemma alias) bevor Holmes gestartet wird
- Wichtig: Holmes immer aus ~ starten (nicht aus llama-cpp-turboquant/) — sonst liest kubernetes_tabular_query lokale Dateien

### Aliases (.zshrc)
```bash
alias h="cd ~ && holmes ask --fast-mode"
alias holmes="cd ~ && holmes ask --fast-mode"
```

### Getestet ✅ (2026-04-21)
- "welches ist der pod mit den meisten restarts?" → korrekte Antwort, 2-5 Tool Calls
- Gemma denkt laut mit (Reasoning sichtbar im Output)

### Bekannte Probleme
- Ollama + Holmes → Infinite Loop / raw JSON Output — NICHT verwenden
- Holmes mit Ollama qwen2.5:14b: "could not find tool respond" Bug in LiteLLM
- Holmes mit Ollama qwen2.5:32b: OOM durch RAM-Druck (32b + 14b gleichzeitig geladen)
- kubernetes_tabular_query liest lokale Dateien wenn Holmes aus falschem Verzeichnis gestartet → cd ~ fix
- HolmesGPT ist read-only — kann keine K8s Ressourcen erstellen/ändern

### TurboQuant Konfiguration
- Cache: --cache-type-k q8_0 --cache-type-v turbo4 (asymmetrisch)
- Kontext: 49152 tokens (48k) — erhöht am 2026-04-18 (131k/65k = OOM Segfault)
- GPU Offload: -ngl 99, Flash Attention: -fa on

### Ollama (für kagent)
- Installiert: brew install ollama (Version 0.21.0)
- Starten: OLLAMA_CONTEXT_LENGTH=65536 ollama serve &
- Port: 11434
- Modelle:
  | Modell | Größe | Verwendung |
  |--------|-------|------------|
  | llama3.1:8b | 4.9GB | Backup / schnelle Tests |
  | qwen2.5:14b | 9GB | kagent Standard (gut) |
  | qwen2.5:32b | 19GB | kagent Default (beste Qualität) |
- Wichtig: OLLAMA_CONTEXT_LENGTH=65536 — kagent sendet sehr lange System Prompts
- llama.cpp (Port 8080) und Ollama (Port 11434) laufen parallel

## Netzwerk
- Loopback Alias: 10.254.254.254
- Open WebUI URL in K8s: http://10.254.254.254:8080/v1
- Port-Forward: localhost:3000 → Open WebUI
- llama-server: MANUELL starten (NICHT automatisch)

## Kubernetes Infrastruktur
- Docker Desktop local, namespace: ollama
- Monitoring: kube-prometheus-stack (Grafana: grafana.local, admin/newpassword123)
- ArgoCD GitOps: yavuzselim28/mac-setup
- Helm Charts: ~/mac-setup/charts/
- Docker Desktop Memory: 20GB (erhöht 2026-04-18 für kagent)

## kagent — AI Platform Operator (Phase 0 ✅, Stand April 2026)

### Was ist kagent
Kubernetes-nativer AI-Agent-Runtime. CNCF Sandbox (KubeCon EU 2025).
Solo.io. Contributors: Google, Red Hat, IBM, Microsoft, SAP, Amazon.
Lizenz: Apache 2.0 — kostenlos, kein Vendor Lock-in.

### Architektur
```
Nutzer → LangGraph (Orchestration) → kagent Runtime → MCP Tools → K8s Cluster
```

### Installation
```bash
brew install kagent  # v0.8.6
helm install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds -n kagent --create-namespace
helm install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent -n kagent \
  --set providers.default=ollama \
  --set providers.ollama.baseUrl=http://host.docker.internal:11434 \
  --set providers.ollama.model=qwen2.5:32b
```
Wichtig: helm repo add funktioniert NICHT → immer OCI Registry

### LLM Provider (aktiv)
```bash
kubectl -n kagent patch modelconfig default-model-config --type=merge -p '{
  "spec": {
    "model": "qwen2.5:32b",
    "provider": "Ollama",
    "ollama": {"host": "http://host.docker.internal:11434"}
  }
}'
```

### Modell-Vergleich für kagent
| Modell | Tool Use | Reasoning | Speed |
|--------|----------|-----------|-------|
| llama3.1:8b | ✅ | Schwach | Schnell |
| qwen2.5:14b | ✅✅ | Gut | Mittel |
| qwen2.5:32b | ✅✅✅ | Excellent | ~2min |
| Gemma 4 (llama.cpp) | ❌ | Gut | - |

### Aktive Pods
```
kagent-controller, kagent-postgresql, kagent-ui, kagent-tools
kagent-grafana-mcp, kagent-kmcp-controller, kagent-querydoc
k8s-agent, release-agent
```

### Dashboard
```bash
kagent dashboard  # → http://localhost:8082
```

### Aktive Agents

#### k8s-agent
- Tools: k8s_get_resources, k8s_get_pod_logs, k8s_describe_resource, k8s_get_events, k8s_get_available_api_resources
- Wichtig: Nur 5 Tools (nicht 100+) — sonst Context Overflow (239k Tokens)
- Getestet: Multi-Namespace Analyse, CrashLoopBackOff Root Cause ✅

#### release-agent
- Tools: k8s_get_resources, k8s_get_cluster_configuration, http_get, fetch_release_notes
- http-fetch-mcp als zweiter Tool Server verbunden ✅
- Kann echte Release Notes von GitHub/Red Hat fetchen ✅
- System Prompt Lessons Learned:
  - K8s CHANGELOG hat KEINE "Breaking Changes" Sektion → suche nach "Urgent Upgrade Notes", "Deprecations", "API Changes", "Removals"
  - type Parameter IMMER lowercase (kubernetes/openshift) — qwen schreibt sonst "Kubernetes" → falsche Branch
  - NIEMALS nach Bestätigung fragen → sofort Tools ausführen
  - fetch_release_notes hat enum für type → verhindert Case-Fehler nach Fix

### Tool Server

#### kagent-tool-server (Helm, automatisch)
- RemoteMCPServer v1alpha2, URL: http://kagent-tools.kagent:8084/mcp
- 100+ Tools — NICHT manuell neu anlegen

#### http-fetch-mcp ✅ (deployed, Stand April 2026)
- Tools: http_get, fetch_release_notes
- Code: ~/mac-setup/kagent/http-fetch-mcp/server.py
- Port: 8085 (nicht 8080!)
- Transport: StreamableHTTP (/mcp endpoint) — NICHT SSE (/sse)
- URL: http://http-fetch-mcp.kagent.svc.cluster.local:8085/mcp
- imagePullPolicy: IfNotPresent (nicht Never!)
- Status: discovered tools = http_get, fetch_release_notes ✅
- Deploy: docker build -t http-fetch-mcp:latest . && kubectl rollout restart
- Wichtig: k8s.yaml RemoteMCPServer nutzt spec.url direkt (NICHT spec.config)
- MCP Framework: StreamableHTTPSessionManager(app=server, stateless=True)

### MCP Server bauen — Struktur (StreamableHTTP)
```python
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import Response
import uvicorn, contextlib

server = Server("name")

@server.list_tools()
async def list_tools():
    return [Tool(name="...", description="...", inputSchema={...})]

@server.call_tool()
async def call_tool(name, arguments):
    return [TextContent(type="text", text=result)]

session_manager = StreamableHTTPSessionManager(app=server, stateless=True)

@contextlib.asynccontextmanager
async def lifespan(app):
    async with session_manager.run():
        yield

starlette_app = Starlette(
    lifespan=lifespan,
    routes=[
        Mount("/mcp", app=session_manager.handle_request),
        Route("/health", endpoint=lambda r: Response("ok")),
    ]
)

if __name__ == "__main__":
    uvicorn.run(starlette_app, host="0.0.0.0", port=8085)
```
Wichtig:
- Transport: StreamableHTTP (nicht SSE) — kagent nutzt POST/DELETE auf /mcp
- RemoteMCPServer spec.url direkt (nicht spec.config)
- stateless=True für einfache Server ohne Session-State
- imagePullPolicy: IfNotPresent (nicht Never) für lokale Images

### Phase 0 Ergebnisse ✅ (2026-04-18/19)
- kagent installiert und stabil
- qwen2.5:32b via Ollama als LLM
- k8s-agent: Multi-Namespace Analyse, Root Cause Analysis ✅
- release-agent: Version Check, Upgrade-Empfehlung, Breaking Changes ✅
- Human-in-the-loop funktioniert ✅
- ArgoCD CrashLoop Root Cause korrekt: fehlendes ApplicationSet CRD ✅

### ROSA-Delta
| Komponente | Lokal | ROSA |
|---|---|---|
| LLM | Ollama qwen2.5:32b | Azure OpenAI |
| RBAC | K8s RBAC | ROSA + Entra ID |
| Policy | Kyverno | OPA Gatekeeper |
| Audit | OTel lokal | OTel → Splunk |
| mTLS | Standard | OSSM (aktiv) |

### Bekannte Probleme kagent
- helm repo add → NICHT funktioniert → OCI Registry
- ImagePullBackOff → docker pull dann rollout restart
- Demo-Profil → zu viele Agents → löschen
- API Version → immer v1alpha2
- Context Overflow → max 5 Tools pro Agent
- Ollama truncation → OLLAMA_CONTEXT_LENGTH=65536
- shell Tool kein curl → http-fetch-mcp verwenden
- OOM llama.cpp + Docker 20GB → Ollama verwenden
- Anthropic API ≠ Claude Pro → separates Guthaben
- MCP Server Port: uvicorn Default kann variieren → im server.py explizit setzen
- RemoteMCPServer spec.config → funktioniert NICHT → spec.url direkt verwenden
- imagePullPolicy: Never → ErrImageNeverPull → IfNotPresent verwenden
- StreamableHTTP DELETE 405 → trailing slash Problem, ignorierbar wenn Tools discovered
- kagent-tools Pod hat kein curl/wget → nur kubectl im PATH

## Observability Stack

### Status
| Säule | Tool | Status |
|-------|------|--------|
| Metrics | Prometheus + Grafana | ✅ |
| Logging | Loki + Promtail | ✅ |
| Tracing | Langfuse | ⏳ Python 3.14 inkompatibel |

### Prometheus
- Namespace: monitoring, Scrape: 15s
- PrometheusRule Label: release: monitoring (Pflicht!)
- Zugriff: kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090

### Grafana
- URL: http://grafana.local, Login: admin/newpassword123
- Loki Datasource: http://loki.monitoring.svc.cluster.local:3100

### PromQL Queries
- CPU per NS: sum by (namespace) (rate(container_cpu_usage_seconds_total[5m]))
- Memory: container_memory_working_set_bytes{container!=""}

## LaunchAgents
- com.yavuz.platform-agent → stündlicher Health Check
- com.yavuz.port-forward → Port-Forward localhost:3000
- com.yavuz.dashboard → localhost:8999

### start.sh (~/mac-setup/scripts/start.sh)
- Startet: GPU Limit, Ollama serve, K8s Pods, Port-Forward
- Ollama wird automatisch gestartet falls nicht läuft (OLLAMA_CONTEXT_LENGTH=65536)
- ollama-start Alias → ~/mac-setup/scripts/start.sh

## Agent System (LangGraph)
- File: ~/mac-setup/agent/platform_agent_lg.py
- Checkpointer: SqliteSaver → checkpoint.db
- run_intelligence: DEAKTIVIERT

## .zshrc Aliases
- ai-llama/ai-llama-fast/ai-gemma/ai-qwen/ai-mistral: Port 8080, 48k Kontext
- monitoring-start/stop

## Bekannte Lösungen
- Loopback: sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255
- TurboFlash V4 OOM: git reset --hard 8590cbff9
- K8s Restart >100: Issue (Docker Desktop akkumuliert)
- Grafana PromQL Division: sum by (namespace)
- Loki URL: http://loki.monitoring.svc.cluster.local:3100
- LaunchAgent PATH: absolute Pfade (/opt/homebrew/bin/python3)

## Offene TODOs
- [x] http-fetch-mcp deployen ✅
- [x] release-agent mit http-fetch-mcp verbinden ✅
- [x] release-agent System Prompt optimiert (CHANGELOG Sektionen, lowercase type) ✅
- [x] ollama serve in start.sh integriert ✅
- [x] HolmesGPT installiert und mit Gemma 4 via llama.cpp konfiguriert ✅
- [ ] release-agent weiter testen mit echten ROSA Release Notes
- [ ] kagent Phase 1: LangGraph Runtime + Intent Router + HITL
- [ ] kagent Phase 2: RBAC Rollen (viewer/operator/deployer/admin)
- [ ] kagent Phase 3: Prometheus + Grafana MCP
- [ ] kagent Phase 4: Teams/Slack Bot
- [ ] kagent Phase 5: ROSA-Deployment + Entra ID + OPA
- [ ] AlertManager Routing (critical vs warning)
- [ ] Grafana Tempo (OpenTelemetry)
- [ ] Langfuse aktivieren (Python 3.14 Support abwarten)
- [ ] TurboFlash V4 testen wenn M5 Pro Fix kommt
- [ ] SYSTEM_CONTEXT.md regelmäßig ins Git pushen
