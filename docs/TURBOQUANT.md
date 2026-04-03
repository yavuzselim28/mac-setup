# TurboQuant auf Apple Silicon — Local LLM Setup Guide

> Getestet auf MacBook Pro M5 Pro (64GB), macOS, lokales Kubernetes (Docker Desktop), ArgoCD  
> Datum: April 2026

---

## Was ist TurboQuant?

TurboQuant ist ein Algorithmus von Google Research (ICLR 2026), der den **KV-Cache** von LLMs während der Inferenz komprimiert — von 16-bit auf 3-bit pro Wert, ohne merklichen Qualitätsverlust.

**KV-Cache** = das "Kurzzeitgedächtnis" des Modells. Wächst linear mit dem Kontext und ist bei langen Gesprächen der größte RAM-Flaschenhals.

### Warum ist das wichtig?

| | Ohne TurboQuant | Mit TurboQuant |
|---|---|---|
| KV-Cache (32K Kontext, 70B) | ~8 GB | ~2 GB |
| KV-Cache (32K Kontext, 7B) | ~1 GB | ~200 MB |
| Kompression | — | **5.1x** |
| Qualitätsverlust | — | praktisch null |

TurboQuant macht es möglich, ein **70B Modell mit 32K Kontext auf einem MacBook Pro mit 64GB** zu betreiben — ohne Swapping, mit voller Metal-Beschleunigung.

---

## Voraussetzungen

- Apple Silicon Mac (M1/M2/M3/M4/M5) mit mindestens 32GB RAM
- macOS mit Xcode Command Line Tools
- cmake >= 3.14
- Docker Desktop (optional, für Open WebUI)
- Kubernetes lokal (optional, für Open WebUI)

```bash
# Xcode Command Line Tools installieren
xcode-select --install

# cmake prüfen / installieren
cmake --version
brew install cmake  # falls nicht vorhanden
```

---

## Schritt 1 — TurboQuant Fork klonen & bauen

TurboQuant ist noch nicht in mainline llama.cpp. Wir nutzen den stabilsten Community-Fork mit Metal-Support:

```bash
git clone https://github.com/TheTom/llama-cpp-turboquant.git
cd llama-cpp-turboquant
git checkout feature/turboquant-kv-cache

# Build mit Metal (Apple Silicon)
cmake -B build \
  -DGGML_METAL=ON \
  -DGGML_METAL_EMBED_LIBRARY=ON \
  -DCMAKE_BUILD_TYPE=Release

cmake --build build --config Release -j$(sysctl -n hw.logicalcpu)
```

Build dauert ~5-10 Minuten. Das Binary liegt danach in `./build/bin/llama-server`.

**Validierung:** Im Build-Output sollte stehen:
```
ggml_metal_library_init: turbo3 sparse V dequant enabled
```

---

## Schritt 2 — Modell herunterladen

Wir empfehlen **Llama 3.3 70B Instruct Q4_K_M** von Unsloth (kein HF-Account nötig):

```bash
mkdir -p ~/models

# Llama 3.3 70B (~40 GB)
curl -L \
  "https://huggingface.co/unsloth/Llama-3.3-70B-Instruct-GGUF/resolve/main/Llama-3.3-70B-Instruct-Q4_K_M.gguf" \
  -o ~/models/llama33-70b-q4km.gguf \
  --progress-bar

# Alternativ: Mistral 7B (~4 GB, schneller zum Testen)
curl -L \
  "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf" \
  -o ~/models/mistral-7b-q4km.gguf \
  --progress-bar
```

**Wichtig:** Dateigröße nach dem Download prüfen. Eine korrekte 70B-Datei ist ~40 GB. Wenn sie nur wenige KB groß ist, war der Download ein Auth-Fehler (HTML statt Modell).

```bash
ls -lh ~/models/
```

---

## Schritt 3 — llama-server mit TurboQuant starten

```bash
cd ~/llama-cpp-turboquant

./build/bin/llama-server \
  -m ~/models/llama33-70b-q4km.gguf \
  --cache-type-k turbo3 \
  --cache-type-v turbo3 \
  -ngl 99 \
  -c 32768 \
  -fa on \
  --host 0.0.0.0 --port 8080
```

### Parameter erklärt

| Flag | Bedeutung |
|---|---|
| `--cache-type-k turbo3` | Keys mit TurboQuant 3-bit komprimieren |
| `--cache-type-v turbo3` | Values mit TurboQuant 3-bit komprimieren |
| `-ngl 99` | Alle Layer auf GPU (Metal) |
| `-c 32768` | Kontextfenster 32K Token |
| `-fa on` | Flash Attention (Pflicht für TurboQuant) |
| `--host 0.0.0.0` | Von außen erreichbar (für K8s/Docker) |

### TurboQuant aktiv validieren

Im Startup-Log muss stehen:
```
llama_kv_cache: TurboQuant rotation matrices initialized (128x128)
llama_kv_cache: K (turbo3): 1000.00 MiB, V (turbo3): 1000.00 MiB
llama_kv_cache: attn_rot_k = 1
llama_kv_cache: attn_rot_v = 1
```

Wenn dort `K (f16)` steht, ist TurboQuant **nicht** aktiv.

### Memory Breakdown (Erwartungswerte)

```
70B Q4_K_M + turbo3 + 32K Kontext:
  Modellgewichte:   ~40.500 MiB
  KV-Cache:          ~2.000 MiB  (statt ~8.000 MiB ohne TQ)
  Compute Buffer:      ~266 MiB
  ─────────────────────────────
  Total:            ~42.800 MiB  ✅ passt in 64 GB
```

---

## Schritt 4 — Testen

```bash
# Funktionstest
curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant. Respond naturally, never output JSON."},
      {"role": "user", "content": "Hi wie gehts?"}
    ],
    "max_tokens": 200
  }' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
```

Erwartete Ausgabe: normale, natürlichsprachliche Antwort auf Deutsch.

---

## Schritt 5 — Open WebUI verbinden (optional)

Falls du Open WebUI in Kubernetes betreibst, kannst du den llama-server als OpenAI-kompatiblen Endpoint einbinden.

### Mac IP ermitteln

```bash
ipconfig getifaddr en0
# Beispiel: 192.168.178.32
```

### Open WebUI Deployment patchen

```bash
kubectl set env deployment/ollama-app-open-webui \
  -n ollama \
  OPENAI_API_BASE_URL="http://192.168.178.32:8080/v1" \
  OPENAI_API_KEY="dummy"
```

### GitOps (ArgoCD) — values.yaml anpassen

Damit ArgoCD die Änderung nicht beim nächsten Sync überschreibt, in `values.yaml` eintragen:

```yaml
openWebui:
  env:
    OPENAI_API_BASE_URL: "http://192.168.178.32:8080/v1"
    OPENAI_API_KEY: "dummy"
```

```bash
git add charts/ollama/values.yaml
git commit -m "feat: add TurboQuant llama-server as OpenAI endpoint"
git push
```

---

## Warum kein Docker für den llama-server?

Docker auf macOS hat **keinen Zugriff auf Metal** (Apples GPU-Framework). Der llama-server würde ohne GPU laufen — 10-20x langsamer. Daher läuft er direkt auf macOS, und nur die UI (Open WebUI) ist im Container.

```
Open WebUI  →  K8s/Docker  (nur UI, keine Inference)
llama-server →  macOS direkt  (Inference, Metal GPU)
```

---

## Häufige Fehler

### `invalid magic characters: 'Inva'`
→ Modell-Download war ein Auth-Fehler. Datei löschen und neu laden, ggf. mit HF-Token.

### `error: couldn't bind HTTP server socket`
→ Port 8080 bereits belegt. `lsof -ti:8080 | xargs kill -9`

### KV-Cache zeigt `K (f16)` statt `K (turbo3)`
→ `--cache-type-k turbo3` Flag fehlt oder Flash Attention nicht aktiviert. `-fa on` ist Pflicht.

### Modell antwortet nur mit JSON / Function Calls
→ Falsches GGUF (eingebettetes Function-Calling-Template). Anderes GGUF nehmen, z.B. Unsloth statt bartowski für Llama 3.x.

---

## Verständnis: GGUF vs. TurboQuant

| | GGUF (Q4_K_M) | TurboQuant (turbo3) |
|---|---|---|
| Was wird komprimiert? | Modellgewichte | KV-Cache (Laufzeit) |
| Wann? | Einmalig, liegt als Datei | Live, bei jedem Token |
| Kompression | 4-bit (von 32-bit) | 3-bit (von 16-bit) |
| Qualitätsverlust | ~2-3% | <1% bis 8K Kontext |
| Zweck | Modell auf Disk/RAM kleiner | Kontextgedächtnis kleiner |

Beide ergänzen sich — zusammen machen sie 70B auf Consumer-Hardware möglich.

---

## RAM-Planung für Apple Silicon

| Modell | GGUF | Gewichte | KV-Cache (32K, turbo3) | Min. RAM |
|---|---|---|---|---|
| Mistral 7B | Q4_K_M | ~4 GB | ~200 MB | 16 GB |
| Llama 3.1 8B | Q4_K_M | ~5 GB | ~200 MB | 16 GB |
| Llama 3.3 70B | Q4_K_M | ~40 GB | ~2 GB | 64 GB |
| Llama 3.1 405B | Q3_K_M | ~160 GB | ~8 GB | 192 GB |

---

## Nächste Schritte

- [ ] HF-Account anlegen → offizielles Llama 3.1 70B laden
- [ ] llama-server als launchd Service einrichten (autostart beim Mac-Boot)
- [ ] Benchmark: Baseline (f16) vs. turbo3 bei verschiedenen Kontextlängen
- [ ] Warten bis TurboQuant in mainline llama.cpp landet → Ollama native Support

---

*Erstellt nach einem hands-on Session mit TurboQuant auf MacBook Pro M5 Pro (64GB), April 2026.*
