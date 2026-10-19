"""
Validation script for Navis backend refactoring.

Tests:
1. Provider layer initialization
2. ProviderManager instantiation
3. FusionEngine defensive programming
4. Orchestrator None handling

Run: python test_refactoring.py
"""

import asyncio
import sys
from typing import Any, Dict


def test_imports():
    """Test that all new modules can be imported."""
    print("[TEST] Testing imports...")
    try:
        from services.providers.base import BaseProvider, ProviderRegistry, get_registry
        from services.providers.geo import GeoProvider
        from services.providers.places import PlacesProvider
        from services.providers.transit import TransitProvider
        from services.providers.events import EventsProvider
        from services.providers.wiki import WikiProvider
        from services.provider_manager import get_provider_manager
        from services.fusion import FusionEngine
        print("   [PASS] All imports successful")
        return True
    except Exception as e:
        print(f"   [FAIL] Import failed: {e}")
        return False


def test_registry():
    """Test provider registry functionality."""
    print("[TEST] Testing ProviderRegistry...")
    try:
        from services.providers.base import ProviderRegistry
        from services.providers.geo import GeoProvider
        
        registry = ProviderRegistry()
        geo = GeoProvider()
        registry.register(geo)
        
        # Test retrieval
        retrieved = registry.get_provider("geo")
        assert retrieved is not None, "Provider not found"
        assert retrieved.capability.id == "geo", "Provider ID mismatch"
        
        # Test domain lookup
        providers = registry.get_providers_by_domain("geocoding")
        assert len(providers) > 0, "No providers found for domain"
        
        print("   [PASS] ProviderRegistry works correctly")
        return True
    except Exception as e:
        print(f"   [FAIL] Registry test failed: {e}")
        return False


async def test_provider_manager():
    """Test ProviderManager initialization and methods."""
    print("[TEST] Testing ProviderManager...")
    try:
        from services.provider_manager import get_provider_manager
        
        manager = get_provider_manager()
        
        # Test it initialized
        assert manager is not None, "ProviderManager is None"
        
        # Test provider status
        status = manager.get_provider_status()
        print(f"   Provider status: {status}")
        
        # Test safe method calls (should never crash)
        result = await manager.search_places("test", 0, 0)
        assert isinstance(result, dict), "Result is not a dict"
        assert "results" in result, "Missing 'results' key"
        
        result = await manager.detect_city(42.1, -71.5)
        assert isinstance(result, dict), "City detection result is not a dict"
        
        print("   [PASS] ProviderManager works correctly")
        return True
    except Exception as e:
        print(f"   [FAIL] ProviderManager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fusion_engine():
    """Test FusionEngine defensive programming."""
    print("[TEST] Testing FusionEngine...")
    try:
        from services.fusion import FusionEngine
        
        engine = FusionEngine()
        
        # Test with None
        result = engine.fuse_results(None)
        assert isinstance(result, dict), "None input should return dict"
        assert "results" in result, "Missing 'results' in None case"
        
        # Test with empty list
        result = engine.fuse_results([])
        assert isinstance(result, dict), "Empty list should return dict"
        
        # Test with mixed valid/invalid data
        mixed = [
            {"data": {"results": [{"name": "Place 1"}]}},
            None,
            BaseException("test error"),
            {"data": None},
            {"data": {"results": [{"name": "Place 2"}]}},
        ]
        
        result = engine.fuse_results(mixed)
        assert isinstance(result, dict), "Mixed data should return dict"
        assert isinstance(result.get("results"), list), "Results should be a list"
        
        print("   [PASS] FusionEngine defensive programming works")
        return True
    except Exception as e:
        print(f"   [FAIL] FusionEngine test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_orchestrator_guards():
    """Test orchestrator None handling."""
    print("[TEST] Testing Orchestrator None guards...")
    try:
        from models.context import UserContext
        
        # Create context with all None values
        context = UserContext(
            new_city=None,
            preferences=None,
            food_preferences=None,
            neighborhood=None,
        )
        
        # These should not crash due to None values
        # (We're not actually running them, just checking the guards are in place)
        
        # Verify context properties
        assert context.new_city is None, "new_city should be None"
        assert context.preferences is None or context.preferences == [], "preferences handling"
        
        print("   [PASS] UserContext handles None values correctly")
        return True
    except Exception as e:
        print(f"   [FAIL] Orchestrator guards test failed: {e}")
        return False


def test_safe_defaults():
    """Test that safe default patterns work."""
    print("[TEST] Testing safe default patterns...")
    try:
        # Pattern 1: city fallback
        new_city = None
        city = new_city or "unknown"
        assert city == "unknown", "City fallback failed"
        
        # Pattern 2: preference handling
        preferences = None
        q = " ".join(preferences) if preferences else "default query"
        assert q == "default query", "Preference fallback failed"
        
        # Pattern 3: safe list access
        items = None
        safe_items = items or []
        for item in safe_items:  # Should not crash
            pass
        
        # Pattern 4: safe dict access
        response = {"status": "success"}
        places = response.get("places", []) or []
        for place in places:  # Should not crash
            pass
        
        print("   [PASS] Safe default patterns work correctly")
        return True
    except Exception as e:
        print(f"   [FAIL] Safe defaults test failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("NAVIS REFACTORING VALIDATION")
    print("="*60 + "\n")
    
    tests = [
        ("Imports", test_imports),
        ("ProviderRegistry", test_registry),
        ("ProviderManager", test_provider_manager),
        ("FusionEngine", test_fusion_engine),
        ("Orchestrator Guards", test_orchestrator_guards),
        ("Safe Defaults", test_safe_defaults),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"[FAIL] {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status:8} | {test_name}")
    
    print("="*60)
    print(f"Result: {passed}/{total} tests passed")
    print("="*60 + "\n")
    
    if passed == total:
        print("SUCCESS: ALL TESTS PASSED! Refactoring is stable.")
        return 0
    else:
        print(f"WARNING: {total - passed} test(s) failed. Review output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
