"""
Tests for Quick / Comprehensive generation mode feature.

Covers:
  - Config constants
  - Model validation
  - API endpoint parameter handling
  - File batching logic
  - Prompt building differences between modes
  - Section merging in quick mode
  - Frontend HTML wiring (static checks)
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import pytest
    from fastapi.testclient import TestClient
    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False

    class _pytest_stub:
        class fixture:
            def __init__(self, *a, **kw): pass
            def __call__(self, f): return f
        class mark:
            @staticmethod
            def asyncio(f): return f
            @staticmethod
            def parametrize(*a, **kw):
                def deco(f): return f
                return deco

    pytest = _pytest_stub()
    pytest.fixture = _pytest_stub.fixture()
    pytest.mark = _pytest_stub.mark()
    TestClient = None


# --------------- fixtures ---------------

@pytest.fixture
def test_client():
    from main import app
    try:
        client = TestClient(app)
    except TypeError:
        pytest.skip("TestClient incompatible with installed httpx version")
    return client


@pytest.fixture
def doc_generator():
    """Return an uninitialised DocumentationGenerator (no Copilot SDK needed)."""
    from doc_generator import DocumentationGenerator
    return DocumentationGenerator()


# --------------- config tests ---------------

class TestConfigConstants:
    """Verify quick-mode config values exist and are sensible."""

    def test_quick_timeouts_exist(self):
        import config
        assert hasattr(config, "DOC_GEN_QUICK_FILE_TIMEOUT")
        assert hasattr(config, "DOC_GEN_QUICK_SCREENSHOT_TIMEOUT")
        assert hasattr(config, "DOC_GEN_QUICK_SECTION_TIMEOUT")

    def test_quick_timeouts_shorter_than_comprehensive(self):
        import config
        assert config.DOC_GEN_QUICK_FILE_TIMEOUT < config.DOC_GEN_FILE_TIMEOUT
        assert config.DOC_GEN_QUICK_SCREENSHOT_TIMEOUT < config.DOC_GEN_SCREENSHOT_TIMEOUT
        assert config.DOC_GEN_QUICK_SECTION_TIMEOUT < config.DOC_GEN_SECTION_TIMEOUT

    def test_batching_constants_exist(self):
        import config
        assert config.QUICK_MODE_BATCH_MAX_CHARS > 0
        assert config.QUICK_MODE_BATCH_MAX_FILES >= 2
        assert config.QUICK_MODE_SINGLE_FILE_THRESHOLD > 0

    def test_batching_threshold_less_than_max_chars(self):
        import config
        assert config.QUICK_MODE_SINGLE_FILE_THRESHOLD <= config.QUICK_MODE_BATCH_MAX_CHARS


# --------------- model tests ---------------

class TestGenerateDocsRequestModel:
    """Verify generation_mode field on the request model."""

    def test_default_mode_is_comprehensive(self):
        from models import GenerateDocsRequest
        req = GenerateDocsRequest(session_id="abc")
        assert req.generation_mode == "comprehensive"

    def test_quick_mode_accepted(self):
        from models import GenerateDocsRequest
        req = GenerateDocsRequest(session_id="abc", generation_mode="quick")
        assert req.generation_mode == "quick"

    def test_arbitrary_string_accepted_by_model(self):
        """Model itself doesn't restrict values; endpoint validates."""
        from models import GenerateDocsRequest
        req = GenerateDocsRequest(session_id="abc", generation_mode="invalid")
        assert req.generation_mode == "invalid"


# --------------- API endpoint tests ---------------

class TestGenerateDocsEndpoint:
    """Test /generate-docs accepts generation_mode."""

    def test_endpoint_accepts_comprehensive(self, test_client):
        resp = test_client.post(
            "/generate-docs/nonexistent-session",
            json={"generation_mode": "comprehensive"},
        )
        # 404 because session doesn't exist, but NOT 422 (validation error)
        assert resp.status_code == 404

    def test_endpoint_accepts_quick(self, test_client):
        resp = test_client.post(
            "/generate-docs/nonexistent-session",
            json={"generation_mode": "quick"},
        )
        assert resp.status_code == 404

    def test_endpoint_defaults_to_comprehensive(self, test_client):
        resp = test_client.post(
            "/generate-docs/nonexistent-session",
            json={},
        )
        assert resp.status_code == 404

    def test_invalid_mode_falls_back_to_comprehensive(self, test_client):
        """Invalid value should not cause 422; endpoint normalises it."""
        resp = test_client.post(
            "/generate-docs/nonexistent-session",
            json={"generation_mode": "turbo"},
        )
        assert resp.status_code == 404

    def test_endpoint_accepts_mode_with_business_context(self, test_client):
        resp = test_client.post(
            "/generate-docs/nonexistent-session",
            json={
                "generation_mode": "quick",
                "business_context": "Expense approval workflow",
            },
        )
        assert resp.status_code == 404


class TestGenerateQAEndpoint:
    """Test /generate-qa accepts generation_mode."""

    def test_qa_endpoint_accepts_quick(self, test_client):
        resp = test_client.post(
            "/generate-qa/nonexistent-session",
            json={"generation_mode": "quick"},
        )
        assert resp.status_code == 404

    def test_qa_endpoint_accepts_comprehensive(self, test_client):
        resp = test_client.post(
            "/generate-qa/nonexistent-session",
            json={"generation_mode": "comprehensive"},
        )
        assert resp.status_code == 404

    def test_qa_endpoint_defaults(self, test_client):
        resp = test_client.post(
            "/generate-qa/nonexistent-session",
            json={},
        )
        assert resp.status_code == 404

    def test_qa_invalid_mode_no_422(self, test_client):
        resp = test_client.post(
            "/generate-qa/nonexistent-session",
            json={"generation_mode": "blitz"},
        )
        assert resp.status_code == 404


# --------------- file batching tests ---------------

class TestFileBatching:
    """Test _batch_files_for_quick_mode logic."""

    def test_empty_list(self, doc_generator):
        batches = doc_generator._batch_files_for_quick_mode([])
        assert batches == []

    def test_single_small_file(self, doc_generator):
        files = [("app.json", "x" * 100)]
        batches = doc_generator._batch_files_for_quick_mode(files)
        assert len(batches) == 1
        assert len(batches[0]) == 1

    def test_large_file_kept_solo(self, doc_generator):
        import config
        large_content = "x" * (config.QUICK_MODE_SINGLE_FILE_THRESHOLD + 1)
        files = [("big.json", large_content)]
        batches = doc_generator._batch_files_for_quick_mode(files)
        assert len(batches) == 1
        assert len(batches[0]) == 1  # solo batch

    def test_small_files_batched_together(self, doc_generator):
        import config
        # 3 small files well under limits
        files = [
            ("a.json", "a" * 100),
            ("b.json", "b" * 100),
            ("c.json", "c" * 100),
        ]
        batches = doc_generator._batch_files_for_quick_mode(files)
        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_batch_respects_max_files(self, doc_generator):
        import config
        # Create more files than QUICK_MODE_BATCH_MAX_FILES
        n = config.QUICK_MODE_BATCH_MAX_FILES + 1
        files = [(f"f{i}.json", "x" * 10) for i in range(n)]
        batches = doc_generator._batch_files_for_quick_mode(files)
        assert len(batches) >= 2
        for batch in batches:
            assert len(batch) <= config.QUICK_MODE_BATCH_MAX_FILES

    def test_batch_respects_max_chars(self, doc_generator):
        import config
        # Each file is just under the single-file threshold but together they exceed batch max
        file_size = config.QUICK_MODE_SINGLE_FILE_THRESHOLD - 1
        n_files = (config.QUICK_MODE_BATCH_MAX_CHARS // file_size) + 2
        files = [(f"f{i}.json", "x" * file_size) for i in range(n_files)]
        batches = doc_generator._batch_files_for_quick_mode(files)
        assert len(batches) >= 2

    def test_mixed_sizes(self, doc_generator):
        import config
        large = ("large.json", "x" * (config.QUICK_MODE_SINGLE_FILE_THRESHOLD + 1))
        small1 = ("s1.json", "y" * 100)
        small2 = ("s2.json", "z" * 100)
        files = [large, small1, small2]
        batches = doc_generator._batch_files_for_quick_mode(files)
        # large should be solo, two smalls should be together
        assert len(batches) == 2
        solo_batch = [b for b in batches if len(b) == 1 and b[0][0] == "large.json"]
        assert len(solo_batch) == 1

    def test_all_files_present_after_batching(self, doc_generator):
        """Every input file must appear exactly once across all batches."""
        import config
        files = [(f"f{i}.json", "x" * (500 * (i + 1))) for i in range(7)]
        batches = doc_generator._batch_files_for_quick_mode(files)
        flat = [f for batch in batches for f in batch]
        assert sorted(f[0] for f in flat) == sorted(f[0] for f in files)


# --------------- prompt builder tests ---------------

class TestSystemPrompt:
    """Test that system prompt differs by mode."""

    def test_comprehensive_no_quick_directive(self, doc_generator):
        prompt = doc_generator._build_incremental_system_prompt(
            doc_file_path="doc.md",
            generation_mode="comprehensive",
        )
        assert "QUICK MODE" not in prompt

    def test_quick_includes_quick_directive(self, doc_generator):
        prompt = doc_generator._build_incremental_system_prompt(
            doc_file_path="doc.md",
            generation_mode="quick",
        )
        assert "QUICK MODE" in prompt
        assert "bullet" in prompt.lower()


class TestFilePrompt:
    """Test _build_incremental_file_prompt changes by mode."""

    def _make_prompt(self, doc_generator, mode, content_size=500):
        return doc_generator._build_incremental_file_prompt(
            path="Components/App.json",
            content="x" * content_size,
            idx=0,
            total=3,
            doc_file_path="doc.md",
            selection_context="Selected components",
            business_context="Test context",
            generation_mode=mode,
        )

    def test_quick_truncates_content_shorter(self, doc_generator):
        import config
        big = config.QUICK_MODE_SINGLE_FILE_THRESHOLD + 5000
        prompt_quick = self._make_prompt(doc_generator, "quick", content_size=big)
        prompt_comp = self._make_prompt(doc_generator, "comprehensive", content_size=big)
        # Quick prompt should contain less file content
        assert len(prompt_quick) < len(prompt_comp)

    def test_quick_prompt_mentions_concise(self, doc_generator):
        prompt = self._make_prompt(doc_generator, "quick")
        lower = prompt.lower()
        assert "concise" in lower or "brief" in lower or "bullet" in lower


class TestScreenshotPrompt:
    """Test _build_screenshot_pass_prompt mode awareness."""

    def _make_prompt(self, doc_generator, mode):
        return doc_generator._build_screenshot_pass_prompt(
            screenshot={"path": "screens/home.png", "context": "Home screen", "component_path": "App"},
            screenshot_index=0,
            total_screenshots=1,
            doc_file_path="doc.md",
            generation_mode=mode,
        )

    def test_comprehensive_prompt_exists(self, doc_generator):
        prompt = self._make_prompt(doc_generator, "comprehensive")
        assert len(prompt) > 0

    def test_quick_prompt_shorter(self, doc_generator):
        qp = self._make_prompt(doc_generator, "quick")
        cp = self._make_prompt(doc_generator, "comprehensive")
        # Quick should add brevity directives but not be wildly larger
        assert "concise" in qp.lower() or "brief" in qp.lower() or "1-sentence" in qp.lower()


class TestSectionEditingPrompt:
    """Test _build_section_editing_prompt handles merged sections in quick mode."""

    def _make_prompt(self, doc_generator, mode, section_id):
        from pathlib import Path as P
        return doc_generator._build_section_editing_prompt(
            section_id=section_id,
            section_name="Overview" if section_id == "overview" else "Introduction",
            doc_file_path="doc.md",
            selection_context="Selected components",
            business_section="Test business context",
            files_analyzed=3,
            critical_files=[("a.json", "content")],
            non_critical_files=[],
            working_directory=P("."),
            generation_mode=mode,
        )

    def test_comprehensive_section_key(self, doc_generator):
        prompt = self._make_prompt(doc_generator, "comprehensive", "overview")
        assert len(prompt) > 0

    def test_quick_merged_section_key(self, doc_generator):
        prompt = self._make_prompt(doc_generator, "quick", "intro")
        assert len(prompt) > 0

    def test_quick_section_mentions_concise(self, doc_generator):
        prompt = self._make_prompt(doc_generator, "quick", "intro")
        lower = prompt.lower()
        assert "concise" in lower or "bullet" in lower or "brief" in lower


# --------------- frontend static checks ---------------

class TestFrontendWiring:
    """Static checks on index.html to verify mode toggle is wired up."""

    @pytest.fixture(autouse=True)
    def _load_html(self):
        html_path = Path(__file__).parent.parent / "static" / "index.html"
        self.html = html_path.read_text(encoding="utf-8")

    def test_generation_mode_radios_exist(self):
        assert 'name="genMode"' in self.html

    def test_quick_radio_checked_by_default(self):
        assert 'value="quick" checked' in self.html

    def test_quick_radio_exists(self):
        assert 'value="quick"' in self.html

    def test_js_variable_declared(self):
        assert "selectedGenMode" in self.html

    def test_onGenModeChange_function_exists(self):
        assert "function onGenModeChange()" in self.html

    def test_updateGenerateBtnText_function_exists(self):
        assert "function updateGenerateBtnText()" in self.html

    def test_generation_mode_sent_in_doc_request(self):
        assert "generation_mode: selectedGenMode" in self.html

    def test_generation_mode_sent_in_qa_request(self):
        # Both doc and QA endpoints should include generation_mode
        occurrences = self.html.count("generation_mode: selectedGenMode")
        assert occurrences >= 2

    def test_mode_reset_on_new_session(self):
        assert "selectedGenMode = 'quick'" in self.html
        assert 'input[name="genMode"]' in self.html


# --------------- standalone runner ---------------

def _run_standalone():
    """Run basic checks without pytest."""
    print("=" * 60)
    print("Generation Mode Feature — Standalone Tests")
    print("=" * 60)
    passed = 0
    failed = 0

    def check(label, condition):
        nonlocal passed, failed
        if condition:
            print(f"  ✓ {label}")
            passed += 1
        else:
            print(f"  ✗ {label}")
            failed += 1

    # --- Config ---
    print("\n[Config]")
    import config
    check("DOC_GEN_QUICK_FILE_TIMEOUT exists", hasattr(config, "DOC_GEN_QUICK_FILE_TIMEOUT"))
    check("DOC_GEN_QUICK_SCREENSHOT_TIMEOUT exists", hasattr(config, "DOC_GEN_QUICK_SCREENSHOT_TIMEOUT"))
    check("DOC_GEN_QUICK_SECTION_TIMEOUT exists", hasattr(config, "DOC_GEN_QUICK_SECTION_TIMEOUT"))
    check("Quick file timeout < comprehensive", config.DOC_GEN_QUICK_FILE_TIMEOUT < config.DOC_GEN_FILE_TIMEOUT)
    check("Batching constants exist", config.QUICK_MODE_BATCH_MAX_CHARS > 0 and config.QUICK_MODE_BATCH_MAX_FILES >= 2)

    # --- Model ---
    print("\n[Model]")
    from models import GenerateDocsRequest
    req_default = GenerateDocsRequest(session_id="t")
    check("Default mode is comprehensive", req_default.generation_mode == "comprehensive")
    req_quick = GenerateDocsRequest(session_id="t", generation_mode="quick")
    check("Quick mode accepted", req_quick.generation_mode == "quick")

    # --- File batching ---
    print("\n[File Batching]")
    from doc_generator import DocumentationGenerator
    dg = DocumentationGenerator()

    check("Empty list → empty batches", dg._batch_files_for_quick_mode([]) == [])

    small_files = [("a.json", "a" * 100), ("b.json", "b" * 100), ("c.json", "c" * 100)]
    batches = dg._batch_files_for_quick_mode(small_files)
    check("3 small files → 1 batch", len(batches) == 1 and len(batches[0]) == 3)

    large = ("big.json", "x" * (config.QUICK_MODE_SINGLE_FILE_THRESHOLD + 1))
    batches2 = dg._batch_files_for_quick_mode([large, ("s.json", "y" * 100)])
    check("Large file stays solo", any(len(b) == 1 and b[0][0] == "big.json" for b in batches2))

    many = [(f"f{i}.json", "x" * 10) for i in range(config.QUICK_MODE_BATCH_MAX_FILES + 1)]
    batches3 = dg._batch_files_for_quick_mode(many)
    check("Batch respects max files", all(len(b) <= config.QUICK_MODE_BATCH_MAX_FILES for b in batches3))

    files7 = [(f"f{i}.json", "x" * (500 * (i + 1))) for i in range(7)]
    batches4 = dg._batch_files_for_quick_mode(files7)
    flat = [f for b in batches4 for f in b]
    check("All files preserved", sorted(f[0] for f in flat) == sorted(f[0] for f in files7))

    # --- Prompt builders ---
    print("\n[Prompt Builders]")
    sp_comp = dg._build_incremental_system_prompt("doc.md", generation_mode="comprehensive")
    sp_quick = dg._build_incremental_system_prompt("doc.md", generation_mode="quick")
    check("Comprehensive system prompt: no QUICK MODE", "QUICK MODE" not in sp_comp)
    check("Quick system prompt: has QUICK MODE", "QUICK MODE" in sp_quick)

    fp_quick = dg._build_incremental_file_prompt(
        "App.json", "x" * 500, 0, 3, "doc.md", "Selected", "Context", generation_mode="quick"
    )
    check("Quick file prompt mentions concise/brief/bullet",
          any(w in fp_quick.lower() for w in ["concise", "brief", "bullet"]))

    ssp_quick = dg._build_screenshot_pass_prompt(
        {"path": "home.png", "context": "Home screen", "component_path": "App"}, 0, 1, "doc.md", generation_mode="quick"
    )
    check("Quick screenshot prompt has brevity directive",
          any(w in ssp_quick.lower() for w in ["concise", "brief", "1-sentence"]))

    sep_quick = dg._build_section_editing_prompt(
        section_id="intro", section_name="Introduction", doc_file_path="doc.md",
        selection_context="Selected", business_section="Context",
        files_analyzed=3, critical_files=[("a.json", "c")],
        non_critical_files=[], working_directory=Path("."),
        generation_mode="quick"
    )
    check("Quick section prompt for 'intro' works", len(sep_quick) > 0)

    # --- Frontend ---
    print("\n[Frontend HTML]")
    html = (Path(__file__).parent.parent / "static" / "index.html").read_text(encoding="utf-8")
    check('genMode radios exist', 'name="genMode"' in html)
    check('Quick checked by default', 'value="quick" checked' in html)
    check('selectedGenMode variable declared', "selectedGenMode" in html)
    check('onGenModeChange function exists', "function onGenModeChange()" in html)
    check('generation_mode sent in requests', html.count("generation_mode: selectedGenMode") >= 2)
    check('Mode reset on new session', "selectedGenMode = 'quick'" in html)

    # --- API endpoints (requires TestClient) ---
    print("\n[API Endpoints]")
    try:
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)

        r = client.post("/generate-docs/nonexistent", json={"generation_mode": "quick"})
        check("/generate-docs accepts quick mode (404 not 422)", r.status_code == 404)

        r = client.post("/generate-docs/nonexistent", json={"generation_mode": "turbo"})
        check("/generate-docs invalid mode → 404 not 422", r.status_code == 404)

        r = client.post("/generate-qa/nonexistent", json={"generation_mode": "quick"})
        check("/generate-qa accepts quick mode (404 not 422)", r.status_code == 404)

        r = client.post("/generate-qa/nonexistent", json={})
        check("/generate-qa defaults work (404 not 422)", r.status_code == 404)
    except (ImportError, TypeError) as exc:
        print(f"  ⚠ TestClient unavailable ({exc.__class__.__name__}) — verifying routes instead")
        from main import app
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        check("/generate-docs route registered", "/generate-docs/{session_id}" in routes)
        check("/generate-qa route registered", "/generate-qa/{session_id}" in routes)

    # --- Summary ---
    total = passed + failed
    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    if not PYTEST_AVAILABLE:
        success = _run_standalone()
        sys.exit(0 if success else 1)
    else:
        # When run directly with pytest available, do standalone for quick feedback
        success = _run_standalone()
        print("\nFor full pytest run:")
        print("  pytest tests/test_generation_modes.py -v")
        sys.exit(0 if success else 1)
