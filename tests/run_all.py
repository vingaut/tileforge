#!/usr/bin/env python3
"""Lance toute la batterie de tests de TileForge.

    python tests/run_all.py
"""

from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    modules = sorted(p.stem for p in HERE.glob("test_*.py"))
    total = failures = 0
    for name in modules:
        module = importlib.import_module(name)
        tests = [(n, f) for n, f in vars(module).items()
                 if n.startswith("test_") and callable(f)]
        if not tests:
            continue
        print(f"\n{name}")
        for test_name, function in tests:
            total += 1
            try:
                function()
                print(f"  [ok] {test_name}")
            except AssertionError as exc:
                failures += 1
                print(f"  [!!] {test_name} : {exc}")
            except Exception:
                failures += 1
                print(f"  [!!] {test_name} : erreur inattendue")
                traceback.print_exc()
    print(f"\n{total} test(s), {failures} échec(s)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
