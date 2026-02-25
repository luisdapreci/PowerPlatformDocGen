"""Quick test to see actual server errors"""
import asyncio
import websockets
import json

async def test():
    # First upload
    import httpx
    from pathlib import Path
    
    # Use relative path from project root
    base_dir = Path(__file__).parent.parent
    zip_path = base_dir / "tests" / "data" / "Solution_08142025_1_0_0_102.zip"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(zip_path, 'rb') as f:
            files = {'file': ('solution.zip', f, 'application/zip')}
            response = await client.post("http://localhost:8000/upload", files=files)
            data = response.json()
            session_id = data['session_id']
            print(f"Session ID: {session_id}")
    
    # Now connect WebSocket and send message
    async with websockets.connect(f"ws://localhost:8000/ws/chat/{session_id}") as ws:
        await ws.send(json.dumps({"message": "Hello"}))
        
        # Read responses
        for i in range(5):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                print(f"Received: {msg}")
            except asyncio.TimeoutError:
                print("Timeout")
                break

asyncio.run(test())
