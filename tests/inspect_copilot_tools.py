"""
Utility script to inspect available GitHub Copilot SDK built-in tools
"""
import inspect
from copilot import CopilotClient
from copilot.types import SessionConfig


def inspect_copilot_sdk():
    """Inspect the Copilot SDK to discover available built-in tools"""
    
    print("=" * 80)
    print("GITHUB COPILOT SDK INSPECTION")
    print("=" * 80)
    
    # Create client instance
    client = CopilotClient()
    
    # 1. Inspect CopilotClient
    print("\n1. CopilotClient Methods:")
    print("-" * 40)
    for attr in dir(client):
        if not attr.startswith('_') and callable(getattr(client, attr)):
            method = getattr(client, attr)
            sig = inspect.signature(method) if hasattr(method, '__call__') else None
            print(f"  • {attr}{sig if sig else ''}")
    
    # 2. Inspect create_session signature
    print("\n2. create_session Parameters:")
    print("-" * 40)
    sig = inspect.signature(client.create_session)
    for name, param in sig.parameters.items():
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else "Any"
        default = f" = {param.default}" if param.default != inspect.Parameter.empty else ""
        print(f"  • {name}: {annotation}{default}")
    
    # 2b. Inspect SessionConfig type
    print("\n2b. SessionConfig Type Structure:")
    print("-" * 40)
    if hasattr(SessionConfig, '__annotations__'):
        print("  SessionConfig fields (TypedDict):")
        for field, field_type in SessionConfig.__annotations__.items():
            print(f"    • {field}: {field_type}")
    else:
        print("  SessionConfig structure not available via annotations")
    
    # 3. Try to get available_tools from SDK documentation
    print("\n3. Checking for Built-in Tools Documentation:")
    print("-" * 40)
    
    # Check if there's a __doc__ or help available
    if client.create_session.__doc__:
        print(client.create_session.__doc__)
    else:
        print("  No docstring available")
    
    # 4. Known built-in tools from GitHub Copilot SDK
    print("\n4. Known Built-in Tools (from SDK documentation/usage):")
    print("-" * 40)
    known_tools = [
        "read_file",
        "write_file", 
        "replace_string_in_file",
        "multi_replace_string_in_file",
        "list_dir",
        "grep_search",
        "file_search",
        "semantic_search",
        "view",
        "run_in_terminal",
        "get_terminal_output"
    ]
    
    print("  These tools are typically available when you create a session")
    print("  with 'available_tools' parameter:\n")
    for tool in known_tools:
        print(f"  • {tool}")
    
    # 5. Current configuration
    print("\n5. Current Project Configuration:")
    print("-" * 40)
    try:
        import sys
        from pathlib import Path
        # Add src to path if not already there
        src_path = Path(__file__).parent / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))
        
        import config
        print(f"  COPILOT_ALLOWED_BUILTIN_TOOLS:")
        for tool in config.COPILOT_ALLOWED_BUILTIN_TOOLS:
            print(f"    • {tool}")
        print(f"\n  COPILOT_ENABLE_CUSTOM_TOOLS: {config.COPILOT_ENABLE_CUSTOM_TOOLS}")
    except Exception as e:
        print(f"  Error loading config: {e}")
    
    print("\n" + "=" * 80)
    print("HOW TO ENABLE TOOLS IN YOUR SESSION")
    print("=" * 80)
    print("""
When creating a session, use the 'available_tools' parameter:

    session_config = {
        "available_tools": [
            "read_file",
            "replace_string_in_file",
            "multi_replace_string_in_file",
            "list_dir",
            "grep_search"
        ]
    }
    
    session = await client.create_session(**session_config)

The AI will then have access to these tools and can use them during conversations.
    """)
    
    print("=" * 80)


if __name__ == "__main__":
    inspect_copilot_sdk()
