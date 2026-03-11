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
from utils.docx_renderer import render_markdown_to_docx, prepend_logo_to_markdown
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
        
        # HIGHEST priority: PowerApps Power Fx formulas (business logic - typically has most info)
        if '.fx.yaml' in path_lower:
            score = 1200
            # Boost for specific important formulas
            if 'app.fx.yaml' in path_lower or 'onstart' in path_lower:
                score += 500
        
        # High priority: Workflows (Power Automate flows - business logic)
        elif 'workflows' in path_lower and path_lower.endswith('.json'):
            score = 1000
            # Boost for main workflow files (non-connection references)
            if not 'connectionreferences' in path_lower:
                score += 500
        
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
    
    for path, content in prioritized_files:
        path_lower = path.lower()
        is_critical = (
            '.fx.yaml' in path_lower or  # Power Fx formulas
            ('workflows' in path_lower and path_lower.endswith('.json') and 'connectionreferences' not in path_lower)  # Workflows
        )
        
        if is_critical:
            critical_files.append((path, content))
        else:
            non_critical_files.append((path, content))
    
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
                
                # Process Workflow JSON files
                elif normalized_sel.startswith("Workflows/") and normalized_sel.endswith('.json'):
                    # Extract just the filename from the selection
                    selected_filename = Path(normalized_sel).name
                    
                    # Find exact match in Workflows directory
                    workflows_dir = extract_dir / "Workflows"
                    if workflows_dir.exists():
                        workflow_file = workflows_dir / selected_filename
                        if workflow_file.exists() and not selected_filename.endswith("-ConnectionReferences.json"):
                            files_to_analyze.append(str(workflow_file.relative_to(extract_dir)))
                            logger.info(f"Matched Workflow: {sel} -> {selected_filename}")
        
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
            
            component_summary = []
            if canvas_apps:
                app_word = "Canvas App" if len(canvas_apps) == 1 else "Canvas Apps"
                component_summary.append(f"{len(canvas_apps)} {app_word}")
            if workflows:
                flow_word = "Power Automate Flow" if len(workflows) == 1 else "Power Automate Flows"
                component_summary.append(f"{len(workflows)} {flow_word}")
            
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
        
        copilot_documentation = prepend_logo_to_markdown(
            copilot_documentation,
            config.DOCX_CONFIG.get('logo_path', ''),
            config.DOCX_CONFIG.get('logo_width_inches', 1.5),
        )
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
        
        # Inject logo unless the file already contains one (e.g. previously generated .md)
        if 'data:image' not in markdown_content[:500]:
            markdown_content = prepend_logo_to_markdown(
                markdown_content,
                config.DOCX_CONFIG.get('logo_path', ''),
                config.DOCX_CONFIG.get('logo_width_inches', 1.5),
            )

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
