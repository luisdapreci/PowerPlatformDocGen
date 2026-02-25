# Test Suite for Documentation Generation Isolation

This test suite verifies that the WebSocket chat functionality is completely isolated from the documentation generation process.

## Test Files

### 1. `test_doc_generation_isolation.py`
Tests the core `DocumentationGenerator` class and its isolation from chat sessions.

**What it tests:**
- ✅ DocumentationGenerator initialization
- ✅ Singleton pattern for doc generator
- ✅ Progress tracking functionality
- ✅ File type identification
- ✅ Prompt building for critical files and consolidation
- ✅ Non-critical file summary generation
- ✅ Isolation from chat SessionManager

**Key verifications:**
- Doc generator creates its own Copilot sessions (isolated from chat)
- No WebSocket event handlers in doc generation
- Progress can be tracked independently
- Multiple doc generations don't interfere with each other

### 2. `test_api_endpoints.py`
Tests the FastAPI endpoints for documentation generation and progress tracking.

**What it tests:**
- ✅ `/generate-docs/{session_id}` endpoint exists and works
- ✅ `/doc-progress/{session_id}` endpoint exists and returns correct structure
- ✅ `/ws/chat/{session_id}` WebSocket endpoint still works
- ✅ Business context can be passed to doc generation
- ✅ Health endpoint still functional

**Key verifications:**
- API endpoints properly registered
- Endpoint signatures accept correct parameters
- Response structures match expected format

## Running the Tests

### Quick Test (No pytest required)
Run basic structural tests without installing pytest:

**Windows (PowerShell):**
```powershell
.\run_tests.ps1
```

**Linux/Mac (Bash):**
```bash
chmod +x run_tests.sh
./run_tests.sh
```

**Or run individual test files:**
```bash
python tests/test_doc_generation_isolation.py
python tests/test_api_endpoints.py
```

### Full Test Suite (Requires pytest)
For comprehensive testing including integration tests:

```bash
# Install pytest dependencies
pip install pytest pytest-asyncio httpx

# Run all tests with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/test_doc_generation_isolation.py -v
pytest tests/test_api_endpoints.py -v
```

## Test Output Explanation

### ✅ Passing Tests Indicate:

1. **DocumentationGenerator is isolated**: Creates separate Copilot sessions for doc generation
2. **No WebSocket interference**: Doc generation events don't appear in chat WebSocket
3. **Progress tracking works**: Frontend can poll `/doc-progress/{session_id}` for updates
4. **Clean separation**: Chat uses `SessionManager`, doc uses `DocumentationGenerator`
5. **Direct LLM processing**: Documentation goes straight to LLM without chat-style interaction

### ❌ If Tests Fail:

- Check that `doc_generator.py` is correctly imported in `main.py`
- Verify Copilot SDK is installed: `pip install github-copilot-sdk`
- Ensure FastAPI is up to date: `pip install fastapi>=0.109.0`
- Check that the virtual environment is activated

## Architecture Verified by Tests

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────┐      ┌──────────────────────┐    │
│  │   WebSocket Chat     │      │  Doc Generation API   │    │
│  │   /ws/chat/{id}      │      │  /generate-docs/{id}  │    │
│  └──────────┬───────────┘      └──────────┬───────────┘    │
│             │                              │                 │
│             v                              v                 │
│  ┌──────────────────────┐      ┌──────────────────────┐    │
│  │   SessionManager     │      │ DocumentationGenerator│    │
│  │  (Chat sessions)     │      │  (Doc sessions)       │    │
│  └──────────┬───────────┘      └──────────┬───────────┘    │
│             │                              │                 │
│             v                              v                 │
│  ┌──────────────────────┐      ┌──────────────────────┐    │
│  │ Copilot Session      │      │ Isolated Copilot      │    │
│  │ (with WebSocket      │      │ Session (no WebSocket)│    │
│  │  event handlers)     │      │                       │    │
│  └──────────────────────┘      └──────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## What Changed

### Before (Problem):
- Documentation generation used the same Copilot session as chat
- Doc generation events streamed to WebSocket chat
- Caused loop issues and confusion in chat interface

### After (Solution):
- Documentation generation creates isolated sessions
- No WebSocket event handlers in doc sessions
- Clean separation: chat = interactive, docs = batch processing
- Progress tracked separately via `/doc-progress/{session_id}`

## Manual Testing Checklist

After running automated tests, manually verify:

1. ✅ Upload a Power Platform solution
2. ✅ Open WebSocket chat and send a message
3. ✅ Generate documentation
4. ✅ Verify chat doesn't show doc generation progress
5. ✅ Verify doc generation completes successfully
6. ✅ Verify you can continue chatting after doc generation
7. ✅ Poll `/doc-progress/{session_id}` during generation

## Troubleshooting

### "Module not found" errors
```bash
cd c:\PowerPlatformDocGen
pip install -r requirements.txt
```

### Tests timeout
- The full integration tests make actual LLM calls
- Use `pytest -v --tb=short` to see detailed output
- Skip integration tests with: `pytest -m "not asyncio"`

### Import errors
- Ensure you're running from the project root
- Check that `src/` is in the Python path
- Activate virtual environment before running tests

## Contributing

When adding new features to documentation generation:

1. Add tests to verify isolation is maintained
2. Ensure no WebSocket events leak from doc generation
3. Test progress tracking for new stages
4. Verify error handling doesn't affect chat sessions
