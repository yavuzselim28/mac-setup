# SYSTEM_CONTEXT — Yavuz Topcu (Stand: 15. August 2026)

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
| ai-qwen-vllm | vllm-swift (Homebrew) | Qwen3 30B A3B 4bit | ~15–18GB | **~92 tok/s** | **Daily Driver** ✅ |
| ai-qwen-mlx | ekryski MLXServer | Qwen3 30B A3B 4bit | ~18GB | ~100 tok/s (1 req) / ~31 tok/s (3 req) | Single-User Speed, kein TurboQuant |
| ai-gemma | llama.cpp TurboQuant | Gemma 4 31B Q4 | ~20GB | 12.65 tok/s | Tool Use / HolmesGPT |
| ai-glm | llama.cpp TurboQuant | GLM-4.7-Flash Q4 | ~18GB | ~26 tok/s | Tool Use / HolmesGPT (Kandidat) |
| ai-mistral | llama.cpp | Mistral 7B Q4_K_M | 4GB | - | Schnell/leicht |

---

## vllm-swift (TheTom) ✅ Daily Driver — **JETZT ÜBER HOMEBREW**

### ⚠️ Wichtigste Änderung seit Mai 2026
Bisheriger Source-Install-Weg (`~/vllm-swift`, `source activate.sh`, `vllm serve ...`) wurde am 22.07.2026
komplett abgelöst durch die **offizielle Homebrew-Installation**. Grund: Der Source-Checkout von
`vllm-swift` main lief dem `mlx-swift-lm`-Branch `vllm-swift-stable` voraus (fehlende Swift-Typen wie
`RetrievalAttentionContext`, `BatchedHybridSparseLLM` — Upstream-Sync-Bug bei TheTom, main vs. stable-Branch
der Dependency). Der alte `~/vllm-swift`-Checkout und `~/mlx-swift-lm` wurden gelöscht.

Der frühere Hinweis *"Homebrew Bottle funktioniert NICHT mit turbo4v2"* stimmt so nicht mehr /
war ein metallib-Packaging-Bug in der Bottle selbst (siehe Fix unten) — turbo4v2 läuft über Homebrew
einwandfrei, gemessen ~92 tok/s (schneller als der alte Source-Build mit ~75–85 tok/s).

### Was ist vllm-swift
vLLM Metal Plugin powered by mlx-swift-lm. Python nur für Orchestrierung, Swift/Metal für Inference.
Repo: https://github.com/TheTom/vllm-swift
**Installiert via: `brew tap TheTom/tap && brew install vllm-swift`**
Aktuelle Version: **0.6.3** (Cellar: `/opt/homebrew/Cellar/vllm-swift/0.6.3`)

### Bekannter Bug: fehlendes metallib in der Bottle
Nach Install/Reinstall crasht der Server beim ersten Start mit:
```
MLX error: Failed to load the default metallib. library not found ... memory.cpp:69
```
**Fix (muss nach jedem `brew reinstall`/`brew upgrade vllm-swift` wiederholt werden):**
```bash
cp /opt/homebrew/Cellar/mlx/0.32.0/lib/mlx.metallib /opt/homebrew/Cellar/vllm-swift/<VERSION>/lib/mlx.metallib
```
(Versionsnummer im Pfad anpassen. Quelle ist die separate `mlx`-Homebrew-Formel, die ein passendes
metallib fürs eigene System mitbringt — kein eigener Build nötig.)
Sollte als GitHub Issue bei TheTom/vllm-swift gemeldet werden (Bottle-Formula kopiert das metallib
nicht automatisch neben `libVLLMBridge.dylib`).

### Starten
```bash
vllm-swift download mlx-community/Qwen3-30B-A3B-4bit    # einmalig, lädt nach ~/models/
vllm-swift serve mlx-community/Qwen3-30B-A3B-4bit \
  --served-model-name qwen3-30b \
  --max-model-len 40960 \
  --additional-config '{"kv_scheme": "turbo4v2", "kv_bits": 4}'
```
Kein `activate.sh`, kein `GLOO_SOCKET_IFNAME`-Fix mehr nötig — Homebrew-Wrapper regelt das automatisch.
**Neuer Standard-Port: 8000** (vorher 8083 beim Source-Build).

### Alias (.zshrc) — aktualisiert
```bash
alias ai-qwen-vllm="lsof -ti:8000 | xargs kill -9 2>/dev/null; sleep 1; vllm-swift serve mlx-community/Qwen3-30B-A3B-4bit --served-model-name qwen3-30b --max-model-len 40960 --additional-config '{\"kv_scheme\": \"turbo4v2\", \"kv_bits\": 4}'"
```
(Alter Alias mit `cd ~/vllm-swift && source activate.sh && vllm serve ... --port 8083` wurde entfernt.)

### Open WebUI Verbindung — aktualisiert
- URL: `http://10.254.254.254:8000/v1` (Port geändert, via `helm upgrade ollama-app ... --set openWebui.env.OPENAI_API_BASE_URL=...` gesetzt)
- API Key: `dummy`

### Performance (M5 Pro 64GB, 22.07.2026, Homebrew 0.6.3)
| Metrik | Wert |
|--------|------|
| Modell | Qwen3 30B A3B 4bit |
| Decode (Story-Test, 300 Tokens) | **~92,6 tok/s** (300 Tokens / 3,24s) |
| TurboQuant KV | turbo4v2, aktiv und funktionsfähig |
| Thinking Mode | ✅ aktiv (`/no_think` für leeren think-block) |

### Update-Prozedur (Homebrew)
```bash
brew upgrade vllm-swift
# WICHTIG: danach metallib-Fix erneut anwenden (siehe oben), sonst Crash beim nächsten Start!
```

### Integrationstest — funktioniert NICHT ohne Weiteres
`scripts/integration_test.sh` aus dem Repo ist nur für den **Source-Build-Workflow** gedacht
(erwartet `swift/`-Verzeichnis relativ zum Repo-Root, nicht die Homebrew-Bottle-Struktur).
Ein Testversuch am 22.07. via frischem Source-Checkout (`~/vllm-swift-test-only`) schlug mit
denselben API-Skew-Fehlern fehl wie oben beschrieben (main vs. stable-Branch von mlx-swift-lm).
→ Kein verlässlicher offizieller Test aktuell nutzbar; eigener curl-Benchmark (siehe Performance-Tabelle)
ist der praktikable Weg, die Installation zu verifizieren.

### TurboQuant+ Upstream-Status (aus README von turboquant_plus, Stand 22.07.2026)
- MLX Swift Upstream: ✅ gemerged in Apple `mlx-swift-lm` (PR #232, 2026-07-20) — volle asymmetrische
  Familie (turbo0v*/turbo8v*) + symmetrisches turbo4/3/2 mit per-dimension key calibration
- `turbo8v3`: 2.7x KV-Kompression, validiert auf 6 Modellfamilien inkl. 30B MoE (Qwen3-30B-A3B-Klasse)
- vLLM Upstream: ✅ gemerged (PR #38479)
- llama.cpp Upstream: ✅ Hadamard-Rotation gemerged (#21038 + WHT-Kernels)

### turbo8v3-Test auf diesem Setup (15.08.2026) ✅
`vllm-swift serve mlx-community/Qwen3-30B-A3B-4bit --additional-config '{"kv_scheme": "turbo8v3", "kv_bits": 3}'`
— Engine akzeptiert das Schema ohne Fehler, Warmup in 2,34s, zwei Testanfragen erfolgreich beantwortet,
~30 tok/s Generierungsdurchsatz (Einzel-Request, kein Lastvergleich). Rein funktional bestätigt — noch
kein Qualitäts-/Perplexity-Vergleich gegen `turbo4v2` gemacht, das bleibt offener TODO falls relevant.

---

## llama.cpp TurboQuant — Tool Use / HolmesGPT

### Fork
- Repo: TheTom/llama-cpp-turboquant (branch: feature/turboquant-kv-cache)
- Binary: ~/llama-cpp-turboquant/build/bin/llama-server
- Kompilieren: cd ~/llama-cpp-turboquant && cmake --build build --config Release -j$(sysctl -n hw.logicalcpu)
- Stabiler HEAD: fca3093c9 (Stand 15.08.2026, Merge PR #283 tq3-fused-hip) — davor 4 Monate lang auf
  8590cbff9 (9. April) gepinnt, ~1800 Commits Rückstand aufgeholt und neu kompiliert/validiert.

### Rebuild-Validierung (15.08.2026)
- Build sauber durchgelaufen (nur harmlose Compiler-Warnings aus Apple-Headern, keine echten Fehler).
- Mit Gemma 4 31B getestet: `K (q8_0): 1020 MiB, V (turbo4): 495 MiB` bei 49152 Kontext — TurboQuant aktiv.
  ~13,25 tok/s, deckt sich mit dem bisherigen Baseline-Wert (12,65 tok/s).
- Wichtig: die KV-Cache-Init-Logs ("TurboQuant rotation matrices initialized", "K (turbo4): ... MiB")
  erscheinen bei Standard-Verbosity (`-lv 3`) nicht mehr im Log — dafür jetzt `-v`/`--log-verbose` nötig.
  Reine Logging-Änderung im Upstream, keine Funktionsänderung. Doku in `docs/TURBOQUANT.md` entsprechend anpassen.

### TurboFlash V4 — weiterhin Vorsicht geboten
- Die beiden ursprünglich OOM-verursachenden Commits (6946763, b0b8dde) tauchen in der aktuellen
  Fork-Historie nicht mehr auf (vermutlich per Rebase entfernt) — das ist aber keine Bestätigung, dass
  TurboFlash V4 jetzt sicher ist, nur dass diese exakten Commits nicht mehr im Pfad liegen.
  TurboFlash V4 wurde beim Update auf fca3093c9 nicht gezielt erneut getestet.

### Aliases
```bash
alias ai-gemma="lsof -ti:8080 | xargs kill -9 2>/dev/null; sleep 1; cd ~/llama-cpp-turboquant && ./build/bin/llama-server -m ~/models/gemma4-31b/gemma-4-31B-it-UD-Q4_K_XL.gguf --cache-type-k q8_0 --cache-type-v turbo4 -ngl 99 -c 49152 --flash-attn on --host 0.0.0.0 --port 8080 -np 1"
alias ai-glm="lsof -ti:8080 | xargs kill -9 2>/dev/null; sleep 1; cd ~/llama-cpp-turboquant && ./build/bin/llama-server -m ~/models/glm-4.7-flash/GLM-4.7-Flash-UD-Q4_K_XL.gguf --cache-type-k turbo4 --cache-type-v turbo4 -ngl 99 -c 49152 --flash-attn on --host 0.0.0.0 --port 8080 -np 1"  # 15.08.2026: GLM-4.7-Flash, Kandidat fuer ai-gemma-Ablösung (Tool-Use/HolmesGPT), getestet ~26 tok/s. Achtung: braucht symmetrisches turbo4 fuer K+V, kein q8_0/turbo4-Mix wie bei Gemma.
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
- release-agent: type-Parameter muss lowercase sein (`kubernetes`, nicht `Kubernetes`) — sonst
  fällt der Agent fälschlich auf OpenShift-Docs zurück (Bug in server.py, System-Prompt sendet Großschreibung)

---

## Netzwerk
- Loopback Alias: 10.254.254.254 (nach Neustart: sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255)
- vllm-swift: **http://10.254.254.254:8000/v1** (Port geändert von 8083 auf 8000, 22.07.2026)
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
ollama-app-open-webui  (v0.9.5, Update von v0.9.4)
```

### Helm
- Chart: ~/ollama-k8s/ollama-chart
- Values: ~/mac-setup/charts/ollama/values.yaml
- Upgrade: helm upgrade ollama-app ~/ollama-k8s/ollama-chart -n phoenix -f ~/mac-setup/charts/ollama/values.yaml
- vllm-swift Backend läuft **nicht** über Helm, sondern als direkter Python/Homebrew-Prozess

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
- **vllm-swift metallib fehlt (Homebrew):** `cp /opt/homebrew/Cellar/mlx/<VERSION>/lib/mlx.metallib /opt/homebrew/Cellar/vllm-swift/<VERSION>/lib/mlx.metallib`
- **zsh + `#`-Kommentare in Multi-Line-Copy-Paste:** zsh interpretiert `#` in interaktiver Shell nicht als
  Kommentar (`command not found: #`) — harmlos, aber wenn Befehlsblöcke mit Kommentarzeilen eingefügt werden,
  entstehen diese Fehlermeldungen. Kein Blocker, nur Rauschen im Terminal.
- **`getcwd: cannot access parent directories`:** tritt auf, wenn das aktuelle Arbeitsverzeichnis der Shell
  per `rm -rf` gelöscht wurde, während man noch darin steht. Fix: `cd ~` (oder ein anderes existierendes
  Verzeichnis), danach normal weiterarbeiten.
- **Homebrew "untrusted tap":** neuer Trust-Mechanismus verlangt `brew trust <tap>` bzw.
  `brew trust --formula <tap>/<formula>` vor Erstnutzung eines Taps.
- Ingress nach Cluster-Neustart: kubectl apply -f ~/mac-setup/k8s/ollama-ingress-phoenix.yaml

---

## Offene TODOs
- [x] turbo8v3 statt turbo4v2 testen — 15.08.2026 funktional bestätigt (siehe turbo8v3-Test-Notiz oben),
      Perplexity/Qualitätsvergleich gegen turbo4v2 steht noch aus
- [ ] llama-cpp-turboquant Fork von fca3093c9 (15.08.2026) aktuell halten — Update-Rückstand war zuletzt
      4 Monate/~1800 Commits, regelmäßiger nachziehen
- [ ] GitHub Issue bei TheTom/vllm-swift: fehlendes metallib in Homebrew-Bottle melden
- [ ] GitHub Issue bei TheTom/vllm-swift: main-Branch-Build kaputt wegen mlx-swift-lm-stable-Branch-Skew
      (RetrievalAttentionContext, BatchedHybridSparseLLM fehlen)
- [ ] HolmesGPT mit vllm-swift testen (Qwen3 Tool Calling via Hermes) — jetzt mit neuem Port 8000 prüfen
- [ ] release-agent weiter testen mit echten ROSA Release Notes
- [ ] kagent Phase 1: LangGraph Runtime + Intent Router + HITL
- [ ] kagent Phase 2: RBAC Rollen (viewer/operator/deployer/admin)
- [ ] kagent Phase 3: Prometheus + Grafana MCP
- [ ] kagent Phase 4: Teams/Slack Bot
- [ ] kagent Phase 5: ROSA-Deployment + Entra ID + OPA
- [ ] AlertManager Routing
- [ ] Langfuse aktivieren (Python 3.14 Support abwarten)
- [ ] ArgoCD Applications neu konfigurieren
- [ ] SYSTEM_CONTEXT.md regelmäßig ins Git pushen
