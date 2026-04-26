#!/usr/bin/env python3
"""
Fix 7 - Scale direkt im Metal Kernel (turbo_flash.metal + MLXFast.swift)
Verschiebt Scale-Op aus Swift in den Metal Kernel für ~2 tok/s Gewinn.
"""

import os
import re
import glob

MLX_SWIFT_PATH = os.path.expanduser("~/mlx-swift")

# ─── 1. turbo_flash.metal ───────────────────────────────────────────────────

def patch_metal(path):
    if not os.path.exists(path):
        print(f"SKIP (not found): {path}")
        return 0

    with open(path, "r") as f:
        src = f.read()

    changes = 0

    # Add scale buffer(14) to kernel signature if not present
    buf13_pattern = r'(constant\s+float\s*\*\s*q_vals\s*\[\[buffer\(13\)\]\])'
    buf14 = ', constant float& scale [[buffer(14)]]'
    if 'buffer(14)' not in src and re.search(buf13_pattern, src):
        src = re.sub(buf13_pattern, r'\1' + buf14, src)
        changes += 1
        print(f"Metal buffer(13) pattern: 1 Treffer")
    else:
        print(f"Metal buffer(13) pattern: 0 Treffer")

    # Scale q_vals in single-row load
    q_single = r'(float\s+q\s*=\s*q_vals\[q_row\s*\*\s*D\s*\+\s*d\];)'
    if re.search(q_single, src) and 'q * scale' not in src:
        src = re.sub(q_single, r'\1\n    q = q * scale;', src)
        changes += 1
        print(f"q_vals single-row pattern: 1 Treffer")
    else:
        print(f"q_vals single-row pattern: 0 Treffer")

    # Scale q_vals in NR0 multi-row load
    q_nr0 = r'(float\s+q\s*=\s*q_vals\[nr\s*\*\s*D\s*\+\s*d\];)'
    if re.search(q_nr0, src) and 'q * scale' not in src:
        src = re.sub(q_nr0, r'\1\n        q = q * scale;', src)
        changes += 1
        print(f"q_vals NR0 multi-row pattern: 1 Treffer")
    else:
        print(f"q_vals NR0 multi-row pattern: 0 Treffer")

    with open(path, "w") as f:
        f.write(src)

    print(f"Metal: OK ({changes} buf, 0 single, 0 NR0)")
    return changes

# ─── 2. MLXFast.swift ────────────────────────────────────────────────────────

def patch_swift(path):
    if not os.path.exists(path):
        print(f"SKIP (not found): {path}")
        return 0

    with open(path, "r") as f:
        src = f.read()

    changes = 0

    # Remove qScaled manual scaling
    qscaled_pattern = r'\s*let\s+qScaled\s*=\s*qRot\s*\*\s*Float\(1\.0\s*/\s*Float\(dim\)\.squareRoot\(\)\)\s*\n'
    if re.search(qscaled_pattern, src):
        src = re.sub(qscaled_pattern, '\n', src)
        changes += 1

    # Replace qScaled with qRot in function call
    if 'qScaled' in src:
        src = src.replace('qScaled', 'qRot')
        changes += 1

    with open(path, "w") as f:
        f.write(src)

    print(f"Swift: OK ({changes} Ersetzungen, qScaled entfernt)")
    return changes

# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Metal kernel paths - both in mlx-swift and DerivedData
    metal_paths = glob.glob(
        os.path.join(MLX_SWIFT_PATH, "Source/Cmlx/mlx/mlx/backend/metal/kernels/turbo_flash.metal")
    ) + glob.glob(
        os.path.expanduser("~/Library/Developer/Xcode/DerivedData/mlx-swift-lm-*/SourcePackages/checkouts/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/turbo_flash.metal")
    )

    swift_paths = glob.glob(
        os.path.join(MLX_SWIFT_PATH, "Source/MLX/MLXFast.swift")
    ) + glob.glob(
        os.path.expanduser("~/Library/Developer/Xcode/DerivedData/mlx-swift-lm-*/SourcePackages/checkouts/mlx-swift/Source/MLX/MLXFast.swift")
    )

    for p in metal_paths:
        print(f"\nPatching Metal: {p}")
        patch_metal(p)

    for p in swift_paths:
        print(f"\nPatching Swift: {p}")
        patch_swift(p)

    if not metal_paths and not swift_paths:
        print("WARN: Keine Dateien gefunden. MLX_SWIFT_PATH korrekt?")
        print(f"  MLX_SWIFT_PATH={MLX_SWIFT_PATH}")

    print("\nFertig. Jetzt C++ und C-Header patchen (Schritt 2).")
