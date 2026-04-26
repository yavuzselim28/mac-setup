# MLX_CONTEXT — Yavuz Topcu (Stand: April 2026)

## Was ist dieser Stack

Native Swift MLX Inference Server auf Apple Silicon — Alternative zu llama.cpp.
Entwickelt von ekryski (Eric Kryski) in Kollaboration mit TheTom (Tom Turney).
Repo: https://github.com/ekryski/mlx-swift-lm (Branch: ek/tom-eric-moe-tuning)

## Warum MLX statt llama.cpp

- MLX ist Apples eigenes ML Framework — kennt Apple Silicon von innen
- Kein Python Overhead, kein llama.cpp Layer
- Messergebnis (April 2026, M5 Pro 64GB):
  - llama.cpp TurboQuant: Gemma 4 31B → 12.65 tok/s Decode, ~7 tok/s Prefill, TTFT ~5s
  - MLX Swift + NAX: Gemma 4 26B → ~31 tok/s Decode (~2.4x schneller)
  - MLX Swift ekryski (aktuell): Gemma 4 26B A4B → ~120 tok/s Prefill, ~31 tok/s Decode, TTFT ~346ms

## Hardware / OS

- MacBook Pro M5 Pro, 64GB Unified Memory
- macOS 26.4.1 (Tahoe, stable — NICHT Beta)
- Xcode installiert unter /Applications/Xcode.app
- DerivedData Hash: mlx-swift-lm-fdcrefzthdziegeflgsfzdsysodu

## Setup

### 1. Repos clonen

```bash
cd ~ && git clone https://github.com/ekryski/mlx-swift-lm.git
cd mlx-swift-lm && git checkout ek/tom-eric-moe-tuning

cd ~ && git clone --recursive -b ek/speed-improvements-2 https://github.com/ekryski/mlx-swift mlx-swift
export MLX_SWIFT_PATH=~/mlx-swift
```

### 2. Metallib bauen

```bash
cd ~/mlx-swift-lm
swift package resolve
./scripts/build-metallib.sh release
```

### 3. Swift 6 Compatibility Fix

Problem: @main struct + main.swift gleichzeitig nicht erlaubt in Swift 6.
Fix: main.swift → server.swift umbenennen (einmalig, bleibt erhalten):

```bash
mv ~/mlx-swift-lm/Sources/MLXServer/main.swift ~/mlx-swift-lm/Sources/MLXServer/server.swift
```

### 4. Prefill Bridge bauen

```bash
export MLX_SWIFT_PATH=~/mlx-swift
cd ~/mlx-swift-lm
./scripts/build-prefill-bridge.sh
cp Sources/NativePrefillBridge/libprefill_bridge_gemma.dylib .build/arm64-apple-macosx/release/
```

WICHTIG: Bridge funktioniert NICHT für MoE Modelle (gemma-4-26b-a4b) — Shape-Fehler.
Bridge nur für Dense Gemma relevant. Für A4B MoE: Bridge OFF lassen.

### 5. Xcode Build

```bash
cd ~/mlx-swift-lm
xcodebuild -scheme MLXServer -configuration Release -destination 'platform=macOS' -resolvePackageDependencies
xcodebuild -scheme MLXServer -configuration Release -destination 'platform=macOS' build 2>&1 | grep -E "error:|BUILD SUCCEEDED|BUILD FAILED"
```

### 6. Starten (ekryski Stack)

```bash
alias ai-gemma-ekryski="lsof -ti:8081 | xargs kill -9 2>/dev/null; sleep 1; /Users/yavuztopcu/Library/Developer/Xcode/DerivedData/mlx-swift-lm-fdcrefzthdziegeflgsfzdsysodu/Build/Products/Release/MLXServer --model mlx-community/gemma-4-26b-a4b-it-4bit --port 8081 --host 0.0.0.0"
```

### 7. Benchmark

```bash
cd ~/mlx-swift-lm
./scripts/benchmark.sh --model mlx-community/gemma-4-26b-a4b-it-4bit
```

## Fix-Historie

### Fix 1–7 (Alt — nicht mehr nötig)
Alle Fix 1–7 aus dem alten Setup sind im neuen Branch `ek/tom-eric-moe-tuning` bereits
nativ implementiert:
- Scale wird in TurboQuantKVCache.swift Zeile ~1275 korrekt angewendet: `let qRot = keyMSECodec.prepareQueries(queries) * scale`
- compressedAttention ist nativ korrekt implementiert (kein Dequant-Workaround nötig)
- Buffer Overflow im Rotating KV Cache gefixt (Commit 062a628)
- Fix 7 Scripts (patch_scale_kernel.py etc.) liegen in ~/mlx-swift-lm/scripts/ — aber 0 Treffer weil Code anders strukturiert ist

### TurboQuant API

Standard (kurze Kontexte empfohlen):
```bash
curl -s http://127.0.0.1:8081/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"gemma","messages":[...],"max_tokens":800,"kv_scheme":"turbo4"}'
```

Ohne Kompression (lange Kontexte >8K empfohlen):
```bash
  -d '{"model":"gemma","messages":[...],"max_tokens":800}'
```

kv_scheme Optionen: turbo4 (4/4bit) ✅, turbo4v2 (4/2bit), turbo4v3 (4/3bit), turbo0v4 (FP16/4bit), turbo0v2 (FP16/2bit)

## SwiftLM (SharpAI) — Produktiver Daily Driver ✅ (Stand: April 2026)

### Was ist SwiftLM
Alternativer MLX Swift Server von SharpAI. Fertig-Binary, kein Build nötig.
Repo: https://github.com/SharpAI/SwiftLM
Binary: ~/SwiftLM-bin/SwiftLM (Release b543)

### Installation
```bash
curl -L https://github.com/SharpAI/SwiftLM/releases/download/b543/SwiftLM-b543-macos-arm64.tar.gz -o /tmp/swiftlm.tar.gz
mkdir ~/SwiftLM-bin && tar -xzf /tmp/swiftlm.tar.gz -C ~/SwiftLM-bin
```
Wichtig: mlx.metallib muss im gleichen Verzeichnis wie Binary liegen.

### Aliases (.zshrc)
```bash
alias ai-gemma-mlx="lsof -ti:8081 | xargs kill -9 2>/dev/null; sleep 1; ~/SwiftLM-bin/SwiftLM --model mlx-community/gemma-4-26b-a4b-it-4bit --port 8081 --host 0.0.0.0 --repeat-penalty 1.1 --max-tokens 1000"
alias ai-qwen-mlx="lsof -ti:8081 | xargs kill -9 2>/dev/null; sleep 1; ~/SwiftLM-bin/SwiftLM --model mlx-community/Qwen3-30B-A3B-4bit --port 8081 --host 0.0.0.0 --repeat-penalty 1.1 --max-tokens 1000"
alias ai-llama-mlx="lsof -ti:8081 | xargs kill -9 2>/dev/null; sleep 1; ~/SwiftLM-bin/SwiftLM --model mlx-community/Llama-3.3-70B-Instruct-4bit --port 8081 --host 0.0.0.0 --repeat-penalty 1.1 --max-tokens 1000"
alias ai-gemma-ekryski="lsof -ti:8081 | xargs kill -9 2>/dev/null; sleep 1; /Users/yavuztopcu/Library/Developer/Xcode/DerivedData/mlx-swift-lm-fdcrefzthdziegeflgsfzdsysodu/Build/Products/Release/MLXServer --model mlx-community/gemma-4-26b-a4b-it-4bit --port 8081 --host 0.0.0.0"
```

### Bekannte Probleme SwiftLM
- Tool Use (HolmesGPT/kagent) → `strict: true` Bug → HTTP 500 — NICHT für Tool Use verwenden
- Streaming hängt bei großen Requests wenn SwiftLM intern blockiert — Neustart hilft
- Für HolmesGPT/kagent: llama.cpp verwenden (Port 8080)
- Open WebUI: SwiftLM auf Port 8081, Connection: http://10.254.254.254:8081/v1

### Modell-Übersicht
| Alias | Stack | Modell | RAM | Decode | TTFT | Use Case |
|-------|-------|--------|-----|--------|------|----------|
| ai-gemma-ekryski | ekryski MLXServer | Gemma 4 26B A4B 4bit | ~14GB | ~31 tok/s | ~346ms | Daily Driver, TurboQuant |
| ai-gemma-mlx | SwiftLM | Gemma 4 26B A4B 4bit | ~16GB | ~31 tok/s | ~300ms | Daily Driver Open WebUI |
| ai-qwen-mlx | SwiftLM | Qwen3 30B A3B 4bit | ~18GB | ~25 tok/s | ~300ms | Sweet Spot |
| ai-llama-mlx | SwiftLM | Llama 3.3 70B 4bit | ~40GB | ~7 tok/s | 31s* | Heavy Reasoning |

*70B TTFT hoch wegen Swap auf 64GB — auf M5 Ultra (192GB) deutlich besser

## Performance (M5 Pro 64GB, April 2026)

### Offizieller Benchmark (ekryski benchmark.sh, simple method, 4096 ctx)

| Stack | Modell | Prefill | Decode | TTFT | GPU Baseline | GPU Peak |
|-------|--------|---------|--------|------|-------------|----------|
| llama.cpp TurboQuant | Gemma 4 31B | ~7 tok/s | 12.65 tok/s | ~5s | ~20GB | ~22GB |
| MLX ekryski (NAX, Bridge OFF) | Gemma 4 26B A4B 4bit | **~120 tok/s** | **~31 tok/s** | **~346ms** | 13.48GB | 14.61GB |
| MLX ekryski (NAX) | Llama 3.3 70B 4bit | 2.0 tok/s | 6.9 tok/s | 31s* | 36.96GB | 38.24GB |

HINWEIS: Prefill variiert stark (89–173 tok/s) je nach Thermal State des M5 Pro.
Peak 173 tok/s wurde einmalig gemessen — realistischer Durchschnitt ~120 tok/s.
Bridge für MoE (A4B) inkompatibel — Shape-Fehler in quantized_matmul.

*Swap-bedingt auf 64GB RAM

### Langkontext Performance (gemessen, ekryski Stack)

  512 tokens   turbo4   ~29 tok/s   optimal
  3K tokens    turbo4   ~20 tok/s   spürbarer Einbruch
  40K tokens   turbo4   ~4 tok/s    massiver Einbruch ❌
  40K tokens   standard ~20 tok/s   stabiler ✅

WICHTIG: TurboQuant bricht bei langen Kontexten massiv ein.
Für Kontexte >8K → Standard NAX verwenden (kein kv_scheme).

## Bekannte Probleme

  TurboQuant Einbruch >8K          TurboFlash Kernel skaliert nicht         Standard NAX verwenden
  Bridge inkompatibel mit MoE       Shape-Fehler quantized_matmul A4B        Bridge OFF für Gemma A4B
  N-Gram Artefakte                  Thinking-Channel Interaktion              ngram_size nicht verwenden
  SwiftLM strict:true Bug           Holmes/kagent sendet strict JSON          llama.cpp für Tool Use verwenden
  SwiftLM Streaming hängt           Interner Block nach erstem Request        Neustart
  Gemma 26B Repetition Loop         4bit Quantisierung bei langen Outputs     --repeat-penalty 1.1
  Llama 70B Swap auf 64GB           Modell zu groß für 64GB                   M5 Ultra abwarten
  Prefill Varianz                   Thermal Throttling M5 Pro                 Peak 173, Avg ~120 tok/s

## Offene TODOs

- [ ] TurboQuant Langkontext-Bug fixen (TurboFlash Kernel bei 40K+ bricht ein)
- [ ] Bridge für MoE (A4B) kompatibel machen — Shape-Fehler untersuchen
- [ ] Qwen3 30B testen (Sweet Spot zwischen 26B und 70B)
- [ ] SwiftLM strict:true Bug als Issue melden
- [ ] MLX_CONTEXT.md regelmäßig ins Git pushen
- [ ] ekryski Branch ek/turbo-kv-fixes evaluieren wenn MLXServer wieder drin ist

## Repo Stand (April 2026)

  ekryski/mlx-swift-lm:  Branch ek/tom-eric-moe-tuning, aktiv entwickelt
  ekryski/mlx-swift:     Branch ek/speed-improvements-2, NAX Metal dispatch (TheTom PR)
  TurboQuant:            Nativ in TurboQuantKVCache.swift implementiert, keine manuellen Patches nötig
  Langkontext:           TurboQuant nicht geeignet >8K — Standard NAX verwenden
  Spec Decoding:         N-Gram nicht empfohlen, Draft Model für MoE inkompatibel
  SwiftLM (SharpAI):     Release b543, Daily Driver für Open WebUI, kein Tool Use
  ekryski MLXServer:     Gebaut, läuft auf Port 8081, alias ai-gemma-ekryski
