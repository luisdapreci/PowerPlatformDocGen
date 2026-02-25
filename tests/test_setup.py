"""Test script to verify setup and dependencies"""
import sys
import asyncio
from pathlib import Path

async def test_setup():
    """Test that all prerequisites are met"""
    results = {
        "Python": False,
        "Dependencies": False,
        "Copilot SDK": False,
        "Copilot CLI": False,
        "PAC CLI": False
    }
    
    # Test Python version
    print("Testing Python version...")
    if sys.version_info >= (3, 10):
        print(f"✓ Python {sys.version.split()[0]} - OK")
        results["Python"] = True
    else:
        print(f"✗ Python {sys.version.split()[0]} - Need 3.10+")
    
    # Test required packages
    print("\nTesting Python packages...")
    try:
        import fastapi
        import uvicorn
        import copilot
        import yaml
        import lxml
        print("✓ All required Python packages installed")
        results["Dependencies"] = True
    except ImportError as e:
        print(f"✗ Missing package: {e.name}")
    
    # Test Copilot SDK client creation
    print("\nTesting Copilot SDK...")
    try:
        from copilot import CopilotClient
        import subprocess
        
        # First check if Copilot CLI is available
        try:
            cli_result = subprocess.run(
                ["copilot", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if cli_result.returncode == 0:
                print(f"✓ GitHub Copilot CLI installed: {cli_result.stdout.strip()}")
                results["Copilot CLI"] = True
            else:
                print("⚠ Copilot CLI found but returned error")
        except FileNotFoundError:
            print("✗ GitHub Copilot CLI not found")
            print("  Install from: https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli")
        except Exception as e:
            print(f"⚠ Copilot CLI check error: {e}")
        
        # Now test SDK client
        client = CopilotClient()
        print("✓ Copilot SDK client created successfully")
        results["Copilot SDK"] = True
        
        await client.stop()
        
    except Exception as e:
        print(f"✗ Copilot SDK error: {e}")
        print("  Make sure GitHub Copilot CLI is installed:")
        print("  https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli")
    
    # Test PAC CLI
    print("\nTesting Power Platform CLI...")
    try:
        import subprocess
        result = subprocess.run(
            ["pac"],
            capture_output=True,
            text=True,
            timeout=10
        )
        # PAC CLI returns exit code 1 even when working (showing help)
        if "Microsoft PowerPlatform CLI" in result.stdout or "Microsoft PowerPlatform CLI" in result.stderr:
            # Try to extract version from output
            for line in result.stdout.split('\n'):
                if 'Version:' in line:
                    print(f"✓ PAC CLI installed: {line.strip()}")
                    break
            else:
                print("✓ PAC CLI installed and working")
            results["PAC CLI"] = True
        else:
            print("✗ PAC CLI found but not responding correctly")
    except FileNotFoundError:
        print("✗ PAC CLI not found in PATH")
        print("  Install with: dotnet tool install --global Microsoft.PowerApps.CLI.Tool")
    except Exception as e:
        print(f"✗ PAC CLI error: {e}")
    
    # Summary
    print("\n" + "="*50)
    print("SETUP SUMMARY")
    print("="*50)
    
    for component, status in results.items():
        symbol = "✓" if status else "✗"
        print(f"{symbol} {component}")
    
    all_good = all(results.values())
    
    if all_good:
        print("\n🎉 All components are ready!")
        print("Run: python main.py")
        print("Then open: http://localhost:8000/static/index.html")
    else:
        print("\n⚠ Some components need attention (see above)")
        if not results["Copilot CLI"]:
            print("\n⚠ CRITICAL: Copilot CLI is required for this application to work")
    
    return all_good

if __name__ == "__main__":
    try:
        success = asyncio.run(test_setup())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
