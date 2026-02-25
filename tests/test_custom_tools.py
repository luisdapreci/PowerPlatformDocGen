"""Test custom file editing tools"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from copilot import CopilotClient
from file_edit_tools import FILE_EDIT_TOOLS


async def test_custom_tools():
    print("\n" + "="*80)
    print("TEST: CUSTOM FILE EDITING TOOLS")
    print("="*80)
    
    # Setup test file
    test_dir = Path(__file__).parent.parent / "temp" / "custom_tools_test"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    test_file = test_dir / "test.md"
    test_file.write_text("# Test\n\nThis is ORIGINAL text.\n")
    
    print(f"\n1. Setup:")
    print(f"   File: {test_file}")
    print(f"   Initial: {test_file.read_text()}")
    
    # Create client and session with custom tools
    client = CopilotClient()
    
    session_config = {
        "model": "claude-sonnet-4.5",
        "streaming": True,
        "tools": FILE_EDIT_TOOLS,  # Custom tools!
    }
    
    print(f"\n2. Creating Session:")
    print(f"   Custom Tools: {[t.name for t in FILE_EDIT_TOOLS]}")
    
    session = await client.create_session(session_config)
    
    # Track events
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
            tool_calls.append(tool_name)
            print(f"   🔧 TOOL CALL: {tool_name}")
        
        elif event_type == "tool.result":
            tool_name = event.data.name if hasattr(event.data, 'name') else "unknown"
            result = event.data.result if hasattr(event.data, 'result') else {}
            result_text = result.get('textResultForLlm', '') if isinstance(result, dict) else str(result)
            print(f"   ✅ TOOL RESULT: {tool_name}")
            print(f"      {result_text[:100]}")
        
        elif event_type == "session.idle":
            processing_done.set()
    
    session.on(on_event)
    
    # Send request
    prompt = f"Use read_file to read {test_file.name}, then use replace_string_in_file to change 'ORIGINAL' to 'MODIFIED'."
    
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
    print(f"   Tool Calls: {len(tool_calls)} - {tool_calls if tool_calls else 'NONE'}")
    print(f"   Response: {len(response_text)} chars")
    if response_text:
        print(f"   AI Said: {response_text}")
    
    final_content = test_file.read_text()
    print(f"\n6. File After:")
    print(f"   Changed: {'MODIFIED' in final_content}")
    print(f"   Content: {final_content}")
    
    print(f"\n" + "="*80)
    if len(tool_calls) > 0 and 'MODIFIED' in final_content:
        print("✅ SUCCESS: Custom tools work and file was edited!")
    elif len(tool_calls) > 0:
        print("⚠️  PARTIAL: Tools were called but edit failed")
    else:
        print("❌ FAILURE: Tools not called")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_custom_tools())
