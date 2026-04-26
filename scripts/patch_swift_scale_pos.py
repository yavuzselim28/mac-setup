#!/usr/bin/env python3
"""
Fix 7 - Swift scale Position: Float(1/sqrt(dim)) direkt im C-Aufruf
Entfernt qScaled Variable, übergibt scale direkt an C-Bridge.
"""

import os
import re
import glob

MLX_SWIFT_PATH = os.path.expanduser("~/mlx-swift")

def find_swift_files():
    base = MLX_SWIFT_PATH
    derived = os.path.expanduser(
        "~/Library/Developer/Xcode/DerivedData/mlx-swift-lm-*/SourcePackages/checkouts/mlx-swift"
    )
    files = []
    for root in [base] + glob.glob(derived):
        candidate = os.path.join(root, "Source/MLX/MLXFast.swift")
        if os.path.exists(candidate):
            files.append(candidate)
    return list(set(files))

def patch_swift_scale(path):
    with open(path, "r") as f:
        src = f.read()

    changes = 0

    # Pattern 1: Remove qScaled = qRot * Float(1.0 / Float(dim).squareRoot())
    qscaled_decl = r'\s*let\s+qScaled\s*=\s*qRot\s*\*\s*Float\s*\(\s*1\.0\s*/\s*Float\s*\(\s*dim\s*\)\s*\.squareRoot\s*\(\s*\)\s*\)\s*\n'
    count1 = len(re.findall(qscaled_decl, src))
    if count1 > 0:
        src = re.sub(qscaled_decl, '\n', src)
        changes += count1

    # Pattern 2: Replace qScaled with qRot in C call
    if 'qScaled' in src:
        src = src.replace('qScaled', 'qRot')
        changes += 1

    # Pattern 3: Add scale: Float(1.0 / sqrt(Float(dim))) to C call if missing
    # Find turboFlashAttention C call and add scale parameter
    c_call_pattern = r'(turboFlashAttention[^)]*qRot\s*,\s*)(?!scale\s*:)(?!Float)'
    if re.search(c_call_pattern, src):
        # Get dim from context - inject scale calculation
        src = re.sub(
            r'(turboFlashAttention[^)]*,\s*qRot\s*)(,)',
            r'\1, Float(1.0 / Float(dim).squareRoot())\2',
            src
        )
        changes += 1

    with open(path, "w") as f:
        f.write(src)

    print(f"  Swift scale Position: {changes} Treffer")
    return changes

if __name__ == "__main__":
    files = find_swift_files()

    if not files:
        print("WARN: MLXFast.swift nicht gefunden")
        exit(0)

    for path in files:
        print(f"\nPatching: {path}")
        patch_swift_scale(path)

    print("\nSwift scale Position gepatcht.")
