"""FastAPI application for Power Platform Documentation Generator"""
from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect, Body, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Dict, Optional
import asyncio
import logging
from pathlib import Path
import shutil
import json
import re

import config
from models import (
    UploadResponse,
    AnalysisStatus,
    AnalysisProgress,
    ChatRequest,
    ChatResponse,
    DocumentationFiles,
    SolutionComponent,
    ComponentType,
    ComponentsListResponse,
    ComponentSelectionRequest,
    ComponentSelectionResponse,
    GenerateDocsRequest,
    ScreenshotMetadata,
    ScreenshotUploadResponse,
    ScreenshotListResponse
)
from utils import (
    generate_session_id,
    get_session_dir,
    get_output_dir,
    extract_zip,
    find_msapp_files,
    find_flow_files,
    cleanup_session,
    is_valid_solution_structure,
    check_pac_cli_available,
    unpack_all_msapps
)
from utils.docx_renderer import render_markdown_to_docx
from session_manager import SessionManager
from analyze_solution_detailed import SolutionAnalyzer
from doc_generator import get_doc_generator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global session manager
session_manager = SessionManager()

# Per-session generation counter: incremented each time the user (re-)submits a
# component selection or resets the chat.  Background tasks capture their generation
# at start-up and abort before creating a Copilot session when they are stale.
_selection_generation: Dict[str, int] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    logger.info("Starting Power Platform Documentation Generator")
    
    # Check prerequisites
    pac_available = await check_pac_cli_available()
    if not pac_available:
        logger.warning(
            "Power Platform CLI is not available. Canvas app unpacking will not work. "
            "Use 'dnx Microsoft.PowerApps.CLI.Tool --yes' (requires .NET 10+) "
            "or download from: https://aka.ms/PowerAppsCLI"
        )
    else:
        if config.USE_DNX:
            logger.info("Power Platform CLI available via dnx (no-install mode)")
        else:
            logger.info("Power Platform CLI (pac) is available")
    
    # Clean up any stale temp directories left over from a previous server run
    if config.TEMP_DIR.exists():
        for stale_dir in config.TEMP_DIR.iterdir():
            if stale_dir.is_dir():
                shutil.rmtree(stale_dir, ignore_errors=True)
                logger.info(f"Removed stale temp directory: {stale_dir.name}")

    # Initialize session manager (no session restoration - start fresh each time)
    await session_manager.initialize(restore_sessions=False)

    yield
    
# Create FastAPI app
app = FastAPI(
    title="Power Platform Documentation Generator",
    description="Analyze and document Power Platform solutions using GitHub Copilot SDK",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Power Platform Documentation Generator",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    pac_available = await check_pac_cli_available()
    return {
        "status": "healthy",
        "pac_cli_available": pac_available,
        "active_sessions": len(session_manager.sessions)
    }


@app.get("/sessions")
async def list_sessions():
    """
    List all available sessions (both active and pending)
    """
    sessions = []
    seen_session_ids = set()
    
    # First, add all active Copilot sessions
    for session_id, managed_session in session_manager.sessions.items():
        seen_session_ids.add(session_id)
        session_dir = get_session_dir(session_id)
        extract_dir = session_dir / "extracted"
        
        # Check if solution.xml exists to get solution name
        solution_name = "Unknown"
        solution_xml = extract_dir / "solution.xml"
        if not solution_xml.exists():
            solution_xml = extract_dir / "Other" / "solution.xml"
        
        if solution_xml.exists():
            try:
                import xml.etree.ElementTree as ET
                tree = ET.parse(solution_xml)
                root = tree.getroot()
                unique_name_elem = root.find(".//UniqueName")
                if unique_name_elem is not None:
                    solution_name = unique_name_elem.text
            except Exception:
                pass
        
        sessions.append({
            "session_id": session_id,
            "solution_name": solution_name,
            "created_at": managed_session.created_at.isoformat(),
            "last_activity": managed_session.last_activity.isoformat(),
            "status": "ready"
        })
    
    # Also check temp directory for sessions being processed
    if config.TEMP_DIR.exists():
        for session_dir in config.TEMP_DIR.iterdir():
            if not session_dir.is_dir():
                continue
            
            session_id = session_dir.name
            if session_id in seen_session_ids:
                continue  # Already listed above
            
            # Find the uploaded ZIP file to get the filename
            zip_files = list(session_dir.glob("*.zip"))
            filename = zip_files[0].name if zip_files else "Unknown"
            
            sessions.append({
                "session_id": session_id,
                "solution_name": filename.replace(".zip", ""),
                "created_at": datetime.fromtimestamp(session_dir.stat().st_ctime).isoformat(),
                "last_activity": datetime.fromtimestamp(session_dir.stat().st_mtime).isoformat(),
                "status": "processing"
            })
    
    # Sort by last activity (most recent first)
    sessions.sort(key=lambda x: x.get("last_activity", 0), reverse=True)
    
    return {"sessions": sessions}


@app.post("/upload", response_model=UploadResponse)
async def upload_solution(file: UploadFile = File(...)):
    """
    Upload a Power Platform solution ZIP file
    """
    try:
        # Validate file
        if not file.filename.endswith('.zip'):
            raise HTTPException(status_code=400, detail="File must be a ZIP archive")
        
        # Check file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset
        
        if file_size > config.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size {file_size} exceeds maximum {config.MAX_UPLOAD_SIZE}"
            )
        
        # Generate session ID
        session_id = generate_session_id()
        session_dir = get_session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Save uploaded file
        zip_path = session_dir / file.filename
        with open(zip_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)
        
        logger.info(f"Uploaded {file.filename} for session {session_id}")
        
        # Extract ZIP
        extract_dir = session_dir / "extracted"
        await extract_zip(zip_path, extract_dir)
        
        # Validate solution structure
        if not is_valid_solution_structure(extract_dir):
            cleanup_session(session_id)
            raise HTTPException(
                status_code=400,
                detail="Invalid solution structure. Please upload a valid Power Platform solution ZIP file."
            )
        
        logger.info(f"Solution extracted for session {session_id}")
        
        return UploadResponse(
            session_id=session_id,
            filename=file.filename,
            status=AnalysisStatus.EXTRACTED,
            message="Solution uploaded and extracted successfully."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error uploading file")
        raise HTTPException(status_code=500, detail=str(e))


def _get_canvas_app_display_name(msapp_file: Path, extract_dir: Path) -> str:
    """
    Generate human-readable display name from Canvas App filename.
    Note: Canvas Apps are unpacked AFTER selection, so manifest is not available yet.
    Examples:
    - cr6b0_deliveryassessmentca_f54e1_DocumentUri.msapp -> Delivery Assessment
    - cr6b0_projectpricingapp_60712_DocumentUri.msapp -> Project Pricing App
    """
    app_name = msapp_file.stem
    
    # Remove _DocumentUri or _BackgroundImageUri suffix if present
    app_name = re.sub(r'_(DocumentUri|BackgroundImageUri|AdditionalUris.*)$', '', app_name)
    
    if '_' not in app_name:
        return app_name.replace('-', ' ').title()
    
    parts = app_name.split('_')
    
    # Remove publisher prefix (first part if it matches pattern like cr6b0, cr49f, etc.)
    if len(parts) > 1 and len(parts[0]) <= 6 and re.match(r'^[a-z]{2}[0-9a-z]+$', parts[0]):
        parts = parts[1:]
    
    # Remove GUID-like suffix (last part if it's short alphanumeric like f54e1, 60712, etc.)
    if len(parts) > 1 and len(parts[-1]) <= 6 and parts[-1].replace('-', '').isalnum():
        parts = parts[:-1]
    
    # Join remaining parts and clean up common abbreviations
    name = '_'.join(parts)
    
    # Remove common suffixes like 'ca' (canvas app), 'app', etc. if they're standalone
    name = re.sub(r'\b(ca|app)$', '', name, flags=re.IGNORECASE)
    
    # Replace underscores with spaces and title case
    return name.replace('_', ' ').strip().title()


def _get_classic_workflow_display_name(xaml_file: Path) -> str:
    """Extract display name from a classic workflow / business rule XAML file."""
    name = xaml_file.stem
    # Remove GUID suffix
    cleaned = re.sub(r'-[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$', '', name, flags=re.IGNORECASE)
    cleaned = re.sub(r'([a-z])([A-Z])', r'\1 \2', cleaned)
    cleaned = cleaned.replace('-', ' ').replace('_', ' ')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned.title() if cleaned else name


def _get_formula_display_name(formula_file: Path) -> str:
    """Extract display name from a Dataverse formula definition file."""
    name = formula_file.stem
    # Pattern: <publisher>_<entity>-FormulaDefinitions  or  <publisher>_<entity>-<field>.xaml
    # Remove publisher prefix (e.g. cr39c_)
    cleaned = re.sub(r'^[a-z0-9]+_', '', name, flags=re.IGNORECASE)
    # Replace separators
    cleaned = cleaned.replace('-', ' - ').replace('_', ' ')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned.title() if cleaned else name


def _get_flow_display_name(flow_file: Path) -> str:
    """
    Extract human-readable display name from Power Automate flow definition.
    Falls back to cleaned filename if definition is not available or doesn't contain display name.
    Examples:
    - CreateaProjectwhenanOpportunityisCreated-D57D6B46...json -> Create A Project When An Opportunity Is Created
    - SendemailtoMMwhenOpportunitystatuschanges-6B1B5831...json -> Send Email To MM When Opportunity Status Changes
    """
    flow_name = flow_file.stem
    
    # Remove GUID suffix (pattern: -XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX)
    cleaned = re.sub(r'-[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$', '', flow_name, flags=re.IGNORECASE)
    
    # Split camelCase into words (e.g., CreateaProject -> Create a Project)
    # Insert space before capital letters
    cleaned = re.sub(r'([a-z])([A-Z])', r'\1 \2', cleaned)
    
    # Replace hyphens and underscores with spaces
    cleaned = cleaned.replace('-', ' ').replace('_', ' ')
    
    # Clean up any double spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # Title case
    return cleaned.title()


@app.get("/components/{session_id}", response_model=ComponentsListResponse)
async def list_components(session_id: str):
    """
    List all available components (Canvas Apps and Power Automate flows) in the solution
    """
    try:
        session_dir = get_session_dir(session_id)
        extract_dir = session_dir / "extracted"
        
        if not session_dir.exists() or not extract_dir.exists():
            raise HTTPException(status_code=404, detail="Session not found")
        
        components = []
        
        # Find Canvas Apps (.msapp files in CanvasApps folder)
        canvas_apps_dir = extract_dir / "CanvasApps"
        if canvas_apps_dir.exists():
            for msapp_file in canvas_apps_dir.glob("*.msapp"):
                display_name = _get_canvas_app_display_name(msapp_file, extract_dir)
                components.append(SolutionComponent(
                    name=msapp_file.stem,
                    path=str(msapp_file.relative_to(extract_dir)),
                    type=ComponentType.CANVAS_APP,
                    display_name=display_name
                ))
        
        # Find Power Automate flows (JSON files in Workflows folder)
        workflows_dir = extract_dir / "Workflows"
        if workflows_dir.exists():
            for flow_file in workflows_dir.glob("*.json"):
                # Skip the workflow-related metadata files
                if not flow_file.stem.endswith("-ConnectionReferences"):
                    display_name = _get_flow_display_name(flow_file)
                    components.append(SolutionComponent(
                        name=flow_file.stem,
                        path=str(flow_file.relative_to(extract_dir)),
                        type=ComponentType.POWER_AUTOMATE,
                        display_name=display_name
                    ))
        
        # Find classic workflows / business rules (XAML files in Workflows folder)
        if workflows_dir.exists():
            for xaml_file in workflows_dir.glob("*.xaml"):
                display_name = _get_classic_workflow_display_name(xaml_file)
                components.append(SolutionComponent(
                    name=xaml_file.stem,
                    path=str(xaml_file.relative_to(extract_dir)),
                    type=ComponentType.CLASSIC_WORKFLOW,
                    display_name=display_name
                ))
        
        # Find Dataverse formula definitions (Formulas folder)
        formulas_dir = extract_dir / "Formulas"
        if formulas_dir.exists():
            for formula_file in sorted(formulas_dir.iterdir()):
                if formula_file.suffix in ('.yaml', '.xaml'):
                    display_name = _get_formula_display_name(formula_file)
                    components.append(SolutionComponent(
                        name=formula_file.stem,
                        path=str(formula_file.relative_to(extract_dir)),
                        type=ComponentType.DATAVERSE_FORMULA,
                        display_name=display_name
                    ))
        
        logger.info(f"Found {len(components)} components for session {session_id}")
        
        return ComponentsListResponse(
            session_id=session_id,
            components=components,
            message=f"Found {len(components)} components"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error listing components for session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/select-components", response_model=ComponentSelectionResponse)
async def select_components(request: ComponentSelectionRequest):
    """
    Select components for documentation and unpack .msapp files if needed
    """
    try:
        session_id = request.session_id
        session_dir = get_session_dir(session_id)
        extract_dir = session_dir / "extracted"
        
        if not session_dir.exists() or not extract_dir.exists():
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Save selected components to session
        selection_file = session_dir / "selected_components.json"
        with open(selection_file, 'w', encoding='utf-8') as f:
            json.dump(request.selected_components, f, indent=2)
        
        logger.info(f"Selected {len(request.selected_components)} components for session {session_id}")
        
        # Bump the generation counter so any still-running task from a previous
        # selection knows it is now stale and should not create a new session.
        _selection_generation[session_id] = _selection_generation.get(session_id, 0) + 1
        current_gen = _selection_generation[session_id]
        
        # Start unpacking in background
        asyncio.create_task(unpack_selected_components(session_id, request.selected_components, current_gen))
        
        return ComponentSelectionResponse(
            session_id=session_id,
            status=AnalysisStatus.UNPACKING,
            message="Components selected. Unpacking .msapp files...",
            selected_count=len(request.selected_components)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error selecting components")
        raise HTTPException(status_code=500, detail=str(e))


async def unpack_selected_components(session_id: str, selected_paths: List[str], generation: int = 0):
    """
    Background task to unpack selected .msapp files and prepare for analysis
    """
    try:
        session_dir = get_session_dir(session_id)
        extract_dir = session_dir / "extracted"
        
        # Filter only .msapp files
        msapp_paths = [p for p in selected_paths if p.endswith('.msapp')]
        
        if msapp_paths:
            logger.info(f"Unpacking {len(msapp_paths)} canvas apps for session {session_id}")
            msapp_files = [extract_dir / p for p in msapp_paths]
            unpack_results = await unpack_all_msapps(msapp_files, extract_dir)
            
            for app_name, (success, error) in unpack_results.items():
                if success:
                    logger.info(f"Successfully unpacked {app_name}")
                else:
                    logger.error(f"Failed to unpack {app_name}: {error}")
        
        # Guard against stale tasks: if the user went back and submitted a new
        # selection while this task was running, skip session creation entirely.
        if _selection_generation.get(session_id, 0) != generation:
            logger.info(f"Aborting stale unpack task for {session_id} (task gen={generation}, current gen={_selection_generation.get(session_id, 0)})")
            return
        
        # Destroy existing session if it exists (to ensure fresh context with the new selection)
        existing_session = session_manager.get_session(session_id)
        if existing_session:
            logger.info(f"Destroying existing session for {session_id} to recreate with updated selected components")
            await session_manager.destroy_session(session_id)
        
        # Create Copilot session for analysis using the exact selection from this request
        copilot_session = await session_manager.create_session(
            session_id=session_id,
            working_directory=extract_dir,
            selected_components=selected_paths
        )
        
        logger.info(f"Session {session_id} is ready for documentation generation with {len(selected_paths)} selected components")
        
    except Exception as e:
        logger.exception(f"Error unpacking components for session {session_id}")


@app.get("/app-screens/{session_id}")
async def get_app_screens(session_id: str):
    """
    Return the list of individual screens/flows available for screenshot assignment.
    Must be called after component selection and unpacking is complete.
    For Canvas Apps: lists each screen's .fx.yaml file found in the unpacked _src folder.
    For Power Automate flows: lists each selected workflow JSON.
    """
    session_dir = get_session_dir(session_id)
    extract_dir = session_dir / "extracted"

    if not session_dir.exists() or not extract_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    # Load the selected component paths
    selection_file = session_dir / "selected_components.json"
    selected_components: List[str] = []
    if selection_file.exists():
        with open(selection_file, "r", encoding="utf-8") as f:
            selected_components = json.load(f)

    screens: List[dict] = []

    logger.info(f"[app-screens] session={session_id}, selected_components={selected_components}")

    for sel in selected_components:
        normalized = sel.replace("\\", "/")

        if normalized.endswith(".msapp"):
            # Canvas App — look for unpacked _src directory
            msapp_stem = Path(normalized).stem
            logger.info(f"[app-screens] Looking for _src dir matching stem '{msapp_stem}' in {extract_dir}")
            src_dir: Optional[Path] = None
            for item in extract_dir.rglob("*_src"):
                logger.info(f"[app-screens]   candidate: {item.name} is_dir={item.is_dir()}")
                if item.is_dir() and item.name.startswith(msapp_stem):
                    src_dir = item
                    break

            if src_dir is None:
                logger.warning(f"[app-screens] No _src directory found for {sel}")
                continue

            display_name = _get_canvas_app_display_name(
                extract_dir / normalized, extract_dir
            )

            # Discover individual screen .fx.yaml files in Src/ subfolder
            src_folder = src_dir / "Src"
            logger.info(f"[app-screens] Checking Src folder: {src_folder} exists={src_folder.exists()}")
            if src_folder.exists():
                fx_files = sorted(src_folder.glob("*.fx.yaml"))
            else:
                # Fallback: search recursively for .fx.yaml anywhere under _src
                logger.info(f"[app-screens] Src/ not found, falling back to rglob in {src_dir}")
                fx_files = sorted(src_dir.rglob("*.fx.yaml"))
            logger.info(f"[app-screens] Found {len(fx_files)} .fx.yaml files: {[f.name for f in fx_files]}")
            for fx_file in fx_files:
                # .stem only strips last extension (.yaml), so "Home.fx.yaml" → "Home.fx"
                screen_name = fx_file.name.replace(".fx.yaml", "")
                rel_path = str(fx_file.relative_to(extract_dir)).replace("\\", "/")
                screens.append({
                    "path": rel_path,
                    "display_name": f"{display_name} → {screen_name}",
                    "type": "canvas_screen",
                    "app_path": sel,
                })

            # If no screens found, fall back to the entire app as one item
            if not any(s.get("app_path") == sel for s in screens):
                screens.append({
                    "path": sel,
                    "display_name": display_name,
                    "type": "canvas_app",
                    "app_path": sel,
                })

        elif normalized.startswith("Workflows/") and normalized.endswith(".json"):
            flow_file = extract_dir / normalized
            if flow_file.exists():
                display_name = _get_flow_display_name(flow_file)
                screens.append({
                    "path": sel,
                    "display_name": display_name,
                    "type": "power_automate",
                    "app_path": None,
                })

    logger.info(f"[app-screens] Returning {len(screens)} screens for session {session_id}")
    return {"session_id": session_id, "screens": screens}


# ==========================================
# Screenshot/Image Management Endpoints
# ==========================================

def _get_screenshots_dir(session_id: str) -> Path:
    """Get the screenshots directory for a session"""
    return get_session_dir(session_id) / "screenshots"


def _load_screenshot_metadata(session_id: str) -> List[ScreenshotMetadata]:
    """Load screenshot metadata from session directory"""
    meta_file = _get_screenshots_dir(session_id) / "metadata.json"
    if not meta_file.exists():
        return []
    with open(meta_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [ScreenshotMetadata(**item) for item in data]


def _save_screenshot_metadata(session_id: str, screenshots: List[ScreenshotMetadata]):
    """Save screenshot metadata to session directory"""
    meta_dir = _get_screenshots_dir(session_id)
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta_file = meta_dir / "metadata.json"
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump([s.model_dump(mode='json') for s in screenshots], f, indent=2, default=str)


def _post_process_screenshots(
    markdown: str,
    screenshots: List[ScreenshotMetadata],
    screenshots_dir: Path
) -> str:
    """
    Post-process generated markdown to:
    1. Replace absolute screenshot paths with relative images/ paths
    2. Replace base64 embedded images with relative paths
    3. Ensure ALL screenshots are referenced in the document
    """
    if not screenshots:
        return markdown

    # Build lookup by filename
    ss_by_filename = {ss.filename: ss for ss in screenshots}
    # Build lookup by sanitized context (as used in base64 alt text)
    ss_by_context = {}
    for ss in screenshots:
        safe_ctx = ss.context.replace('[', '(').replace(']', ')').replace('|', '-')
        ss_by_context[safe_ctx.strip()] = ss
        ss_by_context[ss.context.strip()] = ss

    referenced_filenames = set()

    # Parse markdown, finding all ![alt](url) image references
    # Use iterative parsing to handle large base64 strings without regex backtracking
    result_parts = []
    pos = 0
    while pos < len(markdown):
        img_start = markdown.find('![', pos)
        if img_start == -1:
            result_parts.append(markdown[pos:])
            break

        # Add text before this image reference
        result_parts.append(markdown[pos:img_start])

        # Find ]( after the alt text
        bracket_end = markdown.find('](', img_start + 2)
        if bracket_end == -1:
            result_parts.append(markdown[img_start:])
            break

        alt_text = markdown[img_start + 2:bracket_end]

        # Find closing ) for the URL
        paren_start = bracket_end + 2
        paren_end = markdown.find(')', paren_start)
        if paren_end == -1:
            result_parts.append(markdown[img_start:])
            break

        url = markdown[paren_start:paren_end]
        original = markdown[img_start:paren_end + 1]

        # Case 1: Absolute path containing screenshots directory
        if 'screenshots' in url.replace('\\', '/').lower():
            filename = Path(url.replace('\\', '/')).name
            if filename in ss_by_filename:
                referenced_filenames.add(filename)
                result_parts.append(f"![{alt_text}](images/{filename})")
            else:
                result_parts.append(original)

        # Case 2: Base64 embedded image
        elif url.startswith('data:image/'):
            matched = False
            # Try exact context match
            if alt_text.strip() in ss_by_context:
                ss = ss_by_context[alt_text.strip()]
                if ss.filename not in referenced_filenames:
                    referenced_filenames.add(ss.filename)
                    result_parts.append(f"![{alt_text}](images/{ss.filename})")
                    matched = True
            # Try fuzzy match by word overlap
            if not matched:
                alt_words = set(alt_text.lower().split())
                best_match = None
                best_score = 0
                for ss in screenshots:
                    if ss.filename not in referenced_filenames:
                        ctx_words = set(ss.context.lower().split())
                        score = len(alt_words & ctx_words)
                        if score > best_score and score >= 2:
                            best_score = score
                            best_match = ss
                if best_match:
                    referenced_filenames.add(best_match.filename)
                    result_parts.append(f"![{alt_text}](images/{best_match.filename})")
                    matched = True
            if not matched:
                # Can't determine which screenshot - leave as is but try first unreferenced
                for ss in screenshots:
                    if ss.filename not in referenced_filenames:
                        referenced_filenames.add(ss.filename)
                        result_parts.append(f"![{alt_text}](images/{ss.filename})")
                        matched = True
                        break
            if not matched:
                result_parts.append(original)
        else:
            # Track already-correct images/ references so they aren't re-appended
            if url.startswith('images/'):
                fname = url[len('images/'):]
                if fname in ss_by_filename:
                    referenced_filenames.add(fname)
            result_parts.append(original)

        pos = paren_end + 1

    markdown = ''.join(result_parts)

    # Now ensure ALL screenshots are referenced - append missing ones
    missing = [ss for ss in screenshots if ss.filename not in referenced_filenames]
    if missing:
        # Try to find "### 8.2 Screenshots" section
        section_patterns = ["### 8.2 Screenshots", "### 8.2", "## 8. Appendices", "## 8."]
        insert_pos = -1
        for pattern in section_patterns:
            idx = markdown.find(pattern)
            if idx != -1:
                # Find end of heading line
                line_end = markdown.find('\n', idx)
                if line_end != -1:
                    insert_pos = line_end + 1
                break

        missing_block = "\n"
        for ss in missing:
            missing_block += f"![{ss.context}](images/{ss.filename})\n\n"
            missing_block += f"*{ss.context}*\n\n"

        if insert_pos != -1:
            markdown = markdown[:insert_pos] + missing_block + markdown[insert_pos:]
        else:
            markdown += "\n\n## Screenshots\n" + missing_block

    return markdown


@app.post("/screenshots/{session_id}", response_model=ScreenshotUploadResponse)
async def upload_screenshots(
    session_id: str,
    files: List[UploadFile] = File(...),
    contexts: str = Form(default="[]"),
    component_paths: str = Form(default="[]")
):
    """
    Upload one or more screenshots with context descriptions.
    
    - files: Image files (png, jpg, jpeg, gif, webp)
    - contexts: JSON array of context strings, one per file
    - component_paths: JSON array of component paths (or null for global), one per file
    """
    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Reject uploads if unpacking has not completed yet
    if not session_manager.get_session(session_id):
        raise HTTPException(
            status_code=409,
            detail="Components are still being unpacked. Please wait for unpacking to finish before uploading screenshots."
        )
    
    # Parse JSON form fields
    try:
        context_list = json.loads(contexts)
        component_path_list = json.loads(component_paths)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in contexts or component_paths")
    
    # Validate lengths match
    if len(context_list) != len(files):
        raise HTTPException(
            status_code=400, 
            detail=f"Number of contexts ({len(context_list)}) must match number of files ({len(files)})"
        )
    if len(component_path_list) != len(files):
        raise HTTPException(
            status_code=400, 
            detail=f"Number of component_paths ({len(component_path_list)}) must match number of files ({len(files)})"
        )
    
    # Load existing screenshots
    existing = _load_screenshot_metadata(session_id)
    
    # Check limits
    if len(existing) + len(files) > config.MAX_SCREENSHOTS_PER_SESSION:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {config.MAX_SCREENSHOTS_PER_SESSION} screenshots per session. Currently have {len(existing)}."
        )
    
    screenshots_dir = _get_screenshots_dir(session_id)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    new_screenshots = []
    
    for i, file in enumerate(files):
        # Validate file extension
        ext = Path(file.filename or "").suffix.lower()
        if ext not in config.ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File '{file.filename}' has unsupported type '{ext}'. Allowed: {', '.join(config.ALLOWED_IMAGE_EXTENSIONS)}"
            )
        
        # Validate content type
        if file.content_type and file.content_type not in config.ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"File '{file.filename}' has unsupported content type '{file.content_type}'"
            )
        
        # Read and validate size
        content = await file.read()
        if len(content) > config.MAX_SCREENSHOT_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File '{file.filename}' exceeds maximum size of {config.MAX_SCREENSHOT_SIZE // (1024*1024)}MB"
            )
        
        # Generate unique ID and save
        screenshot_id = generate_session_id()
        saved_filename = f"{screenshot_id}{ext}"
        save_path = screenshots_dir / saved_filename
        save_path.write_bytes(content)
        
        mime_type = file.content_type or f"image/{ext.lstrip('.')}"
        component_path = component_path_list[i] if component_path_list[i] else None
        
        metadata = ScreenshotMetadata(
            id=screenshot_id,
            filename=saved_filename,
            context=context_list[i] or "",
            component_path=component_path,
            mime_type=mime_type
        )
        new_screenshots.append(metadata)
        logger.info(f"Saved screenshot {saved_filename} for session {session_id} (component: {component_path or 'global'})")
    
    # Merge with existing and save
    all_screenshots = existing + new_screenshots
    _save_screenshot_metadata(session_id, all_screenshots)
    
    return ScreenshotUploadResponse(
        session_id=session_id,
        screenshots=all_screenshots,
        message=f"Uploaded {len(new_screenshots)} screenshot(s). Total: {len(all_screenshots)}"
    )


@app.get("/screenshots/{session_id}", response_model=ScreenshotListResponse)
async def list_screenshots(session_id: str):
    """List all screenshots for a session"""
    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    
    screenshots = _load_screenshot_metadata(session_id)
    return ScreenshotListResponse(session_id=session_id, screenshots=screenshots)


@app.delete("/screenshots/{session_id}/{screenshot_id}")
async def delete_screenshot(session_id: str, screenshot_id: str):
    """Delete a specific screenshot"""
    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    
    screenshots = _load_screenshot_metadata(session_id)
    target = next((s for s in screenshots if s.id == screenshot_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    
    # Delete the image file
    image_path = _get_screenshots_dir(session_id) / target.filename
    if image_path.exists():
        image_path.unlink()
    
    # Update metadata
    screenshots = [s for s in screenshots if s.id != screenshot_id]
    _save_screenshot_metadata(session_id, screenshots)
    
    return JSONResponse(content={"message": "Screenshot deleted", "remaining": len(screenshots)})


@app.get("/screenshots/{session_id}/{screenshot_id}/image")
async def get_screenshot_image(session_id: str, screenshot_id: str):
    """Serve a screenshot image for preview"""
    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    
    screenshots = _load_screenshot_metadata(session_id)
    target = next((s for s in screenshots if s.id == screenshot_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    
    image_path = _get_screenshots_dir(session_id) / target.filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")
    
    return FileResponse(path=image_path, media_type=target.mime_type)


@app.get("/status/{session_id}", response_model=AnalysisProgress)
async def get_status(session_id: str):
    """
    Get the status of an analysis session
    """
    session_dir = get_session_dir(session_id)
    
    # Check if session directory exists
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check if Copilot session exists (unpacking complete)
    copilot_session = session_manager.get_session(session_id)
    
    if copilot_session:
        # Copilot session exists - unpacking complete, ready for chat
        return AnalysisProgress(
            session_id=session_id,
            status=AnalysisStatus.ANALYZING,
            progress_percent=75,
            current_step="Ready for documentation generation and chat"
        )
    
    # Check if components have been selected
    selection_file = session_dir / "selected_components.json"
    if selection_file.exists():
        # Components selected, unpacking in progress
        return AnalysisProgress(
            session_id=session_id,
            status=AnalysisStatus.UNPACKING,
            progress_percent=50,
            current_step="Unpacking canvas apps..."
        )
    
    # Only extracted, waiting for component selection
    return AnalysisProgress(
        session_id=session_id,
        status=AnalysisStatus.EXTRACTED,
        progress_percent=25,
        current_step="Waiting for component selection"
    )


@app.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for interactive chat with the Copilot agent.
    Supports real-time streaming with delta events and tool execution visibility.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for session {session_id}")
    
    try:
        # Get or create Copilot session
        copilot_session = session_manager.get_session(session_id)
        
        if not copilot_session:
            # Session doesn't exist yet - create it
            session_dir = get_session_dir(session_id)
            extract_dir = session_dir / "extracted"
            selection_file = session_dir / "selected_components.json"
            
            if not session_dir.exists() or not extract_dir.exists():
                await websocket.send_json({
                    "type": "error",
                    "error": "Session not found. Please upload a solution to start."
                })
                await websocket.close()
                return
            
            # Load selected components if available
            selected_components = []
            if selection_file.exists():
                try:
                    with open(selection_file, 'r', encoding='utf-8') as f:
                        selected_components = json.load(f)
                    logger.info(f"Loaded {len(selected_components)} selected components for chat context")
                except Exception as e:
                    logger.warning(f"Could not load selected components: {e}")
            
            # Create the Copilot session now
            logger.info(f"Creating Copilot session for {session_id} (on-demand)")
            copilot_session = await session_manager.create_session(
                session_id=session_id,
                working_directory=extract_dir,
                selected_components=selected_components
            )
        
        # Track current processing state
        processing_done = asyncio.Event()
        
        # Event handler for all Copilot events
        def on_event(event):
            event_type = event.type.value if hasattr(event.type, 'value') else str(event.type)
            
            # Log every event received for debugging
            logger.info(f"📨 Copilot event: {event_type}")
            
            try:
                if event_type == "assistant.message_delta":
                    # Streaming text chunks
                    delta_content = event.data.delta_content if hasattr(event.data, 'delta_content') else ""
                    logger.debug(f"   Delta: {len(delta_content)} chars")
                    asyncio.create_task(websocket.send_json({
                        "type": "delta",
                        "content": delta_content or ""
                    }))
                
                elif event_type == "assistant.message":
                    # Complete message
                    content = event.data.content if hasattr(event.data, 'content') else ""
                    logger.info(f"📝 Message: {len(content)} chars")
                    asyncio.create_task(websocket.send_json({
                        "type": "message",
                        "content": content
                    }))
                
                elif event_type == "tool.call":
                    # Tool execution started
                    tool_name = event.data.name if hasattr(event.data, 'name') else "unknown"
                    tool_args = event.data.arguments if hasattr(event.data, 'arguments') else {}
                    asyncio.create_task(websocket.send_json({
                        "type": "tool_call",
                        "tool": tool_name,
                        "args": tool_args
                    }))
                    logger.info(f"🔧 Tool called: {tool_name}")
                
                elif event_type == "tool.result":
                    # Tool execution completed
                    tool_name = event.data.name if hasattr(event.data, 'name') else "unknown"
                    result = event.data.result if hasattr(event.data, 'result') else ""
                    result_str = str(result)
                    result_preview = result_str[:200] if len(result_str) > 200 else result_str
                    asyncio.create_task(websocket.send_json({
                        "type": "tool_result",
                        "tool": tool_name,
                        "preview": result_preview
                    }))
                    logger.info(f"✅ Tool completed: {tool_name}")
                
                elif event_type == "session.idle":
                    # Processing complete
                    logger.info(f"✅ Session idle")
                    asyncio.create_task(websocket.send_json({
                        "type": "idle"
                    }))
                    asyncio.create_task(websocket.send_json({
                        "type": "complete"
                    }))
                    processing_done.set()
                
                elif event_type == "session.compaction_start":
                    logger.info(f"🔄 Compaction start")
                    asyncio.create_task(websocket.send_json({
                        "type": "system",
                        "message": "🔄 Compacting context (large conversation)..."
                    }))
                
                elif event_type == "session.compaction_complete":
                    logger.info(f"✅ Compaction complete")
                    asyncio.create_task(websocket.send_json({
                        "type": "system",
                        "message": "✅ Context compacted successfully"
                    }))
                
                elif event_type == "session.error":
                    # Critical: Session error from Copilot SDK
                    error_msg = "Unknown error"
                    if hasattr(event.data, 'message'):
                        error_msg = event.data.message
                    elif hasattr(event.data, 'error'):
                        error_msg = str(event.data.error)
                    else:
                        error_msg = str(event.data)
                    
                    logger.error(f"❌ Copilot session error: {error_msg}")
                    asyncio.create_task(websocket.send_json({
                        "type": "error",
                        "error": f"Copilot SDK Error: {error_msg}"
                    }))
                    asyncio.create_task(websocket.send_json({
                        "type": "complete"
                    }))
                    processing_done.set()
                
                elif event_type == "assistant.turn_start":
                    logger.info(f"🤖 Assistant turn started")
                
                elif event_type == "assistant.turn_end":
                    logger.info(f"🤖 Assistant turn ended")
                
                elif event_type == "user.message":
                    logger.info(f"👤 User message confirmed")
                
                elif event_type == "session.usage_info":
                    # Token usage information
                    if hasattr(event.data, 'total_tokens'):
                        logger.info(f"📊 Tokens used: {event.data.total_tokens}")
                
                elif event_type == "pending_messages.modified":
                    # Message queue update - can ignore
                    pass
                
                elif event_type == "session.info":
                    # Session info update - can ignore
                    pass
                
                else:
                    # Log truly unexpected event types
                    logger.warning(f"⚠️  Unexpected event type: {event_type}")
                    logger.debug(f"   Event data: {event.data if hasattr(event, 'data') else 'N/A'}")
                
            except Exception as e:
                logger.error(f"❌ Error handling event {event_type}: {e}")
                logger.exception("Event handler exception:")
                try:
                    asyncio.create_task(websocket.send_json({
                        "type": "error",
                        "error": f"Event handling error: {str(e)}"
                    }))
                except:
                    pass
        
        # Register event handler
        copilot_session.on(on_event)
        logger.info(f"Event handler registered for session {session_id}")
        
        # Main message loop
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message = data.get("message", "")
            
            if not message:
                continue
            
            logger.info(f"💬 User message: {message[:100]}...")
            
            # Reset processing state
            processing_done.clear()
            
            # Send typing indicator
            await websocket.send_json({
                "type": "typing",
                "isTyping": True
            })
            
            # Send message to Copilot (non-blocking)
            try:
                logger.info(f"📤 Sending message to Copilot SDK...")
                result = await copilot_session.send({"prompt": message})
                logger.info(f"✅ Message sent to Copilot SDK, result type: {type(result)}")
                
                # Wait for processing to complete or timeout
                try:
                    logger.info(f"⏳ Waiting for Copilot response (max 5 minutes)...")
                    await asyncio.wait_for(processing_done.wait(), timeout=300.0)  # 5 min timeout
                    logger.info(f"✅ Copilot processing complete")
                except asyncio.TimeoutError:
                    logger.error(f"⚠️ Processing timeout for session {session_id} after 5 minutes")
                    await websocket.send_json({
                        "type": "error",
                        "error": "Request timed out after 5 minutes"
                    })
            
            except Exception as e:
                logger.error(f"❌ Error processing chat message: {e}")
                logger.exception("Full error details:")
                await websocket.send_json({
                    "type": "error",
                    "error": str(e)
                })
                # Send complete event to allow client to continue
                await websocket.send_json({
                    "type": "complete"
                })
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.exception(f"WebSocket error for session {session_id}: {e}")
        try:
            await websocket.close()
        except:
            pass


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a session and clean up resources
    """
    try:
        # Destroy Copilot session
        await session_manager.destroy_session(session_id)
        
        # Clean up files
        cleanup_session(session_id)
        
        return {"message": f"Session {session_id} deleted successfully"}
    except Exception as e:
        logger.exception(f"Error deleting session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/session/{session_id}/cleanup")
async def cleanup_session_beacon(session_id: str):
    """
    Clean up a session via POST — used by navigator.sendBeacon on page unload.
    Behaves identically to DELETE /session/{session_id}.
    """
    try:
        await session_manager.destroy_session(session_id)
        cleanup_session(session_id)
        return {"message": f"Session {session_id} cleaned up successfully"}
    except Exception as e:
        logger.exception(f"Error cleaning up session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset-chat-session/{session_id}")
async def reset_chat_session(session_id: str):
    """
    Destroy only the Copilot chat session, keeping uploaded files intact.
    Called when the user navigates back to the component selection screen so that
    the chat restarts with fresh context after the user reconfirms their selection.
    Also bumps the generation counter to invalidate any in-flight unpack tasks.
    """
    try:
        # Invalidate any background task that is still running for the old selection
        _selection_generation[session_id] = _selection_generation.get(session_id, 0) + 1
        await session_manager.destroy_session(session_id)
        return {"message": f"Chat session for {session_id} reset successfully"}
    except Exception as e:
        logger.exception(f"Error resetting chat session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


# IMPROVEMENT 2 & 3: Helper functions for intelligent file processing
def _prioritize_files_for_analysis(file_contents: Dict[str, str]) -> List[tuple]:
    """
    Prioritize files by importance for Power Platform analysis.
    Returns list of (path, content) tuples sorted by priority.
    """
    priority_scores = []
    
    for path, content in file_contents.items():
        score = 0
        path_lower = path.lower()
        
        # HIGHEST priority: PowerApps Power Fx formulas — screens give the most
        # insight about business logic and must always be analyzed first.
        if '.fx.yaml' in path_lower:
            score = 3000
            # Boost for the app-level formula file (global variables, OnStart)
            if 'app.fx.yaml' in path_lower or 'onstart' in path_lower:
                score += 500
        
        # High priority: Dataverse calculated column formulas (server-side logic)
        elif 'formulas/' in path_lower and path_lower.endswith('.yaml'):
            score = 2500
        
        # High priority: Dataverse rollup/BPF XAML formulas
        elif 'formulas/' in path_lower and path_lower.endswith('.xaml'):
            score = 2400
        
        # High priority: Workflows (Power Automate cloud flows)
        # Scored below canvas and Dataverse formulas.
        elif 'workflows' in path_lower and path_lower.endswith('.json'):
            score = 2000
            # Boost for main workflow files (non-connection references)
            if 'connectionreferences' not in path_lower:
                score += 500
        
        # Medium-high priority: Classic workflows / business rules (XAML)
        elif 'workflows' in path_lower and path_lower.endswith('.xaml'):
            score = 1800
        
        # High priority: Manifests (app metadata)
        elif 'canvasmanifest.json' in path_lower:
            score = 900
        elif 'manifest.json' in path_lower:
            score = 850
        
        # Medium-high priority: Data sources
        elif 'datasources' in path_lower:
            score = 700
        
        # Medium priority: Connections
        elif 'connections' in path_lower or 'connectionreferences' in path_lower:
            score = 600
        
        # Medium priority: Screen definitions
        elif 'screens' in path_lower and '.json' in path_lower:
            score = 500
        
        # Medium priority: Component definitions
        elif 'components' in path_lower:
            score = 450
        
        # Lower priority: Editor state
        elif 'editorstate' in path_lower:
            score = 300
        
        # Lower priority: Assets
        elif 'assets' in path_lower:
            score = 200
        
        # Default priority
        else:
            score = 100
        
        priority_scores.append((score, path, content))
    
    # Sort by score (highest first), then by path
    priority_scores.sort(key=lambda x: (-x[0], x[1]))
    
    return [(path, content) for _, path, content in priority_scores]


def _estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens in a text string.
    Rough approximation: 1 token ≈ 4 characters for English text.
    """
    return len(text) // 4


def _separate_critical_files(prioritized_files: List[tuple]) -> tuple:
    """
    Separate critical files (Power Fx formulas, workflows) from non-critical files.
    Returns (critical_files, non_critical_files) where each is a list of (path, content) tuples.
    """
    critical_files = []
    non_critical_files = []
    
    canvas_files = []          # .fx.yaml Power Fx screen formulas
    dataverse_formulas = []     # Formulas/*.yaml calculated columns
    dataverse_xaml = []         # Formulas/*.xaml rollup/BPF definitions
    cloud_flows = []            # Workflows/*.json Power Automate
    classic_workflows = []      # Workflows/*.xaml business rules
    
    for path, content in prioritized_files:
        path_lower = path.lower()
        
        if '.fx.yaml' in path_lower:
            canvas_files.append((path, content))
        elif 'formulas/' in path_lower and path_lower.endswith('.yaml'):
            dataverse_formulas.append((path, content))
        elif 'formulas/' in path_lower and path_lower.endswith('.xaml'):
            dataverse_xaml.append((path, content))
        elif 'workflows' in path_lower and path_lower.endswith('.json') and 'connectionreferences' not in path_lower:
            cloud_flows.append((path, content))
        elif 'workflows' in path_lower and path_lower.endswith('.xaml'):
            classic_workflows.append((path, content))
        else:
            non_critical_files.append((path, content))
    
    # Order: Canvas screens → Dataverse formulas → Cloud flows → Classic workflows
    # Canvas screens give the most insight about business logic.
    # Dataverse formulas define server-side computed columns.
    # Cloud flows contain automation logic.
    # Classic workflows/business rules are supplementary automation.
    critical_files = canvas_files + dataverse_formulas + dataverse_xaml + cloud_flows + classic_workflows
    
    return critical_files, non_critical_files


def _build_non_critical_file_section(non_critical_files: List[tuple]) -> str:
    """
    Build SUMMARY-ONLY section for non-critical files to minimize token usage.
    Critical files get full analysis; non-critical files just get metadata for context.
    """
    if not non_critical_files:
        return "*No additional supporting files.*"
    
    MAX_FILES_TO_LIST = 50  # Limit number of files listed
    
    file_summaries = []
    
    for path, content in non_critical_files[:MAX_FILES_TO_LIST]:
        # Create concise summary without including content
        content_size = len(content)
        summary = _create_file_summary(path, content)
        
        # Ultra-concise format: just filename and one-line summary
        file_summaries.append(f"- **{path}**: {summary}")
    
    result = f"""**Supporting Files ({len(non_critical_files)} total):**

These files provide supporting context (manifests, data sources, assets, editor state) but are not critical business logic:

{chr(10).join(file_summaries[:MAX_FILES_TO_LIST])}
"""
    
    if len(non_critical_files) > MAX_FILES_TO_LIST:
        result += f"\n\n*... and {len(non_critical_files) - MAX_FILES_TO_LIST} more supporting files.*"
    
    # Estimate tokens (should be much lower now)
    estimated_tokens = _estimate_tokens(result)
    logger.info(f"Non-critical section: {len(non_critical_files)} files summarized in ~{estimated_tokens} tokens (was including full content)")
    
    return result


def _create_file_summary(path: str, content: str) -> str:
    """
    Create a concise one-line summary for a file based on its type and content.
    Used for non-critical files to minimize token usage.
    """
    path_lower = path.lower()
    
    try:
        # Power Fx formula files
        if '.fx.yaml' in path_lower:
            lines = content.split('\n')
            return f"Power Fx formulas ({len(lines)} lines)"
        
        # JSON files
        elif path_lower.endswith('.json'):
            if 'canvasmanifest' in path_lower:
                return "Canvas app manifest"
            elif 'datasources' in path_lower:
                return "Data source configuration"
            elif 'editorstate' in path_lower:
                return "UI editor state"
            elif 'connections' in path_lower:
                return "Connection configuration"
            try:
                data = json.loads(content)
                if 'properties' in data and 'definition' in data.get('properties', {}):
                    return "Power Automate Flow definition"
                return f"JSON configuration"
            except:
                return "JSON file"
        
        # XML files
        elif path_lower.endswith('.xml'):
            if 'solution' in path_lower:
                return "Solution manifest"
            return "XML configuration"
        
        # Image/Asset files
        elif any(ext in path_lower for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg']):
            return "Image asset"
        
        # Default
        else:
            return f"Supporting file"
    
    except Exception as e:
        return "Configuration file"


@app.post("/generate-docs/{session_id}", response_model=DocumentationFiles)
async def generate_documentation(
    session_id: str, 
    business_context: Optional[str] = Body(None, embed=True)
):
    """
    Generate documentation using dedicated doc generator (isolated from chat session)
    """
    try:
        # Extract business context if provided
        if business_context:
            business_context = business_context.strip()
            logger.info(f"Business context provided: {business_context[:100]}...")
        
        session_dir = get_session_dir(session_id)
        extract_dir = session_dir / "extracted"
        selection_file = session_dir / "selected_components.json"
        
        # Check if session exists
        if not session_dir.exists() or not extract_dir.exists():
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Load selected components
        selected_components = []
        if selection_file.exists():
            with open(selection_file, 'r', encoding='utf-8') as f:
                selected_components = json.load(f)
        
        logger.info(f"Generating documentation for session {session_id} with {len(selected_components)} selected components")
        
        # NOTE: We don't use the chat copilot session here anymore
        # Documentation generation is now completely isolated from chat
        
        # Build list of files to analyze with EXACT matching
        files_to_analyze = []
        
        # If no components selected, include everything
        if not selected_components:
            logger.info("No components selected - analyzing entire solution")
            # Find all unpacked Canvas Apps (_src folders)
            for item in extract_dir.rglob("*_src"):
                if item.is_dir():
                    files_to_analyze.append(str(item.relative_to(extract_dir)))
            
            # Find all workflow JSON files
            workflows_dir = extract_dir / "Workflows"
            if workflows_dir.exists():
                for json_file in workflows_dir.glob("*.json"):
                    if not json_file.stem.endswith("-ConnectionReferences"):
                        files_to_analyze.append(str(json_file.relative_to(extract_dir)))
            
            # Find classic workflows / business rules (XAML)
            if workflows_dir.exists():
                for xaml_file in workflows_dir.glob("*.xaml"):
                    files_to_analyze.append(str(xaml_file.relative_to(extract_dir)))
            
            # Find Dataverse formula definitions
            formulas_dir = extract_dir / "Formulas"
            if formulas_dir.exists():
                for formula_file in formulas_dir.iterdir():
                    if formula_file.suffix in ('.yaml', '.xaml'):
                        files_to_analyze.append(str(formula_file.relative_to(extract_dir)))
        else:
            logger.info(f"Filtering to {len(selected_components)} selected components")
            
            # Process selected components (normalize path separators for Windows/Unix compatibility)
            for sel in selected_components:
                # Normalize path separators (Windows uses \, Unix uses /)
                normalized_sel = sel.replace('\\', '/')
                
                # Process Canvas Apps
                if normalized_sel.endswith('.msapp'):
                    # Extract app name from path like "CanvasApps/myapp_abc123.msapp"
                    msapp_stem = Path(normalized_sel).stem  # "myapp_abc123"
                    
                    # Find matching _src folder (it will have the same stem)
                    for item in extract_dir.rglob("*_src"):
                        if item.is_dir() and item.name.startswith(msapp_stem):
                            files_to_analyze.append(str(item.relative_to(extract_dir)))
                            logger.info(f"Matched Canvas App: {sel} -> {item.name}")
                            break
                
                # Process Workflow JSON files (Power Automate cloud flows)
                elif normalized_sel.startswith("Workflows/") and normalized_sel.endswith('.json'):
                    selected_filename = Path(normalized_sel).name
                    workflows_dir = extract_dir / "Workflows"
                    if workflows_dir.exists():
                        workflow_file = workflows_dir / selected_filename
                        if workflow_file.exists() and not selected_filename.endswith("-ConnectionReferences.json"):
                            files_to_analyze.append(str(workflow_file.relative_to(extract_dir)))
                            logger.info(f"Matched Workflow: {sel} -> {selected_filename}")
                
                # Process classic workflow / business rule XAML files
                elif normalized_sel.startswith("Workflows/") and normalized_sel.endswith('.xaml'):
                    selected_filename = Path(normalized_sel).name
                    workflows_dir = extract_dir / "Workflows"
                    if workflows_dir.exists():
                        xaml_file = workflows_dir / selected_filename
                        if xaml_file.exists():
                            files_to_analyze.append(str(xaml_file.relative_to(extract_dir)))
                            logger.info(f"Matched Classic Workflow: {sel} -> {selected_filename}")
                
                # Process Dataverse formula definitions
                elif normalized_sel.startswith("Formulas/"):
                    selected_filename = Path(normalized_sel).name
                    formulas_dir = extract_dir / "Formulas"
                    if formulas_dir.exists():
                        formula_file = formulas_dir / selected_filename
                        if formula_file.exists():
                            files_to_analyze.append(str(formula_file.relative_to(extract_dir)))
                            logger.info(f"Matched Formula: {sel} -> {selected_filename}")
        
        logger.info(f"Found {len(files_to_analyze)} files/folders to analyze after filtering")
        
        # Validation: If components were selected but nothing matched, warn user
        if selected_components and not files_to_analyze:
            logger.warning(f"No components matched the selection: {selected_components}")
            logger.warning("This might happen if Canvas Apps weren't unpacked yet or paths don't match")
        
        # Read actual file contents
        file_contents = {}
        for file_path_str in files_to_analyze:
            full_path = extract_dir / file_path_str
            try:
                if full_path.is_dir():
                    # For Canvas Apps (_src folders), read key files
                    manifest_path = full_path / "CanvasManifest.json"
                    if manifest_path.exists():
                        file_contents[f"{file_path_str}/CanvasManifest.json"] = manifest_path.read_text(encoding='utf-8')
                    
                    # Read all .fx.yaml files (formulas)
                    for fx_file in full_path.rglob("*.fx.yaml"):
                        rel_path = fx_file.relative_to(extract_dir)
                        file_contents[str(rel_path)] = fx_file.read_text(encoding='utf-8')
                    
                    # Read DataSources
                    data_sources_dir = full_path / "DataSources"
                    if data_sources_dir.exists():
                        for ds_file in data_sources_dir.glob("*.json"):
                            rel_path = ds_file.relative_to(extract_dir)
                            file_contents[str(rel_path)] = ds_file.read_text(encoding='utf-8')
                    
                    # Read EditorState files
                    editor_state_dir = full_path / "src" / "EditorState"
                    if editor_state_dir.exists():
                        for es_file in editor_state_dir.glob("*.json"):
                            rel_path = es_file.relative_to(extract_dir)
                            file_contents[str(rel_path)] = es_file.read_text(encoding='utf-8')
                else:
                    # For workflow JSON files, read directly
                    file_contents[file_path_str] = full_path.read_text(encoding='utf-8')
            except Exception as e:
                logger.warning(f"Could not read {file_path_str}: {e}")
        
        logger.info(f"Read {len(file_contents)} files totaling {sum(len(c) for c in file_contents.values())} characters")
        
        # Include solution.xml as supplementary context (metadata about the solution)
        solution_xml_path = extract_dir / "solution.xml"
        if not solution_xml_path.exists():
            solution_xml_path = extract_dir / "Other" / "solution.xml"
        if solution_xml_path.exists() and "solution.xml" not in file_contents:
            try:
                file_contents["solution.xml"] = solution_xml_path.read_text(encoding='utf-8')
            except Exception as e:
                logger.warning(f"Could not read solution.xml: {e}")
        
        # Read the documentation template
        template_path = config.TEMPLATES_DIR / "DocumentationTemplate.md"
        template_content = template_path.read_text(encoding='utf-8')
        
        # IMPROVEMENT 2: Prioritize files by importance
        prioritized_files = _prioritize_files_for_analysis(file_contents)
        
        # IMPROVEMENT 3: Multi-pass analysis - separate critical from non-critical files
        critical_files, non_critical_files = _separate_critical_files(prioritized_files)
        logger.info(f"Separated files: {len(critical_files)} critical, {len(non_critical_files)} non-critical")
        
        # IMPROVEMENT 1 & 4: Enhanced prompt with better Power Platform context
        # IMPROVEMENT 5: Multi-pass analysis - PASS 1: Structure and Overview
        
        # Build selection context for prompt
        selection_context = ""
        if selected_components:
            component_count = len(selected_components)
            component_word = "component" if component_count == 1 else "components"
            
            # Categorize selections for better clarity
            canvas_apps = [c for c in selected_components if c.endswith('.msapp')]
            workflows = [c for c in selected_components if c.startswith('Workflows/') and c.endswith('.json')]
            classic_wfs = [c for c in selected_components if c.startswith('Workflows/') and c.endswith('.xaml')]
            dv_formulas = [c for c in selected_components if c.startswith('Formulas/')]
            
            component_summary = []
            if canvas_apps:
                app_word = "Canvas App" if len(canvas_apps) == 1 else "Canvas Apps"
                component_summary.append(f"{len(canvas_apps)} {app_word}")
            if workflows:
                flow_word = "Power Automate Flow" if len(workflows) == 1 else "Power Automate Flows"
                component_summary.append(f"{len(workflows)} {flow_word}")
            if classic_wfs:
                cw_word = "Classic Workflow/Business Rule" if len(classic_wfs) == 1 else "Classic Workflows/Business Rules"
                component_summary.append(f"{len(classic_wfs)} {cw_word}")
            if dv_formulas:
                df_word = "Dataverse Formula Definition" if len(dv_formulas) == 1 else "Dataverse Formula Definitions"
                component_summary.append(f"{len(dv_formulas)} {df_word}")
            
            summary_text = " and ".join(component_summary) if component_summary else f"{component_count} {component_word}"
            
            selection_context = f"""
⚠️ IMPORTANT - SCOPE LIMITATION:
The user has selected {summary_text} for documentation:
{chr(10).join(f"  • {comp}" for comp in selected_components)}

You are analyzing {len(files_to_analyze)} file(s)/folder(s) that correspond to the selection above.

🚫 DO NOT analyze or document components outside this selection.
🚫 DO NOT explore other directories or files beyond what's provided below.
🚫 DO NOT reference Dataverse tables, other apps, or flows unless they are in the provided files.
✅ ONLY document the selected {component_count} {component_word} using the file contents provided below.
✅ If a component references external data sources or connections, document those references but focus on the selected components.
"""
        else:
            selection_context = """
ℹ️ SCOPE: Complete solution analysis
All components in the solution are included for documentation.
"""
        
        logger.info(f"Completed file reading. Now using dedicated doc generator...")
        
        # ==============================================
        # USE DEDICATED DOCUMENTATION GENERATOR (INCREMENTAL APPROACH)
        # This creates an isolated Copilot session that directly edits template
        # ==============================================
        try:
            logger.info(f"Starting incremental documentation generation for {len(critical_files)} critical files...")
            
            # Get the dedicated documentation generator
            doc_gen = await get_doc_generator()
            
            # Load screenshots if any
            screenshot_data = []
            screenshots_meta = _load_screenshot_metadata(session_id)
            if screenshots_meta:
                screenshots_dir = _get_screenshots_dir(session_id)
                for ss in screenshots_meta:
                    image_path = str(screenshots_dir / ss.filename)
                    b64_md = doc_gen._image_to_base64_markdown(
                        image_path, ss.context, ss.mime_type
                    )
                    screenshot_data.append({
                        'path': image_path,
                        'context': ss.context,
                        'component_path': ss.component_path,
                        'mime_type': ss.mime_type,
                        'base64_markdown': b64_md
                    })
                logger.info(f"Loaded {len(screenshot_data)} screenshot(s) for documentation generation")
            
            # Generate documentation using incremental template editing
            copilot_documentation = await doc_gen.generate_documentation(
                session_id=session_id,
                working_directory=extract_dir,
                critical_files=critical_files,
                non_critical_files=non_critical_files,
                template_path=template_path,  # Pass path instead of content
                selection_context=selection_context,
                business_context=business_context or "",
                screenshots=screenshot_data if screenshot_data else None
            )
            
            logger.info(f"✓ Documentation generation complete: {len(copilot_documentation)} characters")
        
        except asyncio.TimeoutError:
            logger.error("Documentation generation timed out")
            copilot_documentation = f"# Low-Code Project Documentation\n\n*Documentation generation timed out after analyzing {len(critical_files)} critical files. Please try again with fewer components or increase timeout.*"
        except Exception as e:
            error_msg = str(e)
            logger.exception("Error in documentation generation")
            copilot_documentation = f"# Low-Code Project Documentation\n\n*Error generating documentation: {error_msg}*\n\n*Attempted to analyze {len(critical_files)} critical files and {len(non_critical_files)} supporting files.*"
        
        # Save the Copilot-generated documentation
        output_dir = get_output_dir(session_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        solution_info_data = {}
        try:
            analyzer = SolutionAnalyzer(str(extract_dir))
            analysis_data = analyzer.generate_report()
            solution_info_data = analysis_data.get('solution_info', {})
        except Exception as e:
            logger.warning(f"Could not run static analyzer: {e}")
        
        project_name = solution_info_data.get('unique_name', 'PowerPlatformSolution')
        
        # Build filename based on selection
        if selected_components:
            # Create a descriptive suffix based on what was selected
            if len(selected_components) == 1:
                # Single component - use its name
                comp_name = Path(selected_components[0]).stem.replace('-', '_').replace(' ', '_')
                output_file = output_dir / f"{project_name}_{comp_name}_Documentation.md"
            else:
                # Multiple components - use count
                output_file = output_dir / f"{project_name}_{len(selected_components)}Components_Documentation.md"
        else:
            # Full solution
            output_file = output_dir / f"{project_name}_Documentation.md"
        
        # Check if Copilot returned a summary pointing to a file it created elsewhere
        if "**File Location:**" in copilot_documentation and copilot_documentation.count('\n') < 50:
            # This looks like a summary - try to find the actual file
            import re
            file_location_match = re.search(r'\*\*File Location:\*\* `([^`]+)`', copilot_documentation)
            if file_location_match:
                actual_file_path = Path(file_location_match.group(1))
                if actual_file_path.exists():
                    logger.info(f"Copilot created file at {actual_file_path}, copying to session folder")
                    copilot_documentation = actual_file_path.read_text(encoding='utf-8')
                    logger.info(f"Read {len(copilot_documentation)} characters from actual documentation")
        
        # Post-process screenshots: copy images to output dir and fix paths
        screenshots_meta = _load_screenshot_metadata(session_id)
        if screenshots_meta:
            screenshots_dir = _get_screenshots_dir(session_id)
            images_output_dir = output_dir / "images"
            images_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy all screenshot files to output/images/
            copied_count = 0
            for ss in screenshots_meta:
                src = screenshots_dir / ss.filename
                dst = images_output_dir / ss.filename
                if src.exists():
                    shutil.copy2(src, dst)
                    copied_count += 1
                else:
                    logger.warning(f"Screenshot file not found for copy: {src}")
            logger.info(f"Copied {copied_count}/{len(screenshots_meta)} screenshots to {images_output_dir}")
            
            # Fix image paths and ensure all screenshots are included
            copilot_documentation = _post_process_screenshots(
                copilot_documentation, screenshots_meta, screenshots_dir
            )
            logger.info("Post-processed screenshot references in documentation")
        
        output_file.write_text(copilot_documentation, encoding='utf-8')

        # Return just the filename, not the full path
        markdown_files = [output_file.name]
        
        logger.info(f"Documentation generation complete for session {session_id}")
        logger.info(f"Generated file: {output_file.name}")
        
        return DocumentationFiles(
            session_id=session_id,
            markdown_files=markdown_files,
            pdf_file=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error generating documentation for session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{session_id}/{filename}")
async def download_file(session_id: str, filename: str):
    """
    Download a generated documentation file (markdown)
    """
    try:
        output_dir = get_output_dir(session_id)
        file_path = output_dir / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='text/markdown'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error downloading file {filename} for session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download-zip/{session_id}/{filename}")
async def download_zip(session_id: str, filename: str):
    """
    Download documentation as a zip containing the markdown file and images/ folder.
    """
    import zipfile as zf
    try:
        output_dir = get_output_dir(session_id)
        md_path = output_dir / filename

        if not md_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        zip_filename = filename.replace('.md', '') + '_Documentation.zip'
        zip_path = output_dir / zip_filename

        with zf.ZipFile(zip_path, 'w', zf.ZIP_DEFLATED) as zipf:
            # Add the markdown file
            zipf.write(md_path, filename)

            # Add all images from the images/ directory
            images_dir = output_dir / "images"
            if images_dir.exists():
                for img_file in images_dir.iterdir():
                    if img_file.is_file():
                        zipf.write(img_file, f"images/{img_file.name}")

        return FileResponse(
            path=zip_path,
            filename=zip_filename,
            media_type='application/zip'
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating zip for session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download-docx/{session_id}/{filename}")
async def download_docx(session_id: str, filename: str):
    """
    Download a generated documentation file as a Word document (on-demand rendering)
    """
    try:
        output_dir = get_output_dir(session_id)
        
        # Find the markdown file (with or without .md extension in filename)
        if filename.endswith('.md'):
            md_filename = filename
            docx_filename = filename[:-3] + '.docx'
        else:
            md_filename = filename + '.md' if not filename.endswith('.md') else filename
            docx_filename = filename.replace('.md', '.docx') if '.md' in filename else filename + '.docx'
        
        md_file_path = output_dir / md_filename
        
        if not md_file_path.exists():
            raise HTTPException(status_code=404, detail="Markdown file not found")
        
        # Read the markdown content
        with open(md_file_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # Generate Word document on-demand
        docx_file_path = output_dir / docx_filename
        result = render_markdown_to_docx(
            markdown_content=markdown_content,
            output_path=str(docx_file_path),
            config=config.DOCX_CONFIG
        )
        
        if result['status'] != 'success':
            logger.error(f"Word document generation failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(
                status_code=500,
                detail=f"Word document generation failed: {result.get('error', 'Unknown error')}"
            )
        
        # Return the generated Word document
        return FileResponse(
            path=docx_file_path,
            filename=docx_filename,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error generating/downloading Word document for session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/convert-markdown-to-docx")
async def convert_markdown_to_docx(file: UploadFile = File(...)):
    """
    Convert an uploaded markdown file to a Word document (standalone feature)
    """
    try:
        # Validate file
        if not file.filename.endswith('.md'):
            raise HTTPException(status_code=400, detail="Only markdown (.md) files are supported")
        
        # Check file size (max 10MB for standalone markdown files)
        file_content = await file.read()
        if len(file_content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 10MB)")
        
        # Decode markdown content
        try:
            markdown_content = file_content.decode('utf-8')
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Invalid UTF-8 encoding in file")
        
        # Generate a temporary session ID for this conversion
        conversion_id = generate_session_id()
        conversion_dir = config.TEMP_DIR / "conversions" / conversion_id
        conversion_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate .docx filename from markdown filename
        docx_filename = file.filename[:-3] + '.docx' if file.filename.endswith('.md') else file.filename + '.docx'
        docx_path = conversion_dir / docx_filename
        
        # Convert to Word document
        result = render_markdown_to_docx(
            markdown_content=markdown_content,
            output_path=str(docx_path),
            config=config.DOCX_CONFIG
        )
        
        if result['status'] != 'success':
            logger.error(f"Word document conversion failed: {result.get('error', 'Unknown error')}")
            # Cleanup
            shutil.rmtree(conversion_dir, ignore_errors=True)
            raise HTTPException(
                status_code=500,
                detail=f"Word document conversion failed: {result.get('error', 'Unknown error')}"
            )
        
        # Return the Word document
        response = FileResponse(
            path=docx_path,
            filename=docx_filename,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        
        # Schedule cleanup after response is sent (do it in background)
        async def cleanup():
            await asyncio.sleep(5)  # Wait 5 seconds to ensure download completes
            shutil.rmtree(conversion_dir, ignore_errors=True)
        
        asyncio.create_task(cleanup())
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error converting markdown to Word document")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/doc-progress/{session_id}")
async def get_documentation_progress(session_id: str):
    """
    Get the current progress of documentation generation for a session
    """
    try:
        doc_gen = await get_doc_generator()
        progress = doc_gen.get_progress(session_id)
        
        if progress is None:
            return {
                "session_id": session_id,
                "status": "not_started",
                "message": "Documentation generation has not started"
            }
        
        return {
            "session_id": session_id,
            "status": "in_progress" if progress["stage"] != "complete" and progress["stage"] != "error" else progress["stage"],
            **progress
        }
    except Exception as e:
        logger.exception(f"Error getting doc progress for {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/files/{session_id}")
async def list_session_files(session_id: str):
    """
    List all files in a session's directory (extracted solution and output docs)
    """
    try:
        session_dir = get_session_dir(session_id)
        output_dir = get_output_dir(session_id)
        
        if not session_dir.exists():
            raise HTTPException(status_code=404, detail="Session not found")
        
        files = []
        
        # Add output documentation files
        if output_dir.exists():
            for file_path in output_dir.rglob("*"):
                if file_path.is_file() and file_path.suffix in ['.md', '.json', '.txt']:
                    relative_path = file_path.relative_to(output_dir)
                    files.append({
                        "name": file_path.name,
                        "path": str(relative_path),
                        "type": "file",
                        "size": file_path.stat().st_size,
                        "location": "output"
                    })
        
        # Sort files by name
        files.sort(key=lambda x: x["name"])
        
        return {"files": files, "session_id": session_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error listing files for session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/file/{session_id}")
async def get_file_content(session_id: str, path: str):
    """
    Get the content of a specific file in a session
    """
    try:
        output_dir = get_output_dir(session_id)
        file_path = output_dir / path
        
        # Security check: ensure file is within output directory
        if not file_path.resolve().is_relative_to(output_dir.resolve()):
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return {
            "path": path,
            "content": content,
            "size": file_path.stat().st_size
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error reading file {path} for session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/file/{session_id}")
async def save_file_content(session_id: str, file_data: dict):
    """
    Save edited content back to a file
    """
    try:
        path = file_data.get("path")
        content = file_data.get("content")
        
        if not path or content is None:
            raise HTTPException(status_code=400, detail="Path and content are required")
        
        output_dir = get_output_dir(session_id)
        file_path = output_dir / path
        
        # Security check: ensure file is within output directory
        if not file_path.resolve().is_relative_to(output_dir.resolve()):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"Saved file {path} for session {session_id}")
        
        return {
            "success": True,
            "path": path,
            "size": file_path.stat().st_size
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error saving file for session {session_id}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
