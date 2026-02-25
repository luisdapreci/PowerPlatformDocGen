"""
Test script to verify the agent can navigate and read multiple selected components
(apps + flows) in a solution.

This tests that when selecting 1 app and multiple flows, the agent can access
and analyze all of them.
"""

import asyncio
import httpx
import websockets
import json
import time
from pathlib import Path


class MultiComponentTester:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session_id = None
        self.events_received = []
        self.selected_components = []
        
    async def upload_solution(self, solution_path: str):
        """Upload a solution zip file"""
        print("\n📤 Step 1: Uploading solution...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(solution_path, 'rb') as f:
                files = {'file': ('solution.zip', f, 'application/zip')}
                response = await client.post(f"{self.base_url}/upload", files=files)
                
                if response.status_code != 200:
                    print(f"❌ Upload failed: {response.status_code}")
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
            
            # Count by type
            canvas_apps = [c for c in components if c['type'].lower() in ['canvasapp', 'canvas_app']]
            flows = [c for c in components if c['type'].lower() in ['power_automate', 'powerautomate']]
            
            print(f"✅ Found {len(components)} components total:")
            print(f"   - Canvas Apps: {len(canvas_apps)}")
            print(f"   - Power Automate Flows: {len(flows)}")
            
            # Show first few of each
            if canvas_apps:
                print(f"\n   📱 Canvas Apps:")
                for comp in canvas_apps[:3]:
                    print(f"      - {comp['name']}")
            
            if flows:
                print(f"\n   ⚡ Flows:")
                for comp in flows[:5]:
                    print(f"      - {comp['name']}")
            
            return components
    
    async def select_multiple_components(self, canvas_count=1, flow_count=3):
        """Select multiple components (apps + flows)"""
        print(f"\n🎯 Step 3: Selecting components ({canvas_count} app + {flow_count} flows)...")
        
        # First get components
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base_url}/components/{self.session_id}")
            
            if response.status_code != 200:
                print(f"❌ Failed to get components")
                return False
            
            data = response.json()
            components = data['components']
            
            # Separate by type
            canvas_apps = [c for c in components if c['type'].lower() in ['canvasapp', 'canvas_app']]
            flows = [c for c in components if c['type'].lower() in ['power_automate', 'powerautomate']]
            
            # Select the requested amounts
            selected_paths = []
            selected_names = []
            
            if canvas_apps and canvas_count > 0:
                for i in range(min(canvas_count, len(canvas_apps))):
                    selected_paths.append(canvas_apps[i]['path'])
                    selected_names.append(('app', canvas_apps[i]['name']))
            
            if flows and flow_count > 0:
                for i in range(min(flow_count, len(flows))):
                    selected_paths.append(flows[i]['path'])
                    selected_names.append(('flow', flows[i]['name']))
            
            self.selected_components = selected_names
            
            print(f"\n   Selected {len(selected_paths)} components:")
            for comp_type, name in selected_names:
                icon = "📱" if comp_type == 'app' else "⚡"
                print(f"      {icon} {name}")
            
            # Send selection
            payload = {
                'session_id': self.session_id,
                'selected_components': selected_paths
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
    
    async def test_multi_component_analysis(self):
        """Test that agent can navigate and analyze all selected components"""
        print("\n💬 Step 5: Testing multi-component analysis...")
        
        ws_url = f"ws://localhost:8000/ws/chat/{self.session_id}"
        self.events_received = []
        
        try:
            async with websockets.connect(ws_url, ping_interval=None) as websocket:
                print(f"✅ WebSocket connected")
                
                # Give the initial context time to process
                await asyncio.sleep(2)
                
                # Ask questions that require accessing multiple components
                questions = [
                    "What canvas apps and flows are in this solution?",
                    "Can you list all the Power Automate flows?",
                    "Summarize what each flow does"
                ]
                
                all_responses = []
                
                for i, question in enumerate(questions, 1):
                    print(f"\n   Question {i}: '{question}'")
                    
                    await websocket.send(json.dumps({
                        "message": question
                    }))
                    
                    # Collect response
                    response_text = ""
                    tools_used = []
                    timeout = 120
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
                                print(f"      🔧 Tool: {tool_name}")
                            
                            elif event_type == 'complete':
                                break
                            
                            elif event_type == 'error':
                                error = data.get('error', 'Unknown error')
                                print(f"      ❌ Error: {error}")
                                break
                        
                        except asyncio.TimeoutError:
                            if response_text:
                                break
                            continue
                    
                    all_responses.append({
                        'question': question,
                        'response': response_text,
                        'tools': tools_used
                    })
                    
                    print(f"      ✅ Got response ({len(response_text)} chars)")
                    
                    # Small delay between questions
                    await asyncio.sleep(1)
                
                return self.analyze_multi_component_results(all_responses)
        
        except Exception as e:
            print(f"❌ Chat test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def analyze_multi_component_results(self, responses):
        """Analyze the test results"""
        print("\n" + "="*60)
        print("📊 MULTI-COMPONENT TEST RESULTS")
        print("="*60)
        
        success_criteria = {
            "Found canvas apps": False,
            "Found Power Automate flows": False,
            "Mentioned multiple flows": False,
            "Listed flow actions/triggers": False,
            "No file access errors": False,
            "All questions answered": len(responses) == 3
        }
        
        # Combine all responses
        all_text = " ".join([r['response'] for r in responses]).lower()
        
        # Check for canvas apps mention
        if any(word in all_text for word in ['canvas', 'app', 'msapp']):
            success_criteria["Found canvas apps"] = True
        
        # Check for flows
        flow_keywords = ['flow', 'automate', 'workflow', 'trigger', 'action']
        if any(word in all_text for word in flow_keywords):
            success_criteria["Found Power Automate flows"] = True
        
        # Check if multiple flows mentioned
        flow_indicators = all_text.count('flow')
        if flow_indicators >= 3:
            success_criteria["Mentioned multiple flows"] = True
        
        # Check for flow details (triggers, actions, etc.)
        detail_keywords = ['trigger', 'action', 'when', 'create', 'update', 'send', 'get', 'list']
        if sum(1 for word in detail_keywords if word in all_text) >= 3:
            success_criteria["Listed flow actions/triggers"] = True
        
        # Check for errors
        error_patterns = [
            'cannot find',
            'does not exist',
            'no such file',
            'not found',
            'failed to',
            'error reading',
            'unable to'
        ]
        
        if not any(pattern in all_text for pattern in error_patterns):
            success_criteria["No file access errors"] = True
        
        # Print criteria results
        print("\n✅ Success Criteria:")
        all_passed = True
        for criterion, passed in success_criteria.items():
            status = "✅" if passed else "❌"
            print(f"   {status} {criterion}")
            if not passed:
                all_passed = False
        
        # Print detailed responses
        print(f"\n📝 Responses Summary:")
        print("-" * 60)
        for i, resp in enumerate(responses, 1):
            print(f"\nQ{i}: {resp['question']}")
            print(f"Tools used: {len(resp['tools'])} - {', '.join(set(resp['tools']))[:100]}")
            preview = resp['response'][:200]
            print(f"Response: {preview}{'...' if len(resp['response']) > 200 else ''}")
        print("-" * 60)
        
        # Check component coverage
        print(f"\n🎯 Component Coverage:")
        components_mentioned = []
        for comp_type, name in self.selected_components:
            # Simplify name for matching
            simple_name = name.lower().replace('_', ' ')
            if simple_name[:20] in all_text or name[:20].lower() in all_text:
                components_mentioned.append(name)
                print(f"   ✅ {name}")
            else:
                print(f"   ⚠️  {name} (not explicitly mentioned)")
        
        coverage_percent = (len(components_mentioned) / len(self.selected_components) * 100) if self.selected_components else 0
        print(f"\n   Coverage: {len(components_mentioned)}/{len(self.selected_components)} ({coverage_percent:.0f}%)")
        
        return all_passed
    
    async def run_full_test(self, solution_path: str):
        """Run the complete test workflow"""
        print("="*60)
        print("🧪 TESTING: Multi-Component Navigation")
        print("="*60)
        print(f"Solution: {solution_path}")
        print(f"Test: Select 1 app + 3 flows, verify agent can access all")
        
        # Step 1: Upload
        if not await self.upload_solution(solution_path):
            return False
        
        # Step 2: Get components to verify they exist
        components = await self.get_components()
        if not components:
            return False
        
        # Step 3: Select multiple components (1 app + 3 flows)
        if not await self.select_multiple_components(canvas_count=1, flow_count=3):
            return False
        
        # Step 4: Wait for unpacking
        if not await self.wait_for_unpacking():
            return False
        
        # Step 5: Test multi-component access
        result = await self.test_multi_component_analysis()
        
        print("\n" + "="*60)
        if result:
            print("🎉 TEST PASSED!")
            print("   The agent successfully navigated multiple components.")
        else:
            print("❌ TEST FAILED!")
            print("   The agent had issues accessing all components.")
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
    
    tester = MultiComponentTester()
    
    try:
        await tester.run_full_test(str(solution_path))
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("Starting multi-component test...")
    print("Make sure the server is running on http://localhost:8000\n")
    asyncio.run(main())
