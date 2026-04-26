#!/usr/bin/env python3
"""
Fix 7 - C-Bridge Signaturen (mlx-c/fast.cpp + include/fast.h) alignen
Stellt sicher dass C-Bridge float scale korrekt weiterreicht.
"""

import os
import re
import glob

MLX_SWIFT_PATH = os.path.expanduser("~/mlx-swift")

def find_cbridge_files():
    base = MLX_SWIFT_PATH
    derived = os.path.expanduser(
        "~/Library/Developer/Xcode/DerivedData/mlx-swift-lm-*/SourcePackages/checkouts/mlx-swift"
    )
    files = []
    for root in [base] + glob.glob(derived):
        candidates = [
            os.path.join(root, "Source/Cmlx/mlx-c/mlx-c/fast.cpp"),
            os.path.join(root, "Source/Cmlx/mlx-c/mlx/c/fast.h"),
            os.path.join(root, "Source/Cmlx/include/mlx-c/fast.h"),
        ]
        for c in candidates:
            if os.path.exists(c):
                files.append(c)
    return list(set(files))

def patch_cbridge(path):
    with open(path, "r") as f:
        src = f.read()

    # Pattern: mlx_fast_turbo_flash_attention C signature
    # Add float scale after mlx_array q_rot
    pattern = r'(mlx_fast_turbo_flash_attention[^)]*mlx_array\s+q_rot)(\s*,\s*(?!float\s+scale)(?!mlx_array\s+scale))'
    count = len(re.findall(pattern, src))

    if count == 0:
        print(f"  mlx-c/fast.cpp Signaturen: 0 Treffer (bereits gepatcht)")
        return 0

    src = re.sub(pattern, r'\1, float scale\2', src)

    with open(path, "w") as f:
        f.write(src)

    print(f"  mlx-c/fast.cpp Signaturen: {count} Treffer")
    return count

if __name__ == "__main__":
    files = find_cbridge_files()

    if not files:
        print("WARN: Keine C-Bridge Dateien gefunden")
        exit(0)

    for path in files:
        print(f"\nPatching: {path}")
        patch_cbridge(path)

    print("\nC-Bridge Signaturen aligned.")
