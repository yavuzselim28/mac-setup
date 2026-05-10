# SYSTEM_CONTEXT — Yavuz Topcu (Stand: Mai 2026)

## Wer bin ich
Platform Engineer bei Audi AG (seit März 2025).
Arbeite mit ROSA (Red Hat OpenShift on AWS), Kubernetes, Terraform, AWS.
Dieses Projekt ist mein lokales AI-Setup zum Lernen und Testen.

## Hardware
- MacBook Pro M5 Pro, 64GB Unified Memory, 1TB SSD
- Apple Silicon GPU (Metal) — Compiler: Clang (NICHT GCC)
- GPU Memory Limit: sudo sysctl iogpu.wired_limit_mb=52429
- Tailscale IP: 100.78.80.6

---

## Lokaler AI Stack — Übersicht

| Alias | Stack | Modell | RAM | Decode | Use Case |
|-------|-------|--------|-----|--------|----------|
| ai-qwen-vllm | vllm-swift | Qwen3 30B A3B 4bit | ~15–18GB | ~75–85 tok/s | **Daily Driver** ✅ |
| ai-qwen-mlx | ekryski MLXServer | Qwen3 30B A3B 4bit | ~18GB | ~100 tok/s | Single-User Speed |
| ai-gemma | llama.cpp TurboQuant | Gemma 4 31B Q4 | ~20GB | 12.65 tok/s | Tool Use / HolmesGPT |
| ai-llama | llama.cpp | Llama 3.3 70B Q4_K_M | 40GB | 8.31 tok/s | Heavy Tasks |
| ai-llama-fast | llama.cpp + Spec. Dec. | 70B + 8B Draft | 40+4.6GB | ~10 tok/s | Heavy Reasoning |
| ai-qwen | llama.cpp | Qwen 2.5 72B Q4_K_M | 44GB | - | Large Context |
| ai-mistral | llama.cpp | Mistral 7B Q4_K_M | 4GB | - | Schnell/leicht |
| ai-llama-mlx | SwiftLM | Llama 3.3 70B 4bit | ~40GB | ~7 tok/s | Legacy |

---

## vllm-swift (TheTom) ✅ Daily Driver

### Was ist vllm-swift
vLLM Metal Plugin powered by mlx-swift-lm. Python nur für Orchestrierung, Swift/Metal für Inference.
Repo: https://github.com/TheTom/vllm-swift
Installiert unter: ~/vllm-swift
Aktuelle Version: **v0.6.0**

### Wichtige Hinweise
- ⚠️ turbo4v2 war vor v0.5.3 silent broken (raw fp16) — seit v0.5.4 echt aktiv
- ⚠️ Homebrew Bottle (TheTom/tap) funktioniert NICHT mit turbo4v2 — Source Install verwenden
- ⚠️ Symlinks in swift/Packages/ zeigen auf /Users/tom/dev/ — manuell fixen (einmalig erledigt)
- Source Install Alias: `ai-qwen-vllm` → cd ~/vllm-swift && source activate.sh && vllm serve

### Abhängigkeiten (TheToms Forks)
```
~/tom-mlx-swift-lm  → github.com/TheTom/mlx-swift-lm  Branch: vllm-swift-stable @ c02054a
~/tom-mlx-swift     → github.com/TheTom/mlx-swift      Branch: vllm-swift-stable @ cd49379
```

Symlinks:
```
~/vllm-swift/swift/Packages/mlx-swift-lm → ~/tom-mlx-swift-lm
~/vllm-swift/swift/Packages/mlx-swift    → ~/tom-mlx-swift
```

### Starten
```bash
cd ~/vllm-swift && source activate.sh
vllm serve mlx-community/Qwen3-30B-A3B-4bit \
  --served-model-name qwen3-30b \
  --max-model-len 40960 \
  --port 8083 \
  --additional-config '{"kv_scheme": "turbo4v2", "kv_bits": 4}'
```

### Alias (.zshrc)
```bash
alias ai-qwen-vllm="lsof -ti:8083 | xargs kill -9 2>/dev/null; sleep 1; cd ~/vllm-swift && source activate.sh && vllm serve mlx-community/Qwen3-30B-A3B-4bit --served-model-name qwen3-30b --max-model-len 40960 --port 8083 --additional-config '{\"kv_scheme\": \"turbo4v2\", \"kv_bits\": 4}'"
```

### Open WebUI Verbindung
- URL: `http://10.254.254.254:8083/v1`
- API Key: `dummy`

### Performance (M5 Pro 64GB, Mai 2026)
| Metrik | Wert |
|--------|------|
| Modell | Qwen3 30B A3B 4bit |
| RAM | ~15–18GB |
| Decode (1 req) | ~75–85 tok/s |
| Decode (4 req gleichzeitig) | ~77–82 tok/s |
| Prefill | ~70–92 tok/s |
| TurboQuant KV | turbo4v2 (echte Kompression seit v0.5.4) |
| Thinking Mode | ✅ aktiv (`/no_think` für leeren think-block) |

### Update-Prozedur
```bash
cd ~/vllm-swift
git pull
cd swift
rm -rf .build/checkouts .build/manifest.db .build/workspace-state.json
swift package resolve
cd ..
bash scripts/install.sh
source activate.sh
```

---

## llama.cpp TurboQuant — Tool Use / HolmesGPT

### Fork
- Repo: TheTom/llama-cpp-turboquant (branch: feature/turboquant-kv-cache)
- Binary: ~/llama-cpp-turboquant/build/bin/llama-server
- Kompilieren: cd ~/llama-cpp-turboquant && cmake --build build --config Release -j$(sysctl -n hw.logicalcpu)
- Stabiler HEAD: 8590cbff9 (Merge PR #62 Vulkan turbo3 + Metal TurboFlash kernel)

### TurboFlash V4 — NICHT kompilieren
- Commits 6946763 + b0b8dde: OOM auf M5 Pro
- Workaround: git reset --hard 8590cbff9

### Aliases
```bash
alias ai-gemma="lsof -ti:8080 | xargs kill -9 2>/dev/null; sleep 1; cd ~/llama-cpp-turboquant && ./build/bin/llama-server -m ~/models/gemma4-31b/gemma-4-31B-it-UD-Q4_K_XL.gguf --cache-type-k q8_0 --cache-type-v turbo4 -ngl 99 -c 49152 --flash-attn on --host 0.0.0.0 --port 8080 -np 1"
alias ai-llama="lsof -ti:8080 | xargs kill -9 2>/dev/null; sleep 1; cd ~/llama-cpp-turboquant && ./build/bin/llama-server -m ~/models/llama33-70b-q4km.gguf --cache-type-k q8_0 --cache-type-v turbo4 -ngl 99 -c 49152 --flash-attn on --host 0.0.0.0 --port 8080"
alias ai-llama-fast="lsof -ti:8080 | xargs kill -9 2>/dev/null; sleep 1; cd ~/llama-cpp-turboquant && ./build/bin/llama-server -m ~/models/llama33-70b-q4km.gguf --model-draft ~/models/llama31-8b-draft.gguf --cache-type-k q8_0 --cache-type-v turbo4 --cache-type-k-draft q8_0 --cache-type-v-draft turbo4 -ngl 99 -c 49152 -np 1 -fa on --host 0.0.0.0 --port 8080 --draft-max 8 --draft-min 2 --metrics"
```

---

## HolmesGPT — K8s Diagnose Tool

### Konfiguration
- Config: ~/.holmes/config.yaml
```yaml
model: "openai/gemma"
api_key: "dummy"
api_base: "http://localhost:8080/v1"
max_steps: 10
```
- Wichtig: ai-gemma muss laufen bevor Holmes gestartet wird
- Wichtig: Holmes immer aus ~ starten

### Aliases
```bash
alias h="cd ~ && holmes ask --fast-mode"
alias holmes="cd ~ && holmes ask --fast-mode"
```

### Bekannte Probleme
- Ollama + Holmes → Infinite Loop — NICHT verwenden
- kubernetes_tabular_query liest lokale Dateien wenn Holmes aus falschem Verzeichnis

---

## Netzwerk
- Loopback Alias: 10.254.254.254 (nach Neustart: sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255)
- vllm-swift: http://10.254.254.254:8083/v1
- llama.cpp: http://10.254.254.254:8080/v1
- Open WebUI: http://ollama.local (via Ingress) oder http://localhost:3000 (Port-Forward)

---

## Kubernetes Infrastruktur

### Setup
- Docker Desktop local
- Namespace: **phoenix** (nicht mehr ollama)
- Monitoring Namespace: monitoring
- Docker Desktop Memory: 20GB

### Deployments (Namespace: phoenix)
```
ollama-app-ollama
ollama-app-open-webui  (v0.9.4)
```

### Helm
- Chart: ~/ollama-k8s/ollama-chart
- Values: ~/mac-setup/charts/ollama/values.yaml
- Upgrade: helm upgrade ollama-app ~/ollama-k8s/ollama-chart -n phoenix -f ~/mac-setup/charts/ollama/values.yaml

### Ingress
- ollama.local → ollama-app-open-webui:8080 (Namespace: phoenix)
- YAML: ~/mac-setup/k8s/ollama-ingress-phoenix.yaml
- Nach Cluster-Neustart: kubectl apply -f ~/mac-setup/k8s/ollama-ingress-phoenix.yaml
- Wird automatisch via start.sh angewendet

### Open WebUI Update
```bash
docker pull ghcr.io/open-webui/open-webui:vX.X.X
# values.yaml updaten: image: ghcr.io/open-webui/open-webui:vX.X.X
helm upgrade ollama-app ~/ollama-k8s/ollama-chart -n phoenix -f ~/mac-setup/charts/ollama/values.yaml
kubectl rollout status deployment/ollama-app-open-webui -n phoenix
```

### Monitoring
- kube-prometheus-stack (Grafana: grafana.local, admin/newpassword123)
- Loki URL: http://loki.monitoring.svc.cluster.local:3100
- ArgoCD: argocd.local (keine Applications mehr konfiguriert — manuell via kubectl)

---

## start.sh (ollama-start Alias)

```bash
# Startet:
# - GPU Memory Limit
# - Loopback Alias 10.254.254.254
# - Ollama serve (falls nicht läuft)
# - K8s Pods hochfahren (phoenix Namespace)
# - Ollama Ingress anwenden
# - Ingress Port-Forward (Port 80)
```

---

## kagent — AI Platform Operator

### Installation
```bash
brew install kagent  # v0.8.6
helm install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds -n kagent --create-namespace
helm install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent -n kagent \
  --set providers.default=ollama \
  --set providers.ollama.baseUrl=http://host.docker.internal:11434 \
  --set providers.ollama.model=qwen2.5:32b
```

### LLM Provider
```bash
kubectl -n kagent patch modelconfig default-model-config --type=merge -p '{
  "spec": {
    "model": "qwen2.5:32b",
    "provider": "Ollama",
    "ollama": {"host": "http://host.docker.internal:11434"}
  }
}'
```

### Ollama (für kagent)
- Port: 11434
- OLLAMA_CONTEXT_LENGTH=65536 (kagent sendet lange System Prompts)
- Modelle: llama3.1:8b, qwen2.5:14b, qwen2.5:32b (Standard)

### Aktive Agents
- k8s-agent: Multi-Namespace Analyse, Root Cause Analysis ✅
- release-agent: Version Check, Breaking Changes, Upgrade-Empfehlung ✅

### Tool Server
- kagent-tool-server: http://kagent-tools.kagent:8084/mcp (100+ Tools)
- http-fetch-mcp: http://http-fetch-mcp.kagent.svc.cluster.local:8085/mcp

### Bekannte Probleme
- helm repo add → NICHT funktioniert → OCI Registry
- API Version → immer v1alpha2
- Context Overflow → max 5 Tools pro Agent
- imagePullPolicy: Never → ErrImageNeverPull → IfNotPresent verwenden

---

## Observability Stack
| Säule | Tool | Status |
|-------|------|--------|
| Metrics | Prometheus + Grafana | ✅ |
| Logging | Loki + Promtail | ✅ |
| Tracing | Langfuse | ⏳ Python 3.14 inkompatibel |

---

## LaunchAgents
- com.yavuz.platform-agent → stündlicher Health Check
- com.yavuz.port-forward → Port-Forward localhost:3000
- com.yavuz.dashboard → localhost:8999

---

## Bekannte Lösungen
- Loopback nach Neustart: sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255
- TurboFlash V4 OOM: git reset --hard 8590cbff9
- Grafana PromQL Division: sum by (namespace)
- Loki URL: http://loki.monitoring.svc.cluster.local:3100
- vllm-swift metallib fehlt: bash ~/vllm-swift/scripts/install.sh
- Ingress nach Cluster-Neustart: kubectl apply -f ~/mac-setup/k8s/ollama-ingress-phoenix.yaml

---

## Offene TODOs
- [ ] HolmesGPT mit vllm-swift testen (Qwen3 Tool Calling via Hermes)
- [ ] release-agent weiter testen mit echten ROSA Release Notes
- [ ] kagent Phase 1: LangGraph Runtime + Intent Router + HITL
- [ ] kagent Phase 2: RBAC Rollen (viewer/operator/deployer/admin)
- [ ] kagent Phase 3: Prometheus + Grafana MCP
- [ ] kagent Phase 4: Teams/Slack Bot
- [ ] kagent Phase 5: ROSA-Deployment + Entra ID + OPA
- [ ] AlertManager Routing
- [ ] Langfuse aktivieren (Python 3.14 Support abwarten)
- [ ] TurboFlash V4 testen wenn M5 Pro Fix kommt
- [ ] ArgoCD Applications neu konfigurieren
- [ ] SYSTEM_CONTEXT.md regelmäßig ins Git pushen
