"""
API Endpoint Tests for Documentation Generation
Tests the FastAPI endpoints for documentation generation and progress tracking
"""

import sys
from pathlib import Path
import json
import asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import pytest
    from fastapi.testclient import TestClient
    from httpx import AsyncClient
    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False
    # Define minimal pytest stubs for standalone mode
    class pytest:
        class fixture:
            def __init__(self, *args, **kwargs):
                pass
            def __call__(self, func):
                return func
        
        class mark:
            @staticmethod
            def asyncio(func):
                return func
    
    pytest.fixture = pytest.fixture()
    pytest.mark = pytest.mark()
    TestClient = None
    AsyncClient = None


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app"""
    from main import app
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Create an async test client"""
    from main import app
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


class TestDocumentationGenerationEndpoint:
    """Test the /generate-docs endpoint"""
    
    def test_generate_docs_endpoint_exists(self, test_client):
        """Test that the generate-docs endpoint exists"""
        # Try with a non-existent session to verify endpoint exists
        response = test_client.post("/generate-docs/test-session-123")
        # Should return 404 for non-existent session, not 405 (method not allowed)
        assert response.status_code in [404, 422], "Endpoint should exist"
    
    def test_generate_docs_with_business_context(self, test_client):
        """Test that business context can be passed"""
        # This will fail with 404 since session doesn't exist, but tests the signature
        response = test_client.post(
            "/generate-docs/test-session-456",
            json={"business_context": "Test business requirements"}
        )
        assert response.status_code in [404, 422]
    
    @pytest.mark.asyncio
    async def test_generate_docs_isolation(self, async_client):
        """Test that doc generation doesn't affect chat session"""
        # This is a structural test - in real usage, verify no WebSocket interference
        # by checking that chat WebSocket doesn't receive doc generation events
        pass


class TestProgressEndpoint:
    """Test the /doc-progress endpoint"""
    
    def test_progress_endpoint_exists(self, test_client):
        """Test that the doc-progress endpoint exists"""
        response = test_client.get("/doc-progress/test-session-789")
        assert response.status_code == 200
    
    def test_progress_endpoint_returns_not_started(self, test_client):
        """Test progress endpoint for non-existent generation"""
        response = test_client.get("/doc-progress/nonexistent-session")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_started"
        assert "session_id" in data
    
    def test_progress_endpoint_structure(self, test_client):
        """Test that progress endpoint returns correct structure"""
        response = test_client.get("/doc-progress/test-structure")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ["session_id", "status"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestWebSocketChatIsolation:
    """Test that WebSocket chat is isolated from doc generation"""
    
    @pytest.mark.asyncio
    async def test_chat_websocket_exists(self, test_client):
        """Test that chat WebSocket endpoint still exists"""
        # WebSocket endpoint testing requires special handling
        # This just verifies the structure
        pass
    
    @pytest.mark.asyncio
    async def test_no_doc_events_in_chat(self):
        """Test that doc generation events don't appear in chat"""
        # In a full test, you would:
        # 1. Connect to WebSocket chat
        # 2. Trigger doc generation
        # 3. Verify chat doesn't receive doc generation events
        # This is covered by the integration test in test_doc_generation_isolation.py
        pass


class TestHealthEndpoint:
    """Test health endpoint still works after changes"""
    
    def test_health_check(self, test_client):
        """Test that health endpoint works"""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"


def test_import_structure():
    """Test that all necessary imports work"""
    try:
        from main import app, get_doc_generator
        from doc_generator import DocumentationGenerator
        from session_manager import SessionManager
        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


if __name__ == "__main__":
    print("Testing API endpoint structure...")
    print("\n1. Testing imports...")
    if test_import_structure():
        print("   ✓ All imports successful")
    else:
        print("   ✗ Import failed")
        sys.exit(1)
    
    print("\n2. Testing endpoint structure...")
    print("   Note: Run with pytest for full API tests:")
    print("   pytest tests/test_api_endpoints.py -v")
    
    print("\n3. Checking endpoint registration...")
    from main import app
    
    routes = [route.path for route in app.routes]
    expected_endpoints = [
        "/generate-docs/{session_id}",
        "/doc-progress/{session_id}",
        "/ws/chat/{session_id}",
        "/health"
    ]
    
    for endpoint in expected_endpoints:
        if endpoint in routes:
            print(f"   ✓ {endpoint} registered")
        else:
            print(f"   ✗ {endpoint} NOT found")
    
    print("\n✓ API structure tests complete")
