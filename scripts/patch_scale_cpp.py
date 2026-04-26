#!/usr/bin/env python3
"""
Fix 7 - C++ API: mlx/fast.h + fast.cpp + mlx-c/fast.h + mlx-c/fast.cpp
Fügt float scale Parameter nach q_rot in allen 4 Signaturen ein.
"""

import os
import re
import glob

MLX_SWIFT_PATH = os.path.expanduser("~/mlx-swift")

def find_files():
    base = MLX_SWIFT_PATH
    derived = os.path.expanduser(
        "~/Library/Developer/Xcode/DerivedData/mlx-swift-lm-*/SourcePackages/checkouts/mlx-swift"
    )
    paths = {}
    for root in [base] + glob.glob(derived):
        candidates = {
            "fast_h":    os.path.join(root, "Source/Cmlx/mlx/mlx/fast.h"),
            "fast_cpp":  os.path.join(root, "Source/Cmlx/mlx/mlx/fast.cpp"),
            "mlxc_h":    os.path.join(root, "Source/Cmlx/mlx-c/mlx/c/fast.h"),
            "mlxc_cpp":  os.path.join(root, "Source/Cmlx/mlx-c/mlx-c/fast.cpp"),
        }
        for k, v in candidates.items():
            if os.path.exists(v) and k not in paths:
                paths[k] = v
    return paths

def patch_file(path, pattern, replacement, label):
    if not os.path.exists(path):
        print(f"  SKIP (not found): {path}")
        return 0
    with open(path, "r") as f:
        src = f.read()
    count = len(re.findall(pattern, src))
    if count == 0:
        print(f"  {label}: 0 Treffer (bereits gepatcht oder Pattern nicht gefunden)")
        return 0
    src = re.sub(pattern, replacement, src)
    with open(path, "w") as f:
        f.write(src)
    print(f"  {label}: {count} Treffer")
    return count

if __name__ == "__main__":
    files = find_files()

    if not files:
        print("ERROR: Keine MLX Dateien gefunden!")
        print(f"  MLX_SWIFT_PATH={MLX_SWIFT_PATH}")
        exit(1)

    # Pattern: turbo_flash_attention signature - add scale after q_rot
    # Matches: ..., const array& q_rot, ...
    # Replaces with: ..., const array& q_rot, float scale, ...
    sig_pattern = r'(turbo_flash_attention[^)]*const\s+array\s*&\s*q_rot)(\s*,\s*(?!float\s+scale))'
    sig_replacement = r'\1, float scale\2'

    for label, path in files.items():
        print(f"\n{label}: {path}")
        patch_file(path, sig_pattern, sig_replacement, label)

    # Also patch fast.cpp implementation body to pass scale to kernel
    if "fast_cpp" in files:
        path = files["fast_cpp"]
        with open(path, "r") as f:
            src = f.read()
        # Add scale to kernel launch if not present
        kernel_pattern = r'(turbo_flash_p1[^;]*q_rot[^;]*)(;)'
        if re.search(kernel_pattern, src) and 'scale' not in src[src.find('turbo_flash_p1'):src.find('turbo_flash_p1')+500]:
            src = re.sub(kernel_pattern, r'\1, array(scale, float32)\2', src)
            with open(path, "w") as f:
                f.write(src)
            print(f"  fast.cpp kernel launch: patched")

    print("\nAlle Patches angewendet.")
