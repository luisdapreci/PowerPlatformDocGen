"""Session management for Copilot SDK"""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, List
from copilot import CopilotClient, CopilotSession
import logging
import config

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages Copilot SDK sessions for different users/solutions"""
    
    def __init__(self):
        self.sessions: Dict[str, 'ManagedSession'] = {}
        self.client: Optional[CopilotClient] = None
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def initialize(self, restore_sessions: bool = True):
        """Initialize the Copilot client"""
        try:
            self.client = CopilotClient()
            logger.info("Copilot client initialized")
            
            # Restore existing sessions if requested
            if restore_sessions:
                await self._restore_sessions()
            
            # Start cleanup task
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        except Exception as e:
            logger.error(f"Failed to initialize Copilot client: {e}")
            raise
    
    async def create_session(
        self,
        session_id: str,
        working_directory: Path,
        selected_components: Optional[List[str]] = None
    ) -> CopilotSession:
        """
        Create a new Copilot session for solution analysis
        
        Args:
            session_id: Unique session identifier
            working_directory: Directory where solution is extracted
            tools: Optional list of custom tools
            selected_components: Optional list of selected component paths
        
        Returns:
            CopilotSession instance
        """
        if not self.client:
            raise RuntimeError("SessionManager not initialized")
        
        # System prompt for Power Platform analysis
        system_prompt = """You are a Power Platform solution analyst expert with deep knowledge of Microsoft's low-code platform. Your role is to:
1. Analyze Power Platform solutions including Canvas Apps, Model-driven Apps, Power Automate flows, and Dataverse customizations
2. Extract and document key information: app structure, formulas, data sources, connections, and business logic
3. Generate comprehensive, well-organized documentation in Markdown format
4. Answer specific questions about solution components
5. Identify dependencies and relationships between components

🔧 POWER PLATFORM ARCHITECTURE KNOWLEDGE:

CANVAS APPS (Custom UI Applications):
- Structure: Unpacked in folders ending with _src/
- Key Files:
  * src/*.fx.yaml = Power Fx formulas (CRITICAL - contains all business logic)
  * src/CanvasManifest.json = App metadata, screens list, components
  * DataSources/*.json = Connection definitions (SharePoint, SQL, APIs, etc.)
  * Connections/*.json = Connection instances and authentication
  * Assets/ = Images, media files, custom fonts
  * src/EditorState/*.json = UI layout and control properties
- Power Fx Language: Functional language similar to Excel formulas
  * Uses functions like: Filter(), Patch(), Collect(), Navigate(), Set(), UpdateContext()
  * Context variables: UpdateContext({varName: value})
  * Global variables: Set(varName, value)
  * Collections: ClearCollect(), Collect()
  * Navigation: Navigate(Screen, Transition)
  
POWER AUTOMATE FLOWS (Workflows/*.json):
- Trigger types: Manual, Automated (on item creation/update), Scheduled, Power Apps
- Actions: Create/Update items, Send emails, Approvals, HTTP requests, Conditions, Loops
- Structure: triggers → actions → conditions → parallel branches
- Connection references: Links to data sources
- Error handling: Configure run after settings, try-catch patterns

MODEL-DRIVEN APPS:
- Based on Dataverse tables (entities)
- Forms, views, business rules defined in XML
- Plugin assemblies for server-side logic

DATAVERSE (Cloud Database):
- Tables (formerly entities) with columns (formerly fields)
- Relationships: 1:N, N:1, N:N
- Business rules, workflows, plugins
- Security roles and field-level security

SOLUTION STRUCTURE:
- solution.xml = Root manifest with version, publisher, components list
- customizations.xml = Dataverse customizations (tables, forms, views)
- CanvasApps/ = Canvas app packages (.msapp files)
- Workflows/ = Power Automate flow definitions (JSON)
- WebResources/ = JavaScript, HTML, CSS, images

📋 ANALYSIS BEST PRACTICES:
- For Canvas Apps: Focus on Power Fx formulas in .fx.yaml files - they contain the core logic
- For Flows: Document trigger, conditions, and action sequence with business purpose
- For Dependencies: Note connections between apps, flows, and data sources
- For Business Logic: Explain WHAT the formula/flow does, not just WHAT it says
- Extract meaningful component names and purposes from manifests

🎯 DOCUMENTATION GOALS:
- Make technical solutions understandable for both developers and business users
- Highlight important formulas, workflows, and integration points
- Document data flow and component relationships
- Identify potential issues or improvement areas

Use read_file, list_dir, grep_search, and file_search tools effectively to explore the solution structure. Parse JSON/YAML/XML files accurately.

🔧 FILE OPERATIONS:
You have access to standard file tools:
- read_file: Read any file in the working directory (JSON, YAML, XML, etc.)
- list_dir: List contents of directories
- grep_search: Search for patterns in files
- file_search: Find files by name or pattern (e.g., '*.fx.yaml', '**/DataSources/*.json')

Use these tools to explore and analyze Power Platform components directly."""

        # Build detailed system prompt with file structure
        detailed_prompt = system_prompt + "\n\n" + self._build_file_structure_context(working_directory, selected_components)
        
        # Create session configuration
        session_config = {
            "model": config.COPILOT_MODEL,
            "working_directory": str(working_directory),
            "streaming": config.COPILOT_STREAMING,
            "system_message": {
                "mode": "append",
                "content": detailed_prompt
            },
            # Auto-approve file read requests; deny shell/write for security
            "on_permission_request": lambda req, ctx: (
                {"kind": "denied-by-rules"}
                if req.get("kind") in ("shell", "write")
                else {"kind": "approved"}
            ),
        }
        
        # Add infinite sessions config if enabled
        if config.COPILOT_ENABLE_INFINITE_SESSIONS:
            session_config["infinite_sessions"] = {
                "enabled": True,
                "background_compaction_threshold": config.COPILOT_COMPACTION_THRESHOLD,
                "buffer_exhaustion_threshold": config.COPILOT_BUFFER_THRESHOLD
            }
        
        try:
            copilot_session = await self.client.create_session(session_config)
            
            # Store managed session
            managed_session = ManagedSession(
                session_id=session_id,
                copilot_session=copilot_session,
                working_directory=working_directory
            )
            self.sessions[session_id] = managed_session
            
            logger.info(f"Created Copilot session for {session_id} with SDK built-in tools")
            return copilot_session
            
        except Exception as e:
            logger.error(f"Failed to create session for {session_id}: {e}")
            raise
    
    def _build_file_structure_context(self, working_directory: Path, selected_components: Optional[List[str]] = None) -> str:
        """
        Build a context string describing the file structure of unpacked solution.
        This helps the agent know exactly where to find files.
        
        Args:
            working_directory: Path to the extracted solution
            selected_components: Optional list of selected component paths
        """
        context_parts = []
        context_parts.append("📂 YOUR WORKING DIRECTORY FILE STRUCTURE:")
        context_parts.append(f"Working directory: {working_directory}")
        context_parts.append("")
        
        # Add selected components context if available
        if selected_components and len(selected_components) > 0:
            context_parts.append("=" * 80)
            context_parts.append("🎯 USER SELECTED COMPONENTS - CRITICAL CONTEXT")
            context_parts.append("=" * 80)
            context_parts.append(f"The user has explicitly selected {len(selected_components)} component(s) for analysis.")
            context_parts.append("IMPORTANT: Focus ONLY on these selected components when answering user questions.")
            context_parts.append("")
            
            # Group components by type.
            # Normalise to forward slashes so comparisons work on both Windows and Linux.
            def _norm(p: str) -> str:
                return p.replace('\\', '/')

            canvas_apps = [_norm(c) for c in selected_components if c.endswith('.msapp')]
            flows = [_norm(c) for c in selected_components
                     if _norm(c).startswith('Workflows/') and c.endswith('.json')]
            
            if canvas_apps:
                context_parts.append("📱 SELECTED CANVAS APPS:")
                for idx, app in enumerate(canvas_apps, 1):
                    app_name = Path(app).stem  # Extract name from path
                    context_parts.append(f"   {idx}. {app_name}")
                context_parts.append("")
            
            if flows:
                context_parts.append("⚡ SELECTED POWER AUTOMATE FLOWS:")
                context_parts.append(f"   The user selected {len(flows)} flow(s):")
                for idx, flow in enumerate(flows, 1):
                    flow_name = Path(flow).stem  # Extract name from path
                    context_parts.append(f"   {idx}. {flow_name}")
                    # Also show the full path for clarity
                    context_parts.append(f"      Path: {flow}")
                context_parts.append("")
            
            context_parts.append("💡 CRITICAL: When the user asks about 'the app' or 'the flow', they mean the components listed above.")
            if len(canvas_apps) == 1:
                context_parts.append(f"   - 'the app' = {Path(canvas_apps[0]).stem}")
            elif len(canvas_apps) > 1:
                context_parts.append(f"   - 'the apps' = the {len(canvas_apps)} apps listed above")
            if len(flows) == 1:
                context_parts.append(f"   - 'the flow' = {Path(flows[0]).stem}")
            elif len(flows) > 1:
                context_parts.append(f"   - 'the flows' = the {len(flows)} flows listed above")
            if not canvas_apps and not flows:
                # Fallback: list all paths verbatim so the AI still knows what was selected
                context_parts.append("   Selected paths:")
                for c in selected_components:
                    context_parts.append(f"   - {c}")
            context_parts.append("=" * 80)
            context_parts.append("")
        
        try:
            # Find all unpacked canvas apps (_src folders)
            canvas_apps = []
            if working_directory.exists():
                for item in working_directory.iterdir():
                    if item.is_dir() and item.name.endswith("_src"):
                        canvas_apps.append(item)
                        
            if canvas_apps:
                context_parts.append("🎨 UNPACKED CANVAS APPS (USE THESE PATHS):")
                for app_dir in canvas_apps:
                    app_name = app_dir.name.replace("_src", "")
                    context_parts.append(f"")
                    context_parts.append(f"📱 {app_name}:")
                    context_parts.append(f"   Full path: {app_dir}")
                    
                    # Check for key files
                    src_dir = app_dir / "src"
                    if src_dir.exists():
                        fx_files = list(src_dir.glob("*.fx.yaml"))
                        if fx_files:
                            context_parts.append(f"   ✅ Power Fx Formulas: {len(fx_files)} .fx.yaml files in src/")
                            for fx_file in fx_files[:3]:
                                context_parts.append(f"      - {fx_file.name}")
                            if len(fx_files) > 3:
                                context_parts.append(f"      - ... and {len(fx_files) - 3} more")
                    
                    manifest = app_dir / "CanvasManifest.json"
                    if manifest.exists():
                        context_parts.append(f"   ✅ Manifest: {manifest}")
                    
                    datasources_dir = app_dir / "DataSources"
                    if datasources_dir.exists() and datasources_dir.is_dir():
                        ds_files = list(datasources_dir.glob("*.json"))
                        if ds_files:
                            context_parts.append(f"   ✅ Data Sources: {len(ds_files)} files")
                    
                    connections_dir = app_dir / "Connections"
                    if connections_dir.exists() and connections_dir.is_dir():
                        conn_files = list(connections_dir.glob("*.json"))
                        if conn_files:
                            context_parts.append(f"   ✅ Connections: {len(conn_files)} files")
            
            # Check for Power Automate flows
            workflows_dir = working_directory / "Workflows"
            if workflows_dir.exists() and workflows_dir.is_dir():
                flow_files = list(workflows_dir.glob("*.json"))
                if flow_files:
                    context_parts.append("")
                    context_parts.append("⚡ POWER AUTOMATE FLOWS:")
                    for flow_file in flow_files[:5]:
                        context_parts.append(f"   - {flow_file}")
                    if len(flow_files) > 5:
                        context_parts.append(f"   - ... and {len(flow_files) - 5} more")
            
            # Check for solution.xml
            solution_xml = working_directory / "solution.xml"
            if solution_xml.exists():
                context_parts.append("")
                context_parts.append(f"📋 Solution Manifest: {solution_xml}")
            
            context_parts.append("")
            context_parts.append("💡 IMPORTANT INSTRUCTIONS:")
            context_parts.append("   - Use read_file to read any JSON, YAML, or XML files")
            context_parts.append("   - Use file_search to find files (e.g., '**/*.fx.yaml' for formulas)")
            context_parts.append("   - Use list_dir to explore directory contents")
            context_parts.append("   - The .fx.yaml files in src/ contain ALL the Power Fx formulas")
            
        except Exception as e:
            logger.error(f"Error building file structure context: {e}")
            context_parts.append(f"⚠️  Error scanning directory: {e}")
        
        return "\n".join(context_parts)
    
    def get_session(self, session_id: str) -> Optional[CopilotSession]:
        """Get an existing session"""
        managed = self.sessions.get(session_id)
        if managed:
            managed.update_last_activity()
            return managed.copilot_session
        return None
    
    async def destroy_session(self, session_id: str):
        """Destroy a session and clean up resources"""
        managed = self.sessions.get(session_id)
        if managed:
            try:
                await managed.copilot_session.destroy()
                logger.info(f"Destroyed session {session_id}")
            except Exception as e:
                logger.error(f"Error destroying session {session_id}: {e}")
            finally:
                del self.sessions[session_id]
    
    async def _cleanup_loop(self):
        """Periodically clean up expired sessions"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                now = datetime.now()
                expired = [
                    sid for sid, managed in self.sessions.items()
                    if (now - managed.last_activity).total_seconds() > config.SESSION_TIMEOUT
                ]
                
                for session_id in expired:
                    logger.info(f"Cleaning up expired session {session_id}")
                    await self.destroy_session(session_id)
                    
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def _restore_sessions(self):
        """Restore sessions from disk on startup"""
        try:
            temp_dir = config.TEMP_DIR
            
            if not temp_dir.exists():
                return
            
            # Find all session directories
            for session_dir in temp_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                
                session_id = session_dir.name
                extract_dir = session_dir / "extracted"
                
                # Only restore if extraction was completed
                if extract_dir.exists():
                    try:
                        # Create session for existing extracted solution
                        await self.create_session(
                            session_id=session_id,
                            working_directory=extract_dir,
                            tools=None
                        )
                        logger.info(f"Restored session {session_id}")
                    except Exception as e:
                        logger.warning(f"Could not restore session {session_id}: {e}")
        except Exception as e:
            logger.error(f"Error restoring sessions: {e}")
    
    async def shutdown(self):
        """Shutdown the session manager"""
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Destroy all sessions
        for session_id in list(self.sessions.keys()):
            await self.destroy_session(session_id)
        
        # Stop client
        if self.client:
            await self.client.stop()
            logger.info("Copilot client stopped")


class ManagedSession:
    """Wrapper for Copilot session with metadata"""
    
    def __init__(self, session_id: str, copilot_session: CopilotSession, working_directory: Path):
        self.session_id = session_id
        self.copilot_session = copilot_session
        self.working_directory = working_directory
        self.last_activity = datetime.now()
        self.created_at = datetime.now()
    
    def update_last_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now()
