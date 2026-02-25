"""Debug test to monitor SDK tool call events"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from copilot import CopilotClient
import config


async def test_tool_calls():
    """Test that monitors tool call events in streaming mode"""
    
    print("\n" + "="*80)
    print("TOOL CALL DEBUG TEST")
    print("="*80)
    
    # Create test directory
    test_dir = Path(__file__).parent.parent / "temp" / "tool_debug"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a simple test file
    test_file = test_dir / "test_doc.md"
    test_file.write_text("# Test Document\n\nThis is placeholder text.\n")
    
    print(f"\n1. Test Setup:")
    print(f"   Working Directory: {test_dir}")
    print(f"   Test File: {test_file}")
    print(f"   File Size: {test_file.stat().st_size} bytes")
    
    # Create Copilot client and session
    client = CopilotClient()
    
    session_config = {
        "model": "claude-sonnet-4.5",
        "working_directory": str(test_dir),
        "streaming": True,  # MUST use streaming to see tool calls
        "available_tools": [
            "read_file",
            "replace_string_in_file",
            "list_dir"
        ],
        "system_message": {
            "mode": "append",
            "content": f"""You are a file editing assistant.

[!] CRITICAL: USE TOOLS TO EDIT FILES

Your task is to edit the file at: {test_file}

DO NOT write conversational responses.
DO NOT explain what you will do.

YOUR FIRST ACTION MUST BE:
read_file(filePath="{test_file}", startLine=1, endLine=10)

Then immediately use replace_string_in_file to change "placeholder" to "EDITED BY AI".

[X] INVALID: "I'll read the file..."
[OK] VALID: [Immediate tool call]"""
        }
    }
    
    print(f"\n2. Creating Session:")
    print(f"   Model: {session_config['model']}")
    print(f"   Streaming: {session_config['streaming']}")
    print(f"   Tools: {session_config['available_tools']}")
    
    session = await client.create_session(session_config)
    
    # Send prompt and monitor events
    print(f"\n3. Sending Prompt:")
    print(f"   Prompt: 'Edit the test document now.'")
    
    events_received = []
    tool_calls = []
    tool_results = []
    response_text = ""
    processing_done = asyncio.Event()
    
    # Event handler to capture SDK events
    def on_event(event):
        event_type = event.type.value if hasattr(event.type, 'value') else str(event.type)
        events_received.append(event_type)
        
        try:
            if event_type == "assistant.message_delta":
                delta_content = event.data.delta_content if hasattr(event.data, 'delta_content') else ""
                nonlocal response_text
                response_text += delta_content
                if delta_content:
                    print(f"{delta_content}", end='', flush=True)
            
            elif event_type == "assistant.message":
                content = event.data.content if hasattr(event.data, 'content') else ""
                print(f"\n   📨 MESSAGE: {len(content)} chars")
            
            elif event_type == "tool.call":
                tool_name = event.data.name if hasattr(event.data, 'name') else "unknown"
                tool_args = event.data.arguments if hasattr(event.data, 'arguments') else {}
                tool_calls.append({
                    'tool': tool_name,
                    'args': tool_args
                })
                print(f"\n   🔧 TOOL CALL: {tool_name}")
                if tool_args:
                    print(f"      Args: {json.dumps(tool_args, indent=6)[:300]}")
            
            elif event_type == "tool.result":
                tool_name = event.data.name if hasattr(event.data, 'name') else "unknown"
                result = event.data.result if hasattr(event.data, 'result') else ""
                result_str = str(result)
                tool_results.append({
                    'tool': tool_name,
                    'result': result_str
                })
                result_preview = result_str[:200] if len(result_str) > 200 else result_str
                print(f"\n   ✅ TOOL RESULT: {tool_name}")
                print(f"      {result_preview}")
            
            elif event_type == "session.idle":
                print(f"\n   ✓ SESSION IDLE (complete)")
                processing_done.set()
            
            elif event_type == "session.error":
                error_msg = str(event.data) if hasattr(event, 'data') else "Unknown error"
                print(f"\n   ❌ ERROR: {error_msg}")
                processing_done.set()
            
            elif event_type in ("assistant.turn_start", "assistant.turn_end", "user.message"):
                pass  # Normal flow events
            
            else:
                print(f"\n   ⚠️  EVENT: {event_type}")
        
        except Exception as e:
            print(f"\n   ❌ Event handler error: {e}")
    
    # Register event handler
    session.on(on_event)
    print(f"   Event handler registered")
    
    try:
        # Send message
        print(f"\n   Sending message...")
        await session.send({"prompt": "Edit the test document now."})
        
        # Wait for processing to complete
        print(f"   Waiting for response...")
        await asyncio.wait_for(processing_done.wait(), timeout=60.0)
        print(f"\n   Processing complete")
    
    except asyncio.TimeoutError:
        print(f"\n   ❌ TIMEOUT after 60 seconds")
    except Exception as e:
        print(f"\n   ❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    
    # Results
    print(f"\n\n" + "="*80)
    print("RESULTS")
    print("="*80)
    
    print(f"\n4. Events Received:")
    event_counts = {}
    for evt in events_received:
        event_counts[evt] = event_counts.get(evt, 0) + 1
    for evt, count in sorted(event_counts.items()):
        print(f"   {evt}: {count}")
    
    print(f"\n5. Tool Calls: {len(tool_calls)}")
    if tool_calls:
        for idx, call in enumerate(tool_calls, 1):
            print(f"   {idx}. {call['tool']}")
            if call['args']:
                args_str = json.dumps(call['args'], indent=6)
                if len(args_str) > 200:
                    args_str = args_str[:200] + "..."
                print(f"      {args_str}")
    else:
        print("   ❌ NO TOOL CALLS DETECTED!")
    
    print(f"\n6. Tool Results: {len(tool_results)}")
    if tool_results:
        for idx, result in enumerate(tool_results, 1):
            print(f"   {idx}. {result['tool']}")
    
    print(f"\n7. Response Text: {len(response_text)} chars")
    if response_text:
        print(f"   Preview: {response_text[:200]}...")
    
    # Check file
    final_content = test_file.read_text()
    print(f"\n8. File Status:")
    print(f"   Size: {test_file.stat().st_size} bytes")
    print(f"   Changed: {'EDITED BY AI' in final_content}")
    print(f"   Content: {final_content[:100]}...")
    
    # Verdict
    print(f"\n" + "="*80)
    if len(tool_calls) > 0 and 'EDITED BY AI' in final_content:
        print("✅ SUCCESS: AI used tools and edited the file!")
    elif len(tool_calls) > 0:
        print("⚠️  PARTIAL: AI called tools but file not edited correctly")
    else:
        print("❌ FAILURE: AI did not call any tools!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_tool_calls())
