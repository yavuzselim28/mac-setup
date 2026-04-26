# MLX_CONTEXT — Yavuz Topcu (Stand: April 2026)

## Was ist dieser Stack

Native Swift MLX Inference Server auf Apple Silicon — Alternative zu llama.cpp.
Entwickelt von ekryski (Eric Kryski) in Kollaboration mit TheTom (Tom Turney).

## Hardware / OS

- MacBook Pro M5 Pro, 64GB Unified Memory
- macOS 26.4.1 (Tahoe, stable — NICHT Beta)
- Xcode installiert unter /Applications/Xcode.app
- DerivedData Hash: mlx-swift-lm-fdcrefzthdziegeflgsfzdsysodu

---

## Stack Übersicht (Stand April 2026)

| Stack | Modell | Decode (1 req) | Decode (3 req) | TurboQuant | Concurrency |
|-------|--------|---------------|----------------|------------|-------------|
| llama.cpp TurboQuant | Gemma 4 31B | 12.65 tok/s | ❌ | ✅ | ❌ |
| SwiftLM (SharpAI) | Gemma 4 26B A4B | ~31 tok/s | ❌ | ❌ | ❌ |
| ekryski MLXServer | Qwen3 30B A3B | ~100 tok/s | ~31 tok/s | ❌ | ❌ |
| **vllm-swift ✅ EMPFOHLEN** | **Qwen3 30B A3B** | **~75 tok/s** | **~66 tok/s** | **✅ turbo4v2** | **✅ batched** |

**vllm-swift ist der beste All-round Stack** — TurboQuant + Concurrency + OpenAI-kompatibel.
75 tok/s mit 30B Modell ist schneller als GPT-4 API (~30-50 tok/s). Komplett lokal, offline, kostenlos.

---

## vllm-swift (TheTom) ✅ Daily Driver

### Was ist vllm-swift
vLLM Metal Plugin powered by mlx-swift-lm. Python nur für Orchestrierung, Swift/Metal für Inference.
Repo: https://github.com/TheTom/vllm-swift
Installiert unter: ~/vllm-swift

### Installation
```bash
cd ~/vllm-swift
./scripts/install.sh
source activate.sh
cp ~/mlx-swift-lm/.build/arm64-apple-macosx/release/mlx.metallib \
   ~/vllm-swift/swift/.build/arm64-apple-macosx/release/
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

### Performance (M5 Pro 64GB, April 2026)
| Metrik | Wert |
|--------|------|
| Modell | Qwen3 30B A3B 4bit |
| RAM | ~18GB |
| Decode (1 req) | ~75 tok/s |
| Decode (3 req gleichzeitig) | ~66 tok/s |
| Prefill | ~70 tok/s |
| TurboQuant KV | turbo4v2 (3.2x Kompression) |
| Thinking Mode | ✅ aktiv |

### Bekannte Limitierungen
- LoRA nicht unterstützt
- top_p Sampling nicht in batched decode
- Nur Qwen3 nutzt voll-gebatchten Decode Pfad
- Chunked prefill deaktiviert
- --enable-reasoning Flag fehlt in v0.19.1

---

## ekryski MLXServer (Single-User Speed)

### Setup
```bash
cd ~ && git clone https://github.com/ekryski/mlx-swift-lm.git
cd mlx-swift-lm && git checkout ek/tom-eric-moe-tuning
cd ~ && git clone --recursive -b ek/speed-improvements-2 https://github.com/ekryski/mlx-swift mlx-swift
export MLX_SWIFT_PATH=~/mlx-swift

cd ~/mlx-swift-lm
swift package resolve
./scripts/build-metallib.sh release
./scripts/build-prefill-bridge.sh
mv Sources/MLXServer/main.swift Sources/MLXServer/server.swift

xcodebuild -scheme MLXServer -configuration Release -destination 'platform=macOS' -resolvePackageDependencies
xcodebuild -scheme MLXServer -configuration Release -destination 'platform=macOS' build 2>&1 | grep -E "error:|BUILD SUCCEEDED|BUILD FAILED"
```

### Aliases
```bash
alias ai-qwen-mlx="lsof -ti:8081 | xargs kill -9 2>/dev/null; sleep 1; /Users/yavuztopcu/Library/Developer/Xcode/DerivedData/mlx-swift-lm-fdcrefzthdziegeflgsfzdsysodu/Build/Products/Release/MLXServer --model mlx-community/Qwen3-30B-A3B-4bit --port 8081 --host 0.0.0.0 --repeat-penalty 1.1"
alias ai-gemma-ekryski="lsof -ti:8081 | xargs kill -9 2>/dev/null; sleep 1; /Users/yavuztopcu/Library/Developer/Xcode/DerivedData/mlx-swift-lm-fdcrefzthdziegeflgsfzdsysodu/Build/Products/Release/MLXServer --model mlx-community/gemma-4-26b-a4b-it-4bit --port 8081 --host 0.0.0.0"
```

### Performance
| Modell | Prefill | Decode | TTFT | GPU |
|--------|---------|--------|------|-----|
| Gemma 4 26B A4B 4bit | ~120 tok/s (Peak 173) | ~31 tok/s | ~346ms | 13.5GB |
| Qwen3 30B A3B 4bit | ~22 tok/s | ~100 tok/s | ~1.6s | 16GB |

---

## SwiftLM (SharpAI) — Legacy

Binary: ~/SwiftLM-bin/SwiftLM (Release b543)
Bekannte Probleme: strict:true Bug, kein TurboQuant, Streaming hängt.
Für HolmesGPT/kagent: llama.cpp verwenden.

---

## llama.cpp TurboQuant — Tool Use / kagent

```bash
alias ai-gemma="lsof -ti:8080 | xargs kill -9 2>/dev/null; sleep 1; cd ~/llama-cpp-turboquant && ./build/bin/llama-server -m ~/models/gemma4-31b/gemma-4-31B-it-UD-Q4_K_XL.gguf --cache-type-k q8_0 --cache-type-v turbo4 -ngl 99 -c 49152 --flash-attn on --host 0.0.0.0 --port 8080 -np 1"
```

---

## Modell-Übersicht

| Alias | Stack | Modell | RAM | Decode | Use Case |
|-------|-------|--------|-----|--------|----------|
| ai-qwen-vllm | vllm-swift | Qwen3 30B A3B 4bit | ~18GB | ~75 tok/s | **Daily Driver** ✅ |
| ai-qwen-mlx | ekryski | Qwen3 30B A3B 4bit | ~18GB | ~100 tok/s | Single-User Speed |
| ai-gemma-ekryski | ekryski | Gemma 4 26B A4B 4bit | ~14GB | ~31 tok/s | TurboQuant Test |
| ai-gemma | llama.cpp | Gemma 4 31B Q4 | ~20GB | 12.65 tok/s | Tool Use / kagent |
| ai-llama-mlx | SwiftLM | Llama 3.3 70B 4bit | ~40GB | ~7 tok/s | Heavy Reasoning |

---

## Bekannte Probleme

| Problem | Ursache | Workaround |
|---------|---------|------------|
| TurboQuant Einbruch >8K | TurboFlash Kernel skaliert nicht | Standard NAX verwenden |
| Bridge inkompatibel mit MoE | Shape-Fehler quantized_matmul | Bridge OFF |
| SwiftLM strict:true Bug | Holmes/kagent sendet strict JSON | llama.cpp für Tool Use |
| Prefill Varianz ekryski | Thermal Throttling M5 Pro | Peak 173, Avg ~120 tok/s |
| vllm-swift metallib fehlt | Nach Neuinstallation | cp aus mlx-swift-lm Build |

---

## Offene TODOs

- [ ] TurboQuant Langkontext-Bug fixen
- [ ] vllm-swift Reasoning Parser (--enable-reasoning fehlt in v0.19.1)
- [ ] Qwen3 TurboQuant in ekryski Stack
- [ ] MLX_CONTEXT.md regelmäßig ins Git pushen

---

## Repo Stand (April 2026)

```
ekryski/mlx-swift-lm:  Branch ek/tom-eric-moe-tuning
ekryski/mlx-swift:     Branch ek/speed-improvements-2
vllm-swift (TheTom):   v0.2.0, Daily Driver, turbo4v2 aktiv
SwiftLM (SharpAI):     Release b543, Legacy
```
