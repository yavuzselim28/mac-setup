#!/bin/bash
# ============================================================================
# apply-v4-hybrid.sh — TurboFlash V4 Hybrid Patch für M5 Pro
# ============================================================================
# Wendet den V4-Hybrid-Patch auf Commit 6946763 an und baut llama-server neu.
#
# Was der Patch macht:
#   - Verschiebt o_state[DV] und v_decoded[DV] von Registern → Shared Memory
#   - Reduziert Register-Druck um ~8 floats pro Thread
#   - Behebt kIOGPUCommandBufferCallbackErrorOutOfMemory auf M5 Pro
#   - Behält V4-Vorteile: Online-Softmax, SIMD K-Scoring, Token-Loop
#
# Voraussetzung: Du bist aktuell auf 40b6f96 (stabiler Stand)
#
# Usage:
#   chmod +x apply-v4-hybrid.sh
#   ./apply-v4-hybrid.sh
# ============================================================================

set -euo pipefail

REPO_DIR="$HOME/llama-cpp-turboquant"
TARGET_COMMIT="6946763"
STABLE_COMMIT="40b6f96"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "=========================================="
echo " TurboFlash V4-Hybrid Patch für M5 Pro"
echo "=========================================="
echo ""

# --- Prüfe ob wir im richtigen Repo sind ---
if [ ! -d "$REPO_DIR/.git" ]; then
    echo -e "${RED}Fehler: $REPO_DIR ist kein Git-Repo${NC}"
    exit 1
fi

cd "$REPO_DIR"

# --- Aktuellen Stand merken ---
CURRENT_SHA=$(git rev-parse --short HEAD)
echo -e "Aktueller HEAD: ${YELLOW}${CURRENT_SHA}${NC}"

# --- Prüfe ob uncommitted changes ---
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo -e "${RED}Fehler: Uncommitted changes im Repo. Bitte erst committen oder stashen.${NC}"
    exit 1
fi

# --- Erstelle Backup-Branch ---
BACKUP_BRANCH="backup/pre-v4-hybrid-$(date +%Y%m%d-%H%M%S)"
echo -e "Backup-Branch: ${GREEN}${BACKUP_BRANCH}${NC}"
git branch "$BACKUP_BRANCH"

# --- Checkout auf V4-Commit ---
echo ""
echo "→ Checkout auf Commit ${TARGET_COMMIT} (TurboFlash V4)..."
git checkout "$TARGET_COMMIT" --quiet

ACTUAL_SHA=$(git rev-parse --short HEAD)
if [[ "$ACTUAL_SHA" != "$TARGET_COMMIT"* ]] && [[ "$TARGET_COMMIT" != "$ACTUAL_SHA"* ]]; then
    echo -e "${RED}Fehler: Checkout auf ${TARGET_COMMIT} fehlgeschlagen (HEAD ist ${ACTUAL_SHA})${NC}"
    git checkout "$CURRENT_SHA" --quiet
    exit 1
fi
echo -e "  HEAD jetzt: ${GREEN}${ACTUAL_SHA}${NC}"

# --- Patch anwenden ---
echo ""
echo "→ Wende V4-Hybrid-Patch an..."
echo ""

python3 << 'PYTHON_PATCH'
import sys

# ================================================================
# PATCH 1: ggml-metal-ops.cpp — kurze, eindeutige Substitutionen
# ================================================================
ops_file = "ggml/src/ggml-metal/ggml-metal-ops.cpp"
with open(ops_file, 'r') as f:
    ops = f.read()

# Jede Substitution ist ein kurzer, eindeutiger String — kein Multi-Line-Match
ops_subs = [
    ("const size_t smem_p1 = 16;",
     "const size_t smem_p1 = sizeof(float) * 2 * dv;"),
    ("// V4: no shared memory in pass 1 (all registers)",
     "// V4-hybrid: shared memory for V accumulator + V decode buffer"),
    ("// Metal requires at least 16 bytes for threadgroup memory",
     "// Layout: shared_o[DV] + shared_v_dec[DV] = 2 * DV floats"),
    ('TURBOFLASH: P1 V4 dispatch',
     'TURBOFLASH: P1 V4-hybrid dispatch'),
]

for old, new in ops_subs:
    if old not in ops:
        print(f"  ✗ ops.cpp: '{old}' nicht gefunden!")
        sys.exit(1)
    ops = ops.replace(old, new)

with open(ops_file, 'w') as f:
    f.write(ops)
print("  ✓ ggml-metal-ops.cpp: 4 Substitutionen")

# ================================================================
# PATCH 2: ggml-metal.metal — Kernel-Body ersetzen
# ================================================================
metal_file = "ggml/src/ggml-metal/ggml-metal.metal"
with open(metal_file, 'r') as f:
    lines = f.readlines()

# --- Finde Kernel-Body: Anker = "DK_PER_LANE = DK / 32" ---
body_start = None
for i, line in enumerate(lines):
    if 'DK_PER_LANE = DK / 32' in line and 'constexpr' in line:
        body_start = i
        break

if body_start is None:
    print("  ✗ metal: 'DK_PER_LANE = DK / 32' nicht gefunden!")
    sys.exit(1)

# --- Finde Body-Ende: "}" nach "partial_ms" + "lane == 0" Block ---
body_end = None
for i in range(body_start + 20, len(lines)):
    if lines[i].strip() == '}':
        # Schau ob partial_ms in den letzten ~8 Zeilen vorkommt
        context = ''.join(lines[max(i-8, body_start):i])
        if 'partial_ms' in context:
            body_end = i + 1
            break

if body_end is None:
    print("  ✗ metal: Kernel-Funktionsende nicht gefunden!")
    sys.exit(1)

print(f"  → Kernel-Body: Zeilen {body_start+1}–{body_end} ({body_end - body_start} Zeilen)")

# --- Ermittle Indent der ersten Zeile ---
indent = ''
for ch in lines[body_start]:
    if ch in (' ', '\t'):
        indent += ch
    else:
        break
i2 = indent + '    '  # ein Level tiefer
i3 = indent + '        '  # zwei Level tiefer

# --- Neuer Kernel-Body ---
new_body = f"""{indent}constexpr short DK_PER_LANE = DK / 32;

{indent}const uint lane = tiitg % 32; // SIMD lane (0-31)
{indent}const uint bh_idx = tgpig[0];
{indent}const uint block_id = tgpig[1];

{indent}const int T_kv = args.ne11;
{indent}const int n_blocks = args.n_blocks;

{indent}// Token range for this block
{indent}const int t_start = (int)(block_id * TURBO_FLASH_BLOCK_SIZE);
{indent}const int t_end = min(t_start + TURBO_FLASH_BLOCK_SIZE, T_kv);

{indent}// Decompose bh_idx back to (iq1, iq2, iq3) for pointer arithmetic
{indent}const uint iq1 = bh_idx % args.ne01;
{indent}const uint iq2 = (bh_idx / args.ne01) % args.ne02;
{indent}const uint iq3 = (bh_idx / args.ne01) / args.ne02;

{indent}// GQA: map query head to KV head
{indent}const uint ikv2 = iq2 / (args.ne02 / args.ne_12_2);
{indent}const uint ikv3 = iq3 / (args.ne03 / args.ne_12_3);

{indent}// ====== Shared memory layout ======
{indent}// shared_o[DV]     — V accumulator (online softmax output)
{indent}// shared_v_dec[DV] — decoded V values for current token
{indent}threadgroup float * shared_o     = shmem;
{indent}threadgroup float * shared_v_dec = shmem + DV;

{indent}// Initialize V accumulator to zero
{indent}for (int d = (int)lane; d < DV; d += 32) {{
{i2}shared_o[d] = 0.0f;
{indent}}}

{indent}// ====== Load Q into registers (small: DK_PER_LANE floats) ======
{indent}device const float * q_ptr = (device const float *)((device const char *)q + iq1*args.nb01 + iq2*args.nb02 + iq3*args.nb03);
{indent}float q_vals[DK_PER_LANE];
{indent}for (short i = 0; i < DK_PER_LANE; i++) {{
{i2}const int d = (int)lane + i * 32;
{i2}q_vals[i] = (d < DK) ? q_ptr[d] : 0.0f;
{indent}}}

{indent}// ====== Codebook in registers (8 floats) ======
{indent}float v_cb[8];
{indent}for (int i = 0; i < 8; i++) {{
{i2}v_cb[i] = float(turbo_centroids_3bit_h[i]);
{indent}}}

{indent}// ====== Online softmax scalars — in registers ======
{indent}float m_state = -INFINITY;
{indent}float l_state = 0.0f;

{indent}// ====== K/V base pointers for this KV head ======
{indent}device const char * k_base = (device const char *)k + ikv2*args.nb12 + ikv3*args.nb13;
{indent}device const char * v_base = (device const char *)v + ikv2*args.nb22 + ikv3*args.nb23;

{indent}// Mask pointer (precompute once)
{indent}device const half * mask_ptr = nullptr;
{indent}if (FC_turbo_flash_p1_has_mask) {{
{i2}mask_ptr = (device const half *)(mask + iq1*args.nb31 + (iq2 % args.ne32)*args.nb32 + (iq3 % args.ne33)*args.nb33);
{indent}}}

{indent}// ====== Process all tokens in this block ======
{indent}for (int t = t_start; t < t_end; t++) {{

{i2}// --- Check mask ---
{i2}float mask_val = 0.0f;
{i2}if (FC_turbo_flash_p1_has_mask) {{
{i3}mask_val = (float)mask_ptr[t];
{i3}if (mask_val <= -MAXHALF) {{
{i3}    continue; // masked out
{i3}}}
{i2}}}

{i2}// --- Dequant K and compute Q·K score ---
{i2}device const block_q8_0 * k_row = (device const block_q8_0 *)(k_base + t * args.nb11);

{i2}float dot_partial = 0.0f;
{i2}for (short i = 0; i < DK_PER_LANE; i++) {{
{i3}const int d = (int)lane + i * 32;
{i3}if (d >= DK) break;

{i3}const int qb = d / 32;
{i3}const int qj = d % 32;
{i3}dot_partial += q_vals[i] * (float)k_row[qb].qs[qj] * (float)k_row[qb].d;
{i2}}}
{i2}float score = simd_sum(dot_partial) * args.scale + mask_val;

{i2}// --- Dequant V into shared memory ---
{i2}device const block_turbo3_0 * v_row = (device const block_turbo3_0 *)(v_base + t * args.nb21);
{i2}const float v_norm = float(v_row[0].norm);

{i2}for (int d = (int)lane; d < DV; d += 32) {{
{i3}const int qs_byte = d / 4;
{i3}const int qs_shift = (d % 4) * 2;
{i3}const uint8_t q_idx = (v_row[0].qs[qs_byte] >> qs_shift) & 0x03;

{i3}const int sign_byte = d / 8;
{i3}const int sign_bit = d % 8;
{i3}const uint8_t s_bit = (v_row[0].signs[sign_byte] >> sign_bit) & 1;

{i3}const uint8_t centroid_idx = q_idx | (s_bit << 2);
{i3}shared_v_dec[d] = v_cb[centroid_idx] * v_norm;
{i2}}}
{i2}// Barrier (no-op for 1 SIMD group, but correct)
{i2}threadgroup_barrier(mem_flags::mem_threadgroup);

{i2}// --- Online softmax update + V accumulation ---
{i2}float new_m = max(m_state, score);
{i2}float exp_diff = exp(m_state - new_m);
{i2}float exp_score = exp(score - new_m);

{i2}for (int d = (int)lane; d < DV; d += 32) {{
{i3}shared_o[d] = shared_o[d] * exp_diff + exp_score * shared_v_dec[d];
{i2}}}
{i2}threadgroup_barrier(mem_flags::mem_threadgroup);

{i2}l_state = l_state * exp_diff + exp_score;
{i2}m_state = new_m;
{indent}}}

{indent}// ====== Write partial results ======
{indent}for (int d = (int)lane; d < DV; d += 32) {{
{i2}partial_out[bh_idx * (uint64_t)n_blocks * DV + block_id * DV + d] = shared_o[d];
{indent}}}

{indent}// Lane 0 writes block max and sum
{indent}if (lane == 0) {{
{i2}partial_ms[bh_idx * (uint64_t)n_blocks * 2 + block_id * 2 + 0] = m_state;
{i2}partial_ms[bh_idx * (uint64_t)n_blocks * 2 + block_id * 2 + 1] = l_state;
{indent}}}
"""

# --- Ersetze den Block ---
new_lines = lines[:body_start] + [new_body + '\n'] + lines[body_end:]
content = ''.join(new_lines)

# --- Kommentar-Patches (kurze unique Strings) ---
comment_subs = [
    ("// V4 architecture: 32 threads (1 SIMD group) per block, tokens processed in a loop.",
     "// V4-hybrid architecture: 32 threads (1 SIMD group) per block, shared memory V accum."),
    ("// Pass 1 V4: SIMD-per-token architecture (Eric Kryski pattern)",
     "// Pass 1 V4-hybrid: SIMD-per-token with shared memory V accumulator"),
]

for old, new in comment_subs:
    if old in content:
        content = content.replace(old, new)
        print(f"  ✓ Kommentar: '{old[:55]}...'")
    else:
        print(f"  ⚠ Kommentar nicht gefunden (optional): '{old[:55]}...'")

with open(metal_file, 'w') as f:
    f.write(content)
print(f"  ✓ ggml-metal.metal: Kernel ersetzt ({body_end - body_start} Zeilen → neu)")

# --- Validierung ---
print("")
print("→ Validierung...")
with open(metal_file, 'r') as f:
    final = f.read()

checks_positive = [
    ("shared_o[d] = 0.0f",                          "shared_o Initialisierung"),
    ("shared_v_dec[d] = v_cb[centroid_idx]",         "V decode → shared_v_dec"),
    ("shared_o[d] = shared_o[d] * exp_diff",         "Online softmax in shared_o"),
    ("threadgroup_barrier(mem_flags::mem_threadgroup)", "Barrier vorhanden"),
    ("threadgroup float * shared_o",                  "shared_o Deklaration"),
    ("threadgroup float * shared_v_dec",              "shared_v_dec Deklaration"),
]

checks_negative = [
    ("DV_PER_LANE",     "DV_PER_LANE entfernt"),
    ("o_state[i]",      "Register o_state entfernt"),
    ("v_decoded[i]",    "Register v_decoded entfernt"),
]

all_ok = True
for pattern, label in checks_positive:
    if pattern in final:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label} — fehlt!")
        all_ok = False

for pattern, label in checks_negative:
    if pattern not in final:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ '{pattern}' noch im Code!")
        all_ok = False

# ops.cpp Check
with open("ggml/src/ggml-metal/ggml-metal-ops.cpp", 'r') as f:
    ops_final = f.read()
if "sizeof(float) * 2 * dv" in ops_final:
    print(f"  ✓ ops.cpp: smem_p1 korrekt")
else:
    print(f"  ✗ ops.cpp: smem_p1 fehlt!")
    all_ok = False

if not all_ok:
    print("\nFEHLER: Validierung fehlgeschlagen!")
    sys.exit(1)

print("\nPatch erfolgreich angewendet und validiert!")
PYTHON_PATCH

PATCH_EXIT=$?
if [ $PATCH_EXIT -ne 0 ]; then
    echo ""
    echo -e "${RED}Patch fehlgeschlagen! Zurück auf ${STABLE_COMMIT}...${NC}"
    git checkout "$STABLE_COMMIT" --quiet 2>/dev/null || git reset --hard "$STABLE_COMMIT"
    exit 1
fi

# --- Lokaler Commit ---
echo ""
echo "→ Lokaler Commit..."
git add -A
git commit -m "fix: V4-hybrid — shared memory V accum for M5 Pro

Moves o_state and v_decoded from registers to threadgroup shared memory
(1024 bytes for DV=128) to prevent register spill and OOM on M5 Pro.
K scoring, online softmax logic, and pass 2 interface unchanged.

Applied on top of 6946763 (TurboFlash V4 SIMD-per-token).
" --quiet

PATCHED_SHA=$(git rev-parse --short HEAD)
echo -e "  Neuer Commit: ${GREEN}${PATCHED_SHA}${NC}"

# --- Neubau ---
echo ""
echo "→ Baue llama-server neu..."
echo ""

if [ ! -f "build/CMakeCache.txt" ]; then
    echo "→ CMake configure..."
    cmake -B build -DGGML_METAL=ON -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -3
fi

BUILD_OUTPUT=$(cmake --build build --config Release -j$(sysctl -n hw.logicalcpu) 2>&1)
BUILD_EXIT=$?

echo "$BUILD_OUTPUT" | tail -8

if [ $BUILD_EXIT -eq 0 ]; then
    echo ""
    echo -e "${GREEN}=========================================="
    echo " Build erfolgreich!"
    echo "==========================================${NC}"
    echo ""
    echo "Testen:"
    echo "  ai-llama-fast"
    echo ""
    echo "Erwartetes stderr-Log:"
    echo "  TURBOFLASH: P1 V4-hybrid dispatch grid=(...) tg=(32,1,1) smem=1024"
    echo ""
    echo "Quick-Check (nachdem llama-server läuft):"
    echo '  curl -s http://localhost:8080/v1/chat/completions \'
    echo '    -H "Content-Type: application/json" \'
    echo '    -d '"'"'{"model":"llama","messages":[{"role":"user","content":"Say hello"}],"max_tokens":20}'"'"
    echo ""
    echo -e "Backup:   ${YELLOW}${BACKUP_BRANCH}${NC}"
    echo -e "Patch:    ${GREEN}${PATCHED_SHA}${NC}"
    echo -e "Rollback: git reset --hard ${STABLE_COMMIT} && cmake --build build --config Release -j\$(sysctl -n hw.logicalcpu)"
else
    echo ""
    echo -e "${RED}Build fehlgeschlagen!${NC}"

    if echo "$BUILD_OUTPUT" | grep -qi "metal.*error\|shader.*error"; then
        echo -e "${YELLOW}Metal-Shader-Fehler im Patch:${NC}"
        echo "$BUILD_OUTPUT" | grep -i "error" | head -10
    fi

    echo ""
    echo "→ Rollback..."
    git reset --hard "$STABLE_COMMIT"
    cmake --build build --config Release -j$(sysctl -n hw.logicalcpu) 2>&1 | tail -3
    echo -e "${GREEN}Zurück auf ${STABLE_COMMIT}.${NC}"
    exit 1
fi
