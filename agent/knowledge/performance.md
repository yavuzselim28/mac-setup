# Performance Benchmarks — M5 Pro 64GB

## llama-server (Stand April 2026)

### Llama 3.3 70B Q4_K_M + turbo4 + Speculative Decoding
- Prompt Eval: 83.93 tok/s
- Decode: 8.31 tok/s
- Draft Acceptance Rate: 88% (22 accepted / 25 generated)
- KV-Cache Größe bei 32k Kontext: ~2.7GB (turbo4) vs ~10.8GB (FP16)
- GPU Memory: 42185 MB (Modell) + 1360 MB (KV-Cache) + 282 MB (Compute)

### Konfiguration für obige Werte
- -c 32768 (32k Kontext)
- --cache-type-k turbo4 --cache-type-v turbo4
- --cache-type-k-draft turbo4 --cache-type-v-draft turbo4
- -ngl 99 (alles auf GPU)
- -fa on (Flash Attention)
- --draft-max 8 --draft-min 2
- Sparse V: automatisch aktiv

### Vergleich turbo3 vs turbo4 (TheTom Benchmarks)
- turbo4: +6.3% PPL-Verlust, 3.8x KV-Cache Kompression
- turbo3: +11.4% PPL-Verlust, 4.6-5.1x KV-Cache Kompression
- ENTSCHEIDUNG: turbo4 wegen besserer Qualität

## TurboQuant Algorithmus
- PolarQuant: Walsh-Hadamard Transform + Lloyd-Max Codebooks
- K-Cache: 3-bit PolarQuant + 1-bit QJL = 4.25 bits/dim
- V-Cache: turbo4
- KL Divergenz: < 0.001
- Cosine Similarity: > 0.989

## Business Case (Audi PSF-Chargeback)
- TurboQuant ermöglicht 4-5x mehr concurrent Users pro GPU
- PSF-Faktor: KV-Cache Kompression direkt messbar in Chargeback-Modell

## Geplante Benchmarks
- Wöchentlicher automatischer Benchmark Agent (TODO)
- tokens/sec Tracking über Zeit (stündlich via Intelligence Agent)
- RAM-Verlauf Chart im Dashboard (TODO)

## Aktueller Build-Status
- HEAD: 8590cbf (kompiliert am 2026-04-09)
- Branch: feature/turboquant-kv-cache
- Kompilierte Commits: 8590cbf, 40b6f96, 830eb54, acad28d, cffcbf0
- Build-Befehl: cd ~/llama-cpp-turboquant && cmake --build build --config Release -j$(sysctl -n hw.logicalcpu)
- Letzte Aktualisierung: 2026-04-18 12:03
