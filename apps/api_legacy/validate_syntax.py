"""
Syntax validation for Navis backend refactoring.
Checks that all Python files compile without syntax errors.
"""

import py_compile
import sys
from pathlib import Path

# All new/modified files to validate
FILES_TO_CHECK = [
    # New provider layer
    "services/providers/__init__.py",
    "services/providers/base.py",
    "services/providers/geo.py",
    "services/providers/places.py",
    "services/providers/transit.py",
    "services/providers/events.py",
    "services/providers/wiki.py",
    "services/provider_manager.py",
    # Modified core files
    "agents/orchestrator.py",
    "services/fusion.py",
]


def validate_syntax():
    """Check all files compile successfully."""
    print("\n" + "="*60)
    print("NAVIS REFACTORING SYNTAX VALIDATION")
    print("="*60 + "\n")
    
    results = []
    for filepath in FILES_TO_CHECK:
        full_path = Path(filepath)
        if not full_path.exists():
            print(f"[SKIP] {filepath:50} (file not found)")
            continue
        
        try:
            py_compile.compile(str(full_path), doraise=True)
            print(f"[PASS] {filepath:50} ({full_path.stat().st_size} bytes)")
            results.append((filepath, True))
        except py_compile.PyCompileError as e:
            print(f"[FAIL] {filepath:50}")
            print(f"       Error: {e}")
            results.append((filepath, False))
        except Exception as e:
            print(f"[FAIL] {filepath:50}")
            print(f"       Error: {type(e).__name__}: {e}")
            results.append((filepath, False))
    
    # Summary
    print("\n" + "="*60)
    print("VALIDATION SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    print(f"\nResult: {passed}/{total} files passed syntax validation")
    
    if passed == total and total > 0:
        print("\nSUCCESS: All files compiled successfully!")
        print("="*60 + "\n")
        return 0
    else:
        print(f"\nFAILED: {total - passed} file(s) have syntax errors")
        print("="*60 + "\n")
        return 1


if __name__ == "__main__":
    exit_code = validate_syntax()
    sys.exit(exit_code)
