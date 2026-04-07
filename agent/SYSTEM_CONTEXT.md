# Platform Context — wird von allen Agenten geladen

## Hardware
- MacBook Pro M5 Pro, 64GB Unified Memory, 1TB SSD
- Apple Silicon GPU (Metal), 18 Cores
- Compiler: Apple Clang (NICHT GCC — GCC-spezifische Fixes irrelevant)

## Modelle (lokal)
- Llama 3.3 70B Instruct Q4_K_M (Unsloth) — Hauptmodell, 40GB
- Llama 3.1 8B Instruct Q4_K_M — Draft/Fallback, 4.6GB
- Gemma 4 31B UD-Q4_K_XL (Unsloth) — Multimodal, 17GB
- Qwen 2.5 72B Q4_K_M (12-part) — Code/Mathe, 44GB
- Mistral 7B Q4_K_M — Schnell/Test, 4GB

## Infrastruktur
- llama.cpp Fork: TheTom/llama-cpp-turboquant (feature/turboquant-kv-cache)
- TurboQuant: turbo4 KV-Cache Kompression (4.25 bit, 3.8x)
- Speculative Decoding: Llama 70B + 8B Draft (~10 tok/s)
- Kubernetes: Docker Desktop local, namespace ollama
- Open WebUI: v0.8.12, Port 3000
- ArgoCD GitOps: yavuzselim28/mac-setup
- Port-Forward: localhost:3000 → Open WebUI

## TurboQuant Konfiguration
- cache-type-k: turbo4
- cache-type-v: turbo4
- cache-type-k-draft: turbo4
- cache-type-v-draft: turbo4
- Flash Attention: aktiviert
- Kontext: 16384 tokens
- np: 1 (ein paralleler Slot)

## Relevanz-Kriterien für Commits
- Apple Silicon / Metal Optimierungen: SEHR RELEVANT
- turbo3/turbo4 KV-Cache Änderungen: SEHR RELEVANT
- Speculative Decoding Verbesserungen: RELEVANT
- Q4_K_M Quantisierung Fixes: RELEVANT
- GCC-spezifische Fixes: NICHT RELEVANT (wir nutzen Clang)
- CUDA/ROCm/AMD Änderungen: NICHT RELEVANT
- Windows-spezifische Fixes: NICHT RELEVANT
- Neue Modell-Architekturen (Gemma 4, MoE): PRÜFEN ob Metal Support

## Neu kompilieren: NUR WENN
- Metal Kernel geändert (ggml-metal.metal)
- turbo3/turbo4 Algorithmus geändert
- Flash Attention Pfad geändert
- Llama/Qwen Architektur Support geändert
- Performance-kritische Änderung auf Apple Silicon

## NICHT kompilieren für
- Dokumentation
- GCC/Linux Build Fixes
- CUDA/ROCm Backend
- Andere Hardware-Architekturen
- Minor Bugfixes ohne Metal-Bezug

## Business Context (Audi)
- Platform Engineering bei Audi AG
- ROSA (Red Hat OpenShift on AWS)
- PSF-Chargeback Modell für Multi-Tenant Cost Allocation
- TurboQuant Business Case: 5x mehr concurrent Users pro GPU
