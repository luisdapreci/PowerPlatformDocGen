"""
Test script to verify that the agent can locate unpacked files correctly.

This tests the initial context fix that provides the agent with exact paths
to unpacked canvas apps and their Power Fx formula files.
"""

import asyncio
import httpx
import websockets
import json
import time
from pathlib import Path


class ContextFixTester:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session_id = None
        self.events_received = []
        
    async def upload_solution(self, solution_path: str):
        """Upload a solution zip file"""
        print("\n📤 Step 1: Uploading solution...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(solution_path, 'rb') as f:
                files = {'file': ('solution.zip', f, 'application/zip')}
                response = await client.post(f"{self.base_url}/upload", files=files)
                
                if response.status_code != 200:
                    print(f"❌ Upload failed: {response.status_code}")
                    print(f"   Response: {response.text}")
                    return False
                
                data = response.json()
                self.session_id = data['session_id']
                print(f"✅ Solution uploaded, session: {self.session_id}")
                return True
    
    async def get_components(self):
        """Get available components"""
        print("\n📋 Step 2: Getting components...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base_url}/components/{self.session_id}")
            
            if response.status_code != 200:
                print(f"❌ Get components failed: {response.status_code}")
                return None
            
            data = response.json()
            components = data['components']
            print(f"✅ Found {len(components)} components")
            
            # Print first few components
            for comp in components[:3]:
                print(f"   - {comp['name']} ({comp['type']})")
            
            return components
    
    async def select_components(self, component_paths: list):
        """Select components to unpack"""
        print(f"\n🎯 Step 3: Selecting {len(component_paths)} components...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                'session_id': self.session_id,
                'selected_components': component_paths
            }
            response = await client.post(
                f"{self.base_url}/select-components",
                json=payload
            )
            
            if response.status_code != 200:
                print(f"❌ Select components failed: {response.status_code}")
                return False
            
            print("✅ Components selected, unpacking started")
            return True
    
    async def wait_for_unpacking(self, timeout=60):
        """Poll status endpoint until unpacking is complete"""
        print("\n⏳ Step 4: Waiting for unpacking to complete...")
        
        start_time = time.time()
        last_status = None
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.time() - start_time < timeout:
                response = await client.get(f"{self.base_url}/status/{self.session_id}")
                
                if response.status_code != 200:
                    print(f"❌ Status check failed: {response.status_code}")
                    return False
                
                data = response.json()
                status = data['status']
                
                if status != last_status:
                    print(f"   Status: {status} - {data.get('current_step', '')}")
                    last_status = status
                
                if status == 'analyzing':
                    print("✅ Unpacking complete! Session ready for analysis")
                    return True
                
                await asyncio.sleep(2)
        
        print(f"❌ Timeout waiting for unpacking")
        return False
    
    async def test_chat_with_context(self):
        """Test chat to verify agent can find unpacked files"""
        print("\n💬 Step 5: Testing chat with formula question...")
        
        ws_url = f"ws://localhost:8000/ws/chat/{self.session_id}"
        self.events_received = []
        
        try:
            async with websockets.connect(ws_url, ping_interval=None) as websocket:
                print(f"✅ WebSocket connected")
                
                # Give the initial context time to process
                await asyncio.sleep(2)
                
                # Send a question about formulas
                question = "What Power Fx formulas are in this solution?"
                print(f"   Asking: '{question}'")
                
                await websocket.send(json.dumps({
                    "message": question
                }))
                
                # Collect events for analysis
                response_text = ""
                tools_used = []
                timeout = 120  # 2 minutes for Copilot to respond
                start_time = time.time()
                
                while time.time() - start_time < timeout:
                    try:
                        message = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=5.0
                        )
                        
                        data = json.loads(message)
                        event_type = data.get('type')
                        self.events_received.append(data)
                        
                        if event_type == 'delta':
                            response_text += data.get('content', '')
                        
                        elif event_type == 'message':
                            if data.get('content'):
                                response_text += data.get('content', '')
                        
                        elif event_type == 'tool_call':
                            tool_name = data.get('tool', 'unknown')
                            tools_used.append(tool_name)
                            print(f"   🔧 Tool called: {tool_name}")
                        
                        elif event_type == 'tool_result':
                            tool_name = data.get('tool', 'unknown')
                            preview = data.get('preview', '')[:100]
                            print(f"   ✅ Tool result: {tool_name}")
                            if preview:
                                print(f"      Preview: {preview}...")
                        
                        elif event_type == 'complete':
                            print(f"\n✅ Response complete!")
                            break
                        
                        elif event_type == 'error':
                            error = data.get('error', 'Unknown error')
                            print(f"   ❌ Error: {error}")
                            return False
                    
                    except asyncio.TimeoutError:
                        # Check if we got a response yet
                        if response_text:
                            print(f"\n✅ Got response (timeout while waiting for completion)")
                            break
                        continue
                
                return self.analyze_results(response_text, tools_used)
        
        except Exception as e:
            print(f"❌ Chat test failed: {e}")
            return False
    
    def analyze_results(self, response_text: str, tools_used: list):
        """Analyze the test results"""
        print("\n" + "="*60)
        print("📊 RESULTS ANALYSIS")
        print("="*60)
        
        # Check if tools were used
        print(f"\n🔧 Tools used: {len(tools_used)}")
        for tool in tools_used:
            print(f"   - {tool}")
        
        success_criteria = {
            "Used custom Power Platform tools": False,
            "Found Power Fx formulas": False,
            "Response is substantial": False,
            "No file location errors": False
        }
        
        # Check criteria
        power_platform_tools = [
            'analyze_canvas_app_formulas',
            'list_data_sources',
            'extract_app_metadata'
        ]
        
        if any(tool in tools_used for tool in power_platform_tools):
            success_criteria["Used custom Power Platform tools"] = True
        
        # Check response content
        response_lower = response_text.lower()
        formula_keywords = ['formula', 'power fx', 'powerfx', 'function', 'expression']
        
        if any(keyword in response_lower for keyword in formula_keywords):
            success_criteria["Found Power Fx formulas"] = True
        
        if len(response_text) > 100:
            success_criteria["Response is substantial"] = True
        
        # Check for common error patterns
        error_patterns = [
            'cannot find',
            'does not exist',
            'no such file',
            'not found',
            'failed to',
            'error reading'
        ]
        
        if not any(pattern in response_lower for pattern in error_patterns):
            success_criteria["No file location errors"] = True
        
        # Print criteria results
        print("\n✅ Success Criteria:")
        all_passed = True
        for criterion, passed in success_criteria.items():
            status = "✅" if passed else "❌"
            print(f"   {status} {criterion}")
            if not passed:
                all_passed = False
        
        # Print response preview
        print(f"\n📝 Response Preview ({len(response_text)} chars):")
        print("-" * 60)
        print(response_text[:500])
        if len(response_text) > 500:
            print(f"\n   ... ({len(response_text) - 500} more characters)")
        print("-" * 60)
        
        return all_passed
    
    async def run_full_test(self, solution_path: str):
        """Run the complete test workflow"""
        print("="*60)
        print("🧪 TESTING: Agent Context Fix")
        print("="*60)
        print(f"Solution: {solution_path}")
        
        # Step 1: Upload
        if not await self.upload_solution(solution_path):
            return False
        
        # Step 2: Get components
        components = await self.get_components()
        if not components:
            return False
        
        # Step 3: Select first canvas app
        canvas_apps = [c for c in components if c['type'].lower() in ['canvasapp', 'canvas_app']]
        if not canvas_apps:
            print("❌ No canvas apps found in solution")
            return False
        
        selected = [canvas_apps[0]['path']]
        print(f"\n   Selecting canvas app: {canvas_apps[0]['name']}")
        
        if not await self.select_components(selected):
            return False
        
        # Step 4: Wait for unpacking
        if not await self.wait_for_unpacking():
            return False
        
        # Step 5: Test chat
        result = await self.test_chat_with_context()
        
        print("\n" + "="*60)
        if result:
            print("🎉 TEST PASSED!")
            print("   The agent successfully found and analyzed unpacked files.")
        else:
            print("❌ TEST FAILED!")
            print("   The agent had trouble locating or analyzing unpacked files.")
        print("="*60)
        
        return result


async def main():
    """Main test execution"""
    # Path to test solution
    solution_path = Path("tests/data/Solution_08142025_1_0_0_102.zip")
    
    if not solution_path.exists():
        print(f"❌ Test solution not found: {solution_path}")
        print("\nPlease provide a path to a Power Platform solution ZIP file:")
        custom_path = input("Path: ").strip()
        solution_path = Path(custom_path)
        
        if not solution_path.exists():
            print(f"❌ File not found: {solution_path}")
            return
    
    tester = ContextFixTester()
    
    try:
        await tester.run_full_test(str(solution_path))
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("Starting context fix test...")
    print("Make sure the server is running on http://localhost:8000\n")
    asyncio.run(main())
