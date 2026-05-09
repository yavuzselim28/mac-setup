# MLX_CONTEXT — Yavuz Topcu (Stand: Mai 2026)

## Was ist dieser Stack

Native Swift MLX Inference Server auf Apple Silicon — Alternative zu llama.cpp.
Entwickelt von TheTom (Tom Turney), in Kollaboration mit ekryski (Eric Kryski).

## Hardware / OS

- MacBook Pro M5 Pro, 64GB Unified Memory
- macOS 26.4.1 (Tahoe, stable — NICHT Beta)
- Xcode installiert unter /Applications/Xcode.app
- DerivedData Hash: nicht mehr relevant (vllm-swift nutzt SPM, kein Xcode Build)

---

## Stack Übersicht (Stand Mai 2026)

| Stack | Modell | Decode (1 req) | Decode (3 req) | TurboQuant | Concurrency |
|-------|--------|---------------|----------------|------------|-------------|
| llama.cpp TurboQuant | Gemma 4 31B | 12.65 tok/s | ❌ | ✅ | ❌ |
| SwiftLM (SharpAI) | Gemma 4 26B A4B | ~31 tok/s | ❌ | ❌ | ❌ |
| ekryski MLXServer | Qwen3 30B A3B | ~100 tok/s | ~31 tok/s | ❌ | ❌ |
| **vllm-swift ✅ EMPFOHLEN** | **Qwen3 30B A3B** | **~75 tok/s** | **~66 tok/s** | **✅ turbo4v2 (echt)** | **✅ batched** |

**vllm-swift ist der beste All-round Stack** — TurboQuant + Concurrency + OpenAI-kompatibel.
75 tok/s mit 30B Modell ist schneller als GPT-4 API (~30-50 tok/s). Komplett lokal, offline, kostenlos.

⚠️ **Wichtig:** Vor v0.5.3 war `turbo4v2` silent broken — der KV Cache lief auf raw fp16.
Ab v0.5.3 (jetzt v0.6.0) komprimiert es wirklich. Alte Performance-Zahlen sind raw fp16 Zahlen.

---

## vllm-swift (TheTom) ✅ Daily Driver

### Was ist vllm-swift
vLLM Metal Plugin powered by mlx-swift-lm. Python nur für Orchestrierung, Swift/Metal für Inference.
Repo: https://github.com/TheTom/vllm-swift
Installiert unter: ~/vllm-swift
Aktuelle Version: **v0.6.0**

### Abhängigkeiten (TheToms eigene Forks — NICHT ekryskis Repos)

```
~/tom-mlx-swift-lm  → github.com/TheTom/mlx-swift-lm  Branch: vllm-swift-stable @ c02054a
~/tom-mlx-swift     → github.com/TheTom/mlx-swift      Branch: vllm-swift-stable @ cd49379
```

Diese sind als Symlinks eingebunden:
```
~/vllm-swift/swift/Packages/mlx-swift-lm → ~/tom-mlx-swift-lm
~/vllm-swift/swift/Packages/mlx-swift    → ~/tom-mlx-swift
```

⚠️ Die Original-Symlinks im Repo zeigten auf `/Users/tom/dev/` (TheToms lokales Mac) —
das ist ein bekannter Bug. Manuell mit obigen Pfaden ersetzen nach jedem `git clone`.

### Erstinstallation (von Grund auf)

```bash
# TheToms Repos klonen
cd ~
git clone https://github.com/TheTom/mlx-swift-lm.git tom-mlx-swift-lm
cd tom-mlx-swift-lm && git checkout vllm-swift-stable
cd ~
git clone https://github.com/TheTom/mlx-swift.git tom-mlx-swift
cd tom-mlx-swift && git checkout vllm-swift-stable

# vllm-swift klonen
git clone https://github.com/TheTom/vllm-swift.git ~/vllm-swift
cd ~/vllm-swift

# Kaputte Symlinks ersetzen
rm swift/Packages/mlx-swift-lm swift/Packages/mlx-swift
ln -s ~/tom-mlx-swift-lm swift/Packages/mlx-swift-lm
ln -s ~/tom-mlx-swift swift/Packages/mlx-swift

# Swift Dependencies resolven (nutzt .build/checkouts, nicht Packages/)
cd swift
rm -rf .build/checkouts .build/manifest.db .build/workspace-state.json
swift package resolve
cd ..

# Build + metallib + Python install
bash scripts/install.sh
source activate.sh
```

### Update-Prozedur (nach git pull)

```bash
cd ~/vllm-swift
git pull

# Prüfen ob Package.resolved neue Commits pinnt
cat swift/Package.resolved | python3 -m json.tool | grep -A3 "mlx-swift"

# Falls neue Commits: checkouts leeren und neu resolven
cd swift
rm -rf .build/checkouts .build/manifest.db .build/workspace-state.json
swift package resolve
cd ..

# Neu bauen (metallib + dylib + Python)
bash scripts/install.sh
source activate.sh
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
| Decode (1 req) | ~75 tok/s |
| Decode (3 req gleichzeitig) | ~66 tok/s |
| Prefill | ~70 tok/s |
| TurboQuant KV | turbo4v2 (echte Kompression ab v0.5.3) |
| Thinking Mode | ✅ aktiv (`/no_think` für leeren think-block) |

### Smoke Test nach Start

```bash
curl -s http://localhost:8083/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{"model":"qwen3-30b","messages":[{"role":"user","content":"What is 2+2? /no_think"}],"max_tokens":50,"stream":false}' \
  | python3 -m json.tool | grep -E "content|completion_tokens"
# Erwarteter Output: <think>\n\n</think>\n\n2 + 2 = 4.
```

### Neu in v0.6.0 (gegenüber v0.2.0)

- **v0.3.0:** Metal buffer-aliasing race fix, ~10% Throughput Gewinn bei B≥17
- **v0.4.0:** Auto-detect tool + reasoning parser (Hermes, qwen3_coder XML), response_rewriter, max_tokens rescue für reasoning models
- **v0.5.1:** BatchedKVCache Memory Leak fix (vorher bis 85GB RSS bei langen Sessions)
- **v0.5.3:** ⭐ turbo4v2 wirklich aktiv auf batched-decode Pfad (vorher silent raw fp16)
- **v0.5.4:** turbo4v2 fix auf dense Qwen3 (separater Pfad als MoE)
- **v0.6.0:** TriAttention V3 + longctx (experimental, OFF by default), Gemma 4 MTP drafter

### Bekannte Limitierungen
- LoRA nicht unterstützt
- top_p Sampling nicht in batched decode
- Nur Qwen3 nutzt voll-gebatchten Decode Pfad (MoE); andere Architekturen sequential
- Chunked prefill deaktiviert
- TriAttention V3 nur mit explizitem `VLLM_TRIATT_ENABLED=1` + `LONGCTX_ENDPOINT`

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
| ai-qwen-vllm | vllm-swift | Qwen3 30B A3B 4bit | ~15–18GB | ~75 tok/s | **Daily Driver** ✅ |
| ai-qwen-mlx | ekryski | Qwen3 30B A3B 4bit | ~18GB | ~100 tok/s | Single-User Speed |
| ai-gemma-ekryski | ekryski | Gemma 4 26B A4B 4bit | ~14GB | ~31 tok/s | TurboQuant Test |
| ai-gemma | llama.cpp | Gemma 4 31B Q4 | ~20GB | 12.65 tok/s | Tool Use / kagent |
| ai-llama-mlx | SwiftLM | Llama 3.3 70B 4bit | ~40GB | ~7 tok/s | Heavy Reasoning |

---

## Bekannte Probleme

| Problem | Ursache | Workaround |
|---------|---------|------------|
| Symlinks in swift/Packages/ zeigen auf /Users/tom/dev/ | TheToms hardcodierte Pfade im Repo | Manuell auf ~/tom-mlx-swift* zeigen lassen |
| metallib fehlt nach git pull | SPM kompiliert .metal nicht automatisch | bash scripts/install.sh ausführen |
| turbo4v2 vor v0.5.3 war silent raw fp16 | BatchedKVCache kannte kein turbo | Seit v0.5.3 gefixt |
| SwiftLM strict:true Bug | Holmes/kagent sendet strict JSON | llama.cpp für Tool Use |
| Prefill Varianz ekryski | Thermal Throttling M5 Pro | Peak 173, Avg ~120 tok/s |
| dense Qwen3 + turbo4v2 vor v0.5.4 | anderer decode Pfad als MoE | Seit v0.5.4 gefixt |

---

## Offene TODOs

- [ ] vllm-swift tool calling für kagent testen (Hermes auto-detect seit v0.4.0 drin)
- [ ] Qwen3 TurboQuant in ekryski Stack
- [ ] MLX_CONTEXT.md regelmäßig ins Git pushen
- [ ] TriAttention V3 + longctx evaluieren wenn stabil

---

## Repo Stand (Mai 2026)

```
TheTom/mlx-swift-lm:   Branch vllm-swift-stable @ c02054a (in ~/tom-mlx-swift-lm)
TheTom/mlx-swift:      Branch vllm-swift-stable @ cd49379 (in ~/tom-mlx-swift)
vllm-swift (TheTom):   v0.6.0, Daily Driver, turbo4v2 echt aktiv
ekryski/mlx-swift-lm:  Branch ek/tom-eric-moe-tuning (in ~/mlx-swift-lm, für ekryski Stack)
ekryski/mlx-swift:     Branch ek/speed-improvements-2 (in ~/mlx-swift)
SwiftLM (SharpAI):     Release b543, Legacy
```
