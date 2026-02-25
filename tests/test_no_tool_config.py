"""Test if SDK built-in tools work WITHOUT available_tools configuration"""
import asyncio
import json
from pathlib import Path
from copilot import CopilotClient


async def test_default_tools():
    print("\n" + "="*80)
    print("TEST: SDK BUILT-IN TOOLS WITHOUT CONFIGURATION")
    print("="*80)
    
    # Test directory
    test_dir = Path(__file__).parent.parent / "temp" / "tool_test_2"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    test_file = test_dir / "sample.md"
    test_file.write_text("# Original Title\n\nOriginal content here.\n")
    
    print(f"\n1. Setup:")
    print(f"   File: {test_file}")
    print(f"   Content: {test_file.read_text()}")
    
    # Create session WITHOUT available_tools restriction
    client = CopilotClient()
    
    session_config = {
        "model": "claude-sonnet-4.5",
        "working_directory": str(test_dir),
        "streaming": True
        # NOTE: NO available_tools parameter!
    }
    
    print(f"\n2. Creating Session (no available_tools config):")
    print(f"   Model: {session_config['model']}")
    print(f"   Working Dir: {test_dir}")
    
    session = await client.create_session(session_config)
    
    # Event tracking
    tool_calls = []
    processing_done = asyncio.Event()
    response_text = ""
    
    def on_event(event):
        event_type = event.type.value if hasattr(event.type, 'value') else str(event.type)
        
        nonlocal response_text
        
        if event_type == "assistant.message_delta":
            delta = event.data.delta_content if hasattr(event.data, 'delta_content') else ""
            response_text += delta
        
        elif event_type == "tool.call":
            tool_name = event.data.name if hasattr(event.data, 'name') else "unknown"
            tool_args = event.data.arguments if hasattr(event.data, 'arguments') else {}
            tool_calls.append({'tool': tool_name, 'args': tool_args})
            print(f"   🔧 TOOL CALL: {tool_name}")
            print(f"      Args: {json.dumps(tool_args, indent=8)[:200]}")
        
        elif event_type == "tool.result":
            tool_name = event.data.name if hasattr(event.data, 'name') else "unknown"
            print(f"   ✅ TOOL RESULT: {tool_name}")
        
        elif event_type == "session.idle":
            processing_done.set()
    
    session.on(on_event)
    
    # Send very explicit tool usage request
    prompt = f"""Please use the read_file tool to read {test_file.name}, then use replace_string_in_file to change "Original" to "MODIFIED"."""
    
    print(f"\n3. Sending Prompt:")
    print(f"   '{prompt}'")
    print(f"\n4. Processing...")
    
    try:
        await session.send({"prompt": prompt})
        await asyncio.wait_for(processing_done.wait(), timeout=60.0)
    except asyncio.TimeoutError:
        print("   TIMEOUT!")
    
    # Results
    print(f"\n5. Results:")
    print(f"   Tool Calls: {len(tool_calls)}")
    if tool_calls:
        for call in tool_calls:
            print(f"      - {call['tool']}")
    
    print(f"   Response: {len(response_text)} chars")
    if response_text:
        print(f"      {response_text[:300]}")
    
    final_content = test_file.read_text()
    print(f"\n6. File After:")
    print(f"   Changed: {'MODIFIED' in final_content}")
    print(f"   Content: {final_content}")
    
    print(f"\n" + "="*80)
    if len(tool_calls) > 0:
        print("✅ SUCCESS: Built-in tools called without available_tools config!")
    else:
        print("❌ FAILURE: Built-in tools NOT working even without config")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_default_tools())
