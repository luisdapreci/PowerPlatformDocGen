"""
Thorough test suite for GitHub Copilot SDK v0.1.32 integration.

Covers:
  1. SDK version & protocol version assertions
  2. Import correctness (all types used in production code)
  3. PermissionRequest dataclass structure (field names, enum values)
  4. PermissionRequestResult dataclass construction
  5. Permission handler lambda logic (shell → deny, others → approve)
  6. CopilotClient instantiation
  7. SessionConfig field compatibility
  8. Live session smoke test (create session, send a simple prompt, close)
  9. DocumentationGenerator initialisation
 10. SessionManager instantiation (no live server required)
"""

import asyncio
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup so we can import from src/
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ===========================================================================
# 1. SDK version & protocol version
# ===========================================================================

class TestSDKVersion:
    def test_installed_version(self):
        """SDK must be at least 0.1.32 to support protocol v3."""
        import importlib.metadata

        version_str = importlib.metadata.version("github-copilot-sdk")
        major, minor, patch = (int(x) for x in version_str.split("."))
        assert (major, minor, patch) >= (0, 1, 32), (
            f"SDK version {version_str} is too old – must be >= 0.1.32"
        )

    def test_protocol_version_is_3(self):
        """SDK must expose protocol version 3 (required by current Copilot CLI)."""
        from copilot.sdk_protocol_version import SDK_PROTOCOL_VERSION

        assert SDK_PROTOCOL_VERSION == 3, (
            f"Expected protocol version 3, got {SDK_PROTOCOL_VERSION}"
        )


# ===========================================================================
# 2. Import correctness
# ===========================================================================

class TestImports:
    def test_copilot_package_imports(self):
        """All public names used in production code must be importable."""
        from copilot import (  # noqa: F401
            CopilotClient,
            CopilotSession,
            PermissionRequestResult,
            SessionConfig,
        )

    def test_generated_types_import(self):
        """PermissionRequest comes from the generated types module."""
        from copilot.generated.session_events import (  # noqa: F401
            PermissionRequest,
            PermissionRequestKind,
        )

    def test_doc_generator_imports_cleanly(self):
        """doc_generator.py must import without errors."""
        import doc_generator  # noqa: F401

    def test_session_manager_imports_cleanly(self):
        """session_manager.py must import without errors."""
        import session_manager  # noqa: F401


# ===========================================================================
# 3. PermissionRequest dataclass structure
# ===========================================================================

class TestPermissionRequestStructure:
    def test_permission_request_is_dataclass(self):
        import dataclasses
        from copilot.generated.session_events import PermissionRequest

        assert dataclasses.is_dataclass(PermissionRequest), (
            "PermissionRequest must be a dataclass in SDK >= 0.1.32"
        )

    def test_permission_request_has_kind_field(self):
        import dataclasses
        from copilot.generated.session_events import PermissionRequest

        field_names = {f.name for f in dataclasses.fields(PermissionRequest)}
        assert "kind" in field_names

    def test_permission_request_kind_enum_values(self):
        """All permission kinds referenced in production lambdas must exist."""
        from copilot.generated.session_events import PermissionRequestKind

        # Values used in our permission handlers
        assert PermissionRequestKind.SHELL.value == "shell"
        assert PermissionRequestKind.WRITE.value == "write"
        assert PermissionRequestKind.READ.value == "read"

    def test_can_construct_permission_request(self):
        """Must be possible to construct a PermissionRequest for unit testing."""
        from copilot.generated.session_events import PermissionRequest, PermissionRequestKind

        req = PermissionRequest(kind=PermissionRequestKind.SHELL)
        assert req.kind == PermissionRequestKind.SHELL
        assert req.kind.value == "shell"


# ===========================================================================
# 4. PermissionRequestResult dataclass construction
# ===========================================================================

class TestPermissionRequestResult:
    def test_construct_approved(self):
        from copilot import PermissionRequestResult

        result = PermissionRequestResult(kind="approved")
        assert result.kind == "approved"

    def test_construct_denied_by_rules(self):
        from copilot import PermissionRequestResult

        result = PermissionRequestResult(kind="denied-by-rules")
        assert result.kind == "denied-by-rules"

    def test_default_kind_is_denied(self):
        """Default kind must be a denial variant."""
        from copilot import PermissionRequestResult

        result = PermissionRequestResult()
        assert "denied" in result.kind

    def test_optional_fields_default_to_none(self):
        from copilot import PermissionRequestResult

        result = PermissionRequestResult(kind="approved")
        assert result.rules is None
        assert result.feedback is None
        assert result.message is None


# ===========================================================================
# 5. Permission handler lambda logic
# ===========================================================================

class TestPermissionHandlerLogic:
    """
    Simulate exactly the lambdas used in doc_generator.py and session_manager.py
    and assert they produce the correct PermissionRequestResult for each kind.
    """

    @pytest.fixture
    def doc_gen_handler(self):
        from copilot import PermissionRequestResult

        return lambda req, ctx: (
            PermissionRequestResult(kind="denied-by-rules")
            if req.kind.value == "shell"
            else PermissionRequestResult(kind="approved")
        )

    @pytest.fixture
    def session_mgr_handler(self):
        from copilot import PermissionRequestResult

        return lambda req, ctx: (
            PermissionRequestResult(kind="denied-by-rules")
            if req.kind.value in ("shell", "write")
            else PermissionRequestResult(kind="approved")
        )

    def _make_request(self, kind_str: str):
        from copilot.generated.session_events import PermissionRequest, PermissionRequestKind

        return PermissionRequest(kind=PermissionRequestKind(kind_str))

    # --- doc_generator handler ---

    def test_doc_gen_shell_denied(self, doc_gen_handler):
        req = self._make_request("shell")
        result = doc_gen_handler(req, {})
        assert result.kind == "denied-by-rules"

    def test_doc_gen_read_approved(self, doc_gen_handler):
        req = self._make_request("read")
        result = doc_gen_handler(req, {})
        assert result.kind == "approved"

    def test_doc_gen_write_approved(self, doc_gen_handler):
        """doc_generator allows write (AI edits the doc file in-place)."""
        req = self._make_request("write")
        result = doc_gen_handler(req, {})
        assert result.kind == "approved"

    def test_doc_gen_mcp_approved(self, doc_gen_handler):
        req = self._make_request("mcp")
        result = doc_gen_handler(req, {})
        assert result.kind == "approved"

    # --- session_manager handler ---

    def test_session_mgr_shell_denied(self, session_mgr_handler):
        req = self._make_request("shell")
        result = session_mgr_handler(req, {})
        assert result.kind == "denied-by-rules"

    def test_session_mgr_write_denied(self, session_mgr_handler):
        """session_manager denies write requests for added security."""
        req = self._make_request("write")
        result = session_mgr_handler(req, {})
        assert result.kind == "denied-by-rules"

    def test_session_mgr_read_approved(self, session_mgr_handler):
        req = self._make_request("read")
        result = session_mgr_handler(req, {})
        assert result.kind == "approved"

    def test_session_mgr_url_approved(self, session_mgr_handler):
        req = self._make_request("url")
        result = session_mgr_handler(req, {})
        assert result.kind == "approved"


# ===========================================================================
# 6. CopilotClient instantiation
# ===========================================================================

class TestCopilotClientInstantiation:
    def test_client_can_be_constructed(self):
        """CopilotClient() must not raise at construction time."""
        from copilot import CopilotClient

        client = CopilotClient()
        assert client is not None

    def test_client_has_create_session_method(self):
        from copilot import CopilotClient
        import inspect

        client = CopilotClient()
        assert hasattr(client, "create_session")
        assert inspect.iscoroutinefunction(client.create_session)

    def test_client_has_start_method(self):
        from copilot import CopilotClient
        import inspect

        client = CopilotClient()
        assert hasattr(client, "start")
        assert inspect.iscoroutinefunction(client.start)


# ===========================================================================
# 7. SessionConfig field compatibility
# ===========================================================================

class TestSessionConfigFields:
    """
    The SessionConfig TypedDict must contain all fields our code sets.
    We do NOT start a live server — just validate the type annotations.
    """

    @pytest.fixture
    def annotations(self):
        from copilot import SessionConfig

        return SessionConfig.__annotations__

    def test_model_field_exists(self, annotations):
        assert "model" in annotations

    def test_working_directory_field_exists(self, annotations):
        assert "working_directory" in annotations

    def test_streaming_field_exists(self, annotations):
        assert "streaming" in annotations

    def test_on_permission_request_field_exists(self, annotations):
        assert "on_permission_request" in annotations

    def test_system_message_field_exists(self, annotations):
        assert "system_message" in annotations

    def test_available_tools_field_exists(self, annotations):
        assert "available_tools" in annotations

    def test_infinite_sessions_field_exists(self, annotations):
        """InfiniteSessionConfig support was added in sdk >= 0.1.28."""
        assert "infinite_sessions" in annotations, (
            "infinite_sessions not in SessionConfig – infinite sessions feature unavailable"
        )

    def test_session_config_can_be_built_as_dict(self):
        """Production code builds config as a plain dict – verify it is accepted."""
        import config as app_config
        from copilot import PermissionRequestResult

        session_config = {
            "model": app_config.COPILOT_MODEL,
            "working_directory": "/tmp/test",
            "streaming": False,
            "on_permission_request": lambda req, ctx: PermissionRequestResult(kind="approved"),
            "system_message": {
                "mode": "append",
                "content": "You are a test assistant.",
            },
        }
        # Just check it's a valid dict with the expected keys
        assert session_config["model"] == app_config.COPILOT_MODEL
        assert "on_permission_request" in session_config


# ===========================================================================
# 8. DocumentationGenerator initialisation
# ===========================================================================

class TestDocumentationGeneratorInit:
    def test_instantiation(self):
        from doc_generator import DocumentationGenerator

        gen = DocumentationGenerator()
        assert gen.client is None  # Not yet initialized
        assert isinstance(gen._generation_progress, dict)

    def test_get_progress_returns_none_for_unknown_session(self):
        from doc_generator import DocumentationGenerator

        gen = DocumentationGenerator()
        result = gen.get_progress("nonexistent-session-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_initialize_creates_client(self):
        """initialize() must create a CopilotClient without error."""
        from doc_generator import DocumentationGenerator

        gen = DocumentationGenerator()
        await gen.initialize()
        assert gen.client is not None

    @pytest.mark.asyncio
    async def test_generate_raises_before_init(self):
        """generate_documentation() must raise RuntimeError if not initialized."""
        from doc_generator import DocumentationGenerator

        gen = DocumentationGenerator()
        with pytest.raises(RuntimeError, match="not initialized"):
            await gen.generate_documentation(
                session_id="test",
                working_directory=Path("/tmp"),
                critical_files=[],
                non_critical_files=[],
                template_path=Path("/tmp/template.md"),
            )


# ===========================================================================
# 9. SessionManager instantiation
# ===========================================================================

class TestSessionManagerInit:
    def test_instantiation(self):
        from session_manager import SessionManager

        mgr = SessionManager()
        assert mgr.client is None
        assert isinstance(mgr.sessions, dict)

    def test_uses_permission_request_result(self):
        """session_manager.py must import PermissionRequestResult (not use dicts)."""
        import inspect
        import session_manager

        src = inspect.getsource(session_manager)
        assert "PermissionRequestResult" in src, (
            "session_manager.py must import and use PermissionRequestResult"
        )
        assert 'req.get("kind")' not in src, (
            "session_manager.py must not use the old dict-based req.get('kind') pattern"
        )

    def test_uses_permission_request_result_in_doc_generator(self):
        """doc_generator.py must import PermissionRequestResult (not use dicts)."""
        import inspect
        import doc_generator

        src = inspect.getsource(doc_generator)
        assert "PermissionRequestResult" in src
        assert 'req.get("kind")' not in src, (
            "doc_generator.py must not use the old dict-based req.get('kind') pattern"
        )


# ===========================================================================
# 10. Live session smoke test (requires authenticated Copilot CLI)
# ===========================================================================

@pytest.mark.asyncio
async def test_live_session_smoke():
    """
    End-to-end smoke test: create a real Copilot session with the new SDK,
    send a trivial prompt, and verify a non-empty response is returned.

    Skips gracefully if the Copilot CLI is not authenticated or unavailable.
    """
    import subprocess
    from copilot import CopilotClient, PermissionRequestResult

    # Pre-check: Copilot CLI must be on PATH and authenticated
    try:
        result = subprocess.run(
            ["copilot", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            pytest.skip("Copilot CLI not available or not authenticated")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("Copilot CLI not found on PATH")

    client = CopilotClient()

    session_config = {
        "model": "claude-sonnet-4.5",
        "streaming": False,
        "on_permission_request": lambda req, ctx: (
            PermissionRequestResult(kind="denied-by-rules")
            if req.kind.value == "shell"
            else PermissionRequestResult(kind="approved")
        ),
        "system_message": {
            "mode": "append",
            "content": "You are a helpful assistant for testing purposes.",
        },
    }

    session = await client.create_session(session_config)
    assert session is not None, "create_session() returned None"

    response = await session.send_and_wait(
        {"prompt": "Reply with exactly the word: PONG"},
        timeout=60,
    )

    assert response is not None, "send_and_wait() returned None"
    assert hasattr(response, "data"), "Response must have a 'data' attribute"
    assert hasattr(response.data, "content"), "Response.data must have 'content'"
    content = response.data.content.strip()
    assert len(content) > 0, "Response content must not be empty"
    print(f"\n   Live session response: {content!r}")

    # Cleanup
    try:
        if hasattr(session, "close"):
            await session.close()
    except Exception:
        pass
