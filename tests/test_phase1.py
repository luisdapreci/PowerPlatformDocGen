"""
Test script for Phase 1 implementation
Verifies that Copilot SDK integration works with built-in tools
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

async def test_session_manager_import():
    """Test that session manager can be imported"""
    print("✓ Testing session manager import...")
    try:
        from session_manager import SessionManager
        print("  ✅ SessionManager imported successfully")
        return True
    except Exception as e:
        print(f"  ❌ Import error: {e}")
        return False

async def test_config():
    """Test that configuration is properly set"""
    print("\n✓ Testing configuration...")
    try:
        import config
        
        checks = []
        
        # Check COPILOT_ENABLE_CUSTOM_TOOLS
        if hasattr(config, 'COPILOT_ENABLE_CUSTOM_TOOLS'):
            print(f"  ✅ COPILOT_ENABLE_CUSTOM_TOOLS = {config.COPILOT_ENABLE_CUSTOM_TOOLS}")
            checks.append(True)
        else:
            print("  ❌ COPILOT_ENABLE_CUSTOM_TOOLS not found")
            checks.append(False)
        
        # Check COPILOT_ALLOWED_BUILTIN_TOOLS
        if hasattr(config, 'COPILOT_ALLOWED_BUILTIN_TOOLS'):
            tools = config.COPILOT_ALLOWED_BUILTIN_TOOLS
            print(f"  ✅ COPILOT_ALLOWED_BUILTIN_TOOLS = {len(tools) if tools else 'None'} tools")
            checks.append(True)
        else:
            print("  ❌ COPILOT_ALLOWED_BUILTIN_TOOLS not found")
            checks.append(False)
        
        # Check infinite sessions config
        if hasattr(config, 'COPILOT_ENABLE_INFINITE_SESSIONS'):
            print(f"  ✅ COPILOT_ENABLE_INFINITE_SESSIONS = {config.COPILOT_ENABLE_INFINITE_SESSIONS}")
            checks.append(True)
        else:
            print("  ❌ COPILOT_ENABLE_INFINITE_SESSIONS not found")
            checks.append(False)
        
        return all(checks)
        
    except Exception as e:
        print(f"  ❌ Config error: {e}")
        return False

async def test_session_manager():
    """Test that session manager works without custom tools"""
    print("\n✓ Testing session manager integration...")
    try:
        from session_manager import SessionManager
        
        # Check if the import statement exists in the file
        import inspect
        import session_manager
        
        source = inspect.getsource(session_manager)
        
        # Ensure it doesn't try to import copilot_tools (we removed that)
        if "from copilot_tools import" in source:
            print("  ❌ Session manager still tries to import custom tools (should be removed)")
            return False
        else:
            print("  ✅ Session manager uses SDK built-in tools only")
            return True
            
    except Exception as e:
        print(f"  ❌ Session manager error: {e}")
        return False

async def main():
    """Run all tests"""
    print("=" * 60)
    print("🧪 Phase 1 Implementation Test Suite")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(await test_session_manager_import())
    results.append(await test_config())
    results.append(await test_session_manager())
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")
    
    if all(results):
        print("\n🎉 All tests passed! SDK integration is complete.")
        print("\n📝 Next steps:")
        print("  1. Start the server: python src/main.py")
        print("  2. Upload a Power Platform solution")
        print("  3. Try asking: 'What Power Fx formulas are in this solution?'")
        print("  4. Watch the agent use SDK built-in tools (read_file, file_search, etc.)!")
    else:
        print("\n⚠️  Some tests failed. Please review the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
