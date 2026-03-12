"""
Dedicated Documentation Generator
Handles documentation generation separately from chat sessions to avoid interference
"""

import asyncio
import base64
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from copilot import CopilotClient, PermissionRequestResult
import config

logger = logging.getLogger(__name__)


class DocumentationGenerator:
    """
    Isolated documentation generator that creates temporary Copilot sessions
    specifically for doc generation without WebSocket event handlers
    """
    
    def __init__(self):
        self.client: Optional[CopilotClient] = None
        self._generation_progress: Dict[str, Dict[str, Any]] = {}
    
    async def initialize(self):
        """Initialize the Copilot client for doc generation"""
        try:
            self.client = CopilotClient()
            logger.info("Documentation generator Copilot client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize doc generator Copilot client: {e}")
            raise
    
    def get_progress(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the current progress of a documentation generation"""
        return self._generation_progress.get(session_id)
    
    async def generate_documentation(
        self,
        session_id: str,
        working_directory: Path,
        critical_files: List[tuple],
        non_critical_files: List[tuple],
        template_path: Path,
        selection_context: str = "",
        business_context: str = "",
        screenshots: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        [NEW METHOD - Incremental template editing approach]
        Generate documentation by directly editing a template copy as files are analyzed.
        Much faster than consolidation approach.
        
        Args:
            session_id: Session identifier for progress tracking
            working_directory: Path to extracted solution
            critical_files: List of (path, content) tuples for critical files
            non_critical_files: List of (path, content) tuples for supporting files
            template_path: Path to template file (will be copied to working directory)
            selection_context: Context about selected components
            business_context: User-provided business context
            screenshots: Optional list of screenshot dicts with keys:
                         'path' (file path), 'context' (user description),
                         'component_path' (associated component or None),
                         'mime_type', 'base64_markdown' (pre-built embed snippet)
            
        Returns:
            Path to generated documentation file (in working directory)
        """
        if not self.client:
            raise RuntimeError("DocumentationGenerator not initialized")
        
        total_steps = len(critical_files) + 2  # Files + final formatting pass
        
        try:
            self._update_progress(
                session_id,
                "initializing",
                0,
                total_steps,
                "Creating template copy and session"
            )
            
            # Copy template to working directory
            doc_file = working_directory / f"{session_id}_Documentation.md"
            import shutil
            shutil.copy(template_path, doc_file)
            logger.info(f"Created documentation template copy: {doc_file}")
            
            # Create isolated Copilot session with ALL built-in tools enabled by default
            # Per SDK docs: "By default, the SDK  will operate the Copilot CLI in the equivalent 
            # of --allow-all being passed to the CLI, enabling all first-party tools"
            # This includes: read_file, write_file, replace_string_in_file, list_dir, grep_search, etc.
            session_config = {
                "model": config.COPILOT_MODEL,
                "working_directory": str(working_directory),
                "streaming": False,
                # NOTE: Do NOT specify available_tools - that RESTRICTS tools, not enables them!
                # By omitting it, ALL built-in file operation tools are available.
                # Auto-approve file read/write requests; deny shell for security
                "on_permission_request": lambda req, ctx: (
                    PermissionRequestResult(kind="denied-by-rules")
                    if req.kind.value == "shell"
                    else PermissionRequestResult(kind="approved")
                ),
                "system_message": {
                    "mode": "append",
                    "content": self._build_incremental_system_prompt(
                        str(doc_file),
                        screenshots=screenshots
                    )
                }
            }
            
            temp_session = await self.client.create_session(session_config)
            logger.info(f"Created incremental editing session for {session_id}")
            
            # Build context sections
            business_section = ""
            if business_context:
                business_section = f"\n\n**USER BUSINESS CONTEXT:**\n{business_context}\n"
            
            # Group screenshots by component path for per-file attachment
            screenshots = screenshots or []
            screenshots_by_component = {}
            global_screenshots = []
            for ss in screenshots:
                cp = ss.get('component_path')
                if cp:
                    screenshots_by_component.setdefault(cp, []).append(ss)
                else:
                    global_screenshots.append(ss)
            
            # Create sidecar file with screenshot embed snippets to avoid inlining
            # massive base64 strings in prompts (which can exceed token limits)
            screenshots_snippets_file = None
            if screenshots:
                screenshots_snippets_file = working_directory / f"{session_id}_screenshot_snippets.md"
                snippet_lines = ["# Screenshot Embed Snippets\n\n"]
                snippet_lines.append("Copy the FULL line starting with `![` for the screenshot you need.\n\n")
                for i, ss in enumerate(screenshots, 1):
                    context = ss.get('context', 'No context provided')
                    comp = ss.get('component_path', 'Global')
                    snippet_lines.append(f"## Screenshot {i}: {context}\n")
                    snippet_lines.append(f"Component: {comp or 'Global'}\n\n")
                    snippet_lines.append(f"{ss['base64_markdown']}\n\n")
                    snippet_lines.append("---\n\n")
                screenshots_snippets_file.write_text("".join(snippet_lines), encoding='utf-8')
                logger.info(f"Created screenshot snippets sidecar file: {screenshots_snippets_file} ({len(screenshots)} snippets)")
            
            # PASS 1: Analyze each file and directly edit relevant template sections
            for idx, (path, content) in enumerate(critical_files, 1):
                try:
                    self._update_progress(
                        session_id,
                        "analyzing",
                        idx,
                        total_steps,
                        f"Analyzing and updating doc with: {Path(path).name}"
                    )
                    
                    logger.info(f"Pass {idx}/{len(critical_files)}: Analyzing {path} and editing template...")
                    
                    prompt = self._build_incremental_file_prompt(
                        path,
                        content,
                        idx,
                        len(critical_files),
                        str(doc_file),
                        selection_context,
                        business_section
                    )
                    
                    # Find screenshots associated with this file's component
                    file_screenshots = []
                    norm_path = path.replace('\\', '/')
                    for comp_path, ss_list in screenshots_by_component.items():
                        norm_comp = comp_path.replace('\\', '/')
                        # Match if the component path is part of the file path
                        if norm_comp in norm_path or norm_path in norm_comp:
                            file_screenshots.extend(ss_list)
                        # Also match by component stem (e.g., msapp stem matches _src folder)
                        elif Path(comp_path).stem in norm_path:
                            file_screenshots.extend(ss_list)
                    
                    # Build attachments and screenshot context for prompt
                    attachments = []
                    if file_screenshots:
                        screenshot_section = "\n\n**USER-PROVIDED SCREENSHOTS FOR THIS COMPONENT:**\n\n"
                        for si, ss in enumerate(file_screenshots, 1):
                            attachments.append({"type": "file", "path": ss['path']})
                            # Find global index in the full screenshots list
                            global_idx = next((i for i, s in enumerate(screenshots, 1) if s.get('path') == ss.get('path')), si)
                            screenshot_section += f"**Screenshot {si} (snippet #{global_idx} in sidecar file):** {ss.get('context', 'No context provided')}\n"
                        screenshot_section += f"\n**MANDATORY VISUAL ANALYSIS + EMBEDDING TASK:**\n"
                        screenshot_section += "For EACH screenshot above you MUST do BOTH — analyze AND embed:\n\n"
                        screenshot_section += "**A) VISUAL ANALYSIS (write documentation based on what you SEE):**\n"
                        screenshot_section += "   - Study the attached image carefully — you have full visual access\n"
                        screenshot_section += "   - Identify: screen layout, controls (buttons/galleries/forms/labels), data fields shown, navigation elements\n"
                        screenshot_section += "   - For flow screenshots: list every visible action/step name, conditions, branches, connectors\n"
                        screenshot_section += "   - Write this analysis into the relevant doc section using `replace_string_in_file`:\n"
                        screenshot_section += "     * UI details → `### 3.3 User Interface` (describe layout, list controls with names)\n"
                        screenshot_section += "     * Flow details → `### 3.4 Logic and Automation` (list steps, describe logic)\n"
                        screenshot_section += "     * Data shown → `### 2.2 Data Sources` (what data entities/fields are visible)\n"
                        screenshot_section += "     * Features visible → `### 4.2 Features` (describe user-facing capabilities)\n\n"
                        screenshot_section += "**B) IMAGE EMBEDDING (insert the screenshot into the doc):**\n"
                        screenshot_section += f"   1. Read the embed snippet from `{screenshots_snippets_file}` — find `## Screenshot N` matching the number above\n"
                        screenshot_section += "   2. Copy the FULL `![...]()` line (base64 string is very long — copy it completely)\n"
                        screenshot_section += "   3. Insert it into the documentation section where you wrote the visual analysis above\n"
                        screenshot_section += "   4. Add a rich caption: `*Figure N: <detailed description including key UI elements, data fields, and purpose>*`\n\n"
                        prompt += screenshot_section
                    
                    # Send prompt with optional image attachments
                    send_payload = {"prompt": prompt}
                    if attachments:
                        send_payload["attachments"] = attachments
                        logger.info(f"Attaching {len(attachments)} screenshot(s) for {path}")
                    
                    result = await temp_session.send_and_wait(
                        send_payload,
                        timeout=config.DOC_GEN_FILE_TIMEOUT
                    )
                    
                    if result and hasattr(result, 'data') and hasattr(result.data, 'content'):
                        response = result.data.content
                        logger.info(f"✓ Pass {idx} complete: {len(response)} chars response")
                    else:
                        logger.warning(f"No response for {path}")
                
                except asyncio.TimeoutError:
                    logger.error(f"Timeout analyzing {path}")
                except Exception as e:
                    logger.error(f"Error analyzing {path}: {e}")
            
            # PASS 2: Final formatting and gap-filling pass
            self._update_progress(
                session_id,
                "formatting",
                total_steps - 1,
                total_steps,
                "Final formatting and integration"
            )
            
            logger.info("Final pass: Formatting and filling gaps...")
            
            all_screenshots = screenshots or []
            final_prompt = self._build_incremental_final_prompt(
                str(doc_file),
                selection_context,
                business_section,
                len(critical_files),
                critical_files,
                non_critical_files,
                working_directory,
                global_screenshots=global_screenshots,
                all_screenshots=all_screenshots,
                screenshots_snippets_file=str(screenshots_snippets_file) if screenshots_snippets_file else None
            )
            
            # Build attachments for global screenshots (component-specific ones were already embedded in Pass 1)
            final_attachments = [
                {"type": "file", "path": ss['path']} for ss in global_screenshots
            ]
            
            final_payload = {"prompt": final_prompt}
            if final_attachments:
                final_payload["attachments"] = final_attachments
                logger.info(f"Attaching {len(final_attachments)} global screenshot(s) for final pass")
            
            try:
                result = await temp_session.send_and_wait(
                    final_payload,
                    timeout=config.DOC_GEN_FINAL_PASS_TIMEOUT
                )
                
                if result and hasattr(result, 'data') and hasattr(result.data, 'content'):
                    logger.info(f"✓ Final formatting complete")
            except (TimeoutError, asyncio.TimeoutError):
                logger.warning("Final pass timed out, retrying with simplified prompt...")
                retry_prompt = (
                    f"The previous formatting pass timed out. Please quickly finish editing "
                    f"`{doc_file}`. Focus ONLY on:\n"
                    f"1. Read the file with read_file\n"
                    f"2. Fill any remaining placeholder text in the frontmatter (project name, date, purpose)\n"
                    f"3. Generate a Table of Contents if missing\n"
                    f"4. Replace any remaining template placeholders with '*Not available*'\n"
                    f"Do NOT explore additional files. Make minimal edits and finish quickly."
                )
                try:
                    result = await temp_session.send_and_wait(
                        {"prompt": retry_prompt},
                        timeout=config.DOC_GEN_SECTION_TIMEOUT
                    )
                    if result and hasattr(result, 'data') and hasattr(result.data, 'content'):
                        logger.info("✓ Final formatting complete (retry)")
                except (TimeoutError, asyncio.TimeoutError):
                    logger.warning("Final pass retry also timed out, proceeding with current documentation state")
            
            # Read the final documentation
            documentation = doc_file.read_text(encoding='utf-8')
            logger.info(f"✓ Documentation ready: {len(documentation)} chars")
            
            # Clean up session
            try:
                if hasattr(temp_session, 'close'):
                    await temp_session.close()
                logger.info("Incremental editing session closed")
            except Exception as e:
                logger.warning(f"Error closing session: {e}")
            
            # Mark as complete
            self._update_progress(
                session_id,
                "complete",
                total_steps,
                total_steps,
                "Documentation generation complete"
            )
            
            return documentation
        
        except Exception as e:
            logger.exception(f"Error in incremental documentation generation for {session_id}")
            self._update_progress(
                session_id,
                "error",
                0,
                total_steps,
                f"Error: {str(e)}"
            )
            raise
    
    def _update_progress(
        self, 
        session_id: str, 
        stage: str, 
        current: int, 
        total: int, 
        message: str
    ):
        """Update progress tracking"""
        self._generation_progress[session_id] = {
            "stage": stage,
            "current": current,
            "total": total,
            "message": message,
            "percentage": int((current / total) * 100) if total > 0 else 0,
            "updated_at": datetime.now().isoformat()
        }
        logger.info(f"[{session_id}] Progress: {stage} - {current}/{total} - {message}")
    
    @staticmethod
    def _image_to_base64_markdown(image_path: str, context: str, mime_type: str = None) -> str:
        """Convert an image file to a base64-encoded markdown image tag.
        
        Returns: ![context](data:mime;base64,...) string ready for embedding in markdown.
        """
        path = Path(image_path)
        if not path.exists():
            logger.warning(f"Screenshot not found: {image_path}")
            return f"*[Image not found: {context}]*"
        
        if mime_type is None:
            ext = path.suffix.lower().lstrip('.')
            mime_map = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                        'gif': 'image/gif', 'webp': 'image/webp'}
            mime_type = mime_map.get(ext, f'image/{ext}')
        
        raw = path.read_bytes()
        b64 = base64.b64encode(raw).decode('ascii')
        # Sanitize context for use in alt text (remove markdown special chars)
        safe_context = context.replace('[', '(').replace(']', ')').replace('|', '-')
        return f"![{safe_context}](data:{mime_type};base64,{b64})"
    
    @staticmethod
    def _build_screenshot_system_instructions(screenshots: Optional[List[Dict[str, Any]]] = None) -> str:
        """Build system prompt section about screenshot handling."""
        if not screenshots:
            return ""
        
        return f"""
[IMAGE] **SCREENSHOT HANDLING INSTRUCTIONS:**

The user has provided {len(screenshots)} screenshot(s) with context descriptions.
You will receive these images as file attachments — YOU CAN SEE THEM. Use your vision to analyze each image.

**VISUAL ANALYSIS — MANDATORY FOR EVERY SCREENSHOT:**
When you receive an image attachment, study it carefully and extract:
- **UI Layout**: Screen structure, navigation elements, headers, footers, sidebars
- **Controls & Widgets**: Buttons, galleries, forms, dropdowns, text inputs, labels — note their names if visible
- **Data Displayed**: Tables, lists, cards — what data fields are shown? What values are example/sample data?
- **Color Scheme & Branding**: Primary colors, logos, styling choices
- **Flow Diagrams**: If it shows a Power Automate flow — list every action/step name visible, note conditions/branches
- **Error States or Notifications**: Any alerts, validation messages, loading indicators
- **Navigation Flow**: How screens connect — back buttons, menu items, tabs

**HOW TO USE VISUAL INSIGHTS:**
1. **WRITE** detailed descriptions in the documentation based on what you see — this is the primary value
   - In `### 3.3 User Interface`: Describe the screen layout, list visible controls, explain the UX flow
   - In `### 3.4 Logic and Automation`: Describe flow steps, conditions, and automation paths you can see
   - In `### 4.2 Features`: Describe user-facing features visible in the screenshot
   - In `## 1. Project Overview`: Use visuals to write a more accurate summary of what the app does
2. **EMBED** the screenshot image from the sidecar snippets file (read it with read_file)
3. **PLACE** each image in the MOST RELEVANT section:
   - App/screen screenshots → `### 3.3 User Interface` or `### 4.2 Features`
   - Flow/automation screenshots → `### 3.4 Logic and Automation`
   - Data/output screenshots → `### 2.2 Data Sources` or `### 8.2 Screenshots or Diagrams`
   - General/overview screenshots → `## 1. Project Overview` or `### 8.2 Screenshots or Diagrams`
4. **ADD A RICH CAPTION** below each image: `*Figure N: <detailed description of what the screenshot shows, including key UI elements and data>*`
5. **DO NOT** modify the base64 data — copy the snippet exactly as provided

**IMPORTANT:** The visual analysis should SIGNIFICANTLY ENRICH the documentation.
Do not just embed images — describe what you see in them to create thorough documentation.
"""
    
    @staticmethod
    def _build_global_screenshots_prompt(
        global_screenshots: Optional[List[Dict[str, Any]]] = None,
        snippets_file_path: Optional[str] = None,
        all_screenshots: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Build prompt section for global (non-component) screenshots in the final pass."""
        if not global_screenshots:
            return ""
        
        section = f"\n[IMAGE] **GLOBAL SCREENSHOTS TO EMBED ({len(global_screenshots)}):**\n\n"
        section += "These screenshots are not tied to a specific component. Analyze each one and place it in the most relevant documentation section.\n\n"
        for i, ss in enumerate(global_screenshots, 1):
            context = ss.get('context', 'No context provided')
            # Find global index in the full screenshots list for sidecar file reference
            global_idx = i
            if all_screenshots:
                global_idx = next((idx for idx, s in enumerate(all_screenshots, 1) if s.get('path') == ss.get('path')), i)
            section += f"**Global Screenshot {i} (snippet #{global_idx} in sidecar):** {context}\n"
        if snippets_file_path:
            section += f"\n**TASK — VISUAL ANALYSIS + EMBEDDING for each global screenshot:**\n\n"
            section += "**A) VISUAL ANALYSIS (enrich the documentation with what you SEE):**\n"
            section += "   - Study each attached image carefully — describe UI layouts, controls, data fields, flow steps\n"
            section += "   - Write detailed observations into the most relevant doc sections using `replace_string_in_file`\n"
            section += "   - This analysis is the PRIMARY VALUE — screenshots alone are not enough\n\n"
            section += "**B) IMAGE EMBEDDING:**\n"
            section += f"   1. Read the embed snippet from `{snippets_file_path}` — find the matching `## Screenshot N` section\n"
            section += "   2. Copy the FULL `![...]()` line and use replace_string_in_file to insert it\n"
            section += "   3. Place the image adjacent to the descriptive text you wrote in step A\n"
            section += "   4. Add a rich caption: `*Figure N: <detailed description of what the screenshot shows>*`\n\n"
        else:
            section += "\n**TASK — VISUAL ANALYSIS + EMBEDDING for each global screenshot:**\n\n"
            section += "**A) VISUAL ANALYSIS (enrich the documentation with what you SEE):**\n"
            section += "   - Study each attached image carefully — describe UI layouts, controls, data fields, flow steps\n"
            section += "   - Write detailed observations into the most relevant doc sections\n\n"
            section += "**B) IMAGE EMBEDDING:**\n"
            section += "   1. Determine the best section for placement based on content and context\n"
            section += "   2. Use replace_string_in_file to insert the embeddable markdown at the right location\n"
            section += "   3. Add a rich caption: `*Figure N: <detailed description of what the screenshot shows>*`\n\n"
        return section
    
    @staticmethod
    def _build_screenshot_verification_prompt(
        all_screenshots: Optional[List[Dict[str, Any]]] = None,
        snippets_file_path: Optional[str] = None
    ) -> str:
        """Build a verification prompt to ensure all screenshots were embedded."""
        if not all_screenshots:
            return ""
        
        section = f"\n[CHECK] **SCREENSHOT VERIFICATION ({len(all_screenshots)} total):**\n\n"
        section += "After completing all other tasks, verify that EVERY screenshot below appears in the documentation.\n"
        section += "Search the document for `![` markers or `data:image` strings to confirm embedding.\n\n"
        for i, ss in enumerate(all_screenshots, 1):
            context = ss.get('context', 'No context provided')
            comp = ss.get('component_path', 'Global')
            section += f"  {i}. \"{context}\" (component: {comp or 'Global'})\n"
        if snippets_file_path:
            section += f"\nIf any screenshot is MISSING from the document, read its embed snippet from `{snippets_file_path}` "
            section += "(find `## Screenshot N` matching the number above) and use `replace_string_in_file` to insert it.\n"
            section += "Place missing screenshots in `### 8.2 Screenshots or Diagrams` as a fallback.\n\n"
        else:
            section += f"\nIf any screenshot is MISSING from the document, embed it now using `replace_string_in_file`.\n"
            section += "Place missing screenshots in `### 8.2 Screenshots or Diagrams` as a fallback.\n\n"
        return section
    
    async def generate_documentation_consolidation(
        self,
        session_id: str,
        working_directory: Path,
        critical_files: List[tuple],
        non_critical_files: List[tuple],
        template_content: str,
        selection_context: str = "",
        business_context: str = ""
    ) -> str:
        """
        [LEGACY METHOD - Slower consolidation approach]
        Generate documentation using section-by-section consolidation
        
        Args:
            session_id: Session identifier for progress tracking
            working_directory: Path to extracted solution
            critical_files: List of (path, content) tuples for critical files
            non_critical_files: List of (path, content) tuples for supporting files
            template_content: Documentation template structure
            selection_context: Context about selected components
            business_context: User-provided business context
            
        Returns:
            Generated documentation as markdown string
        """
        if not self.client:
            raise RuntimeError("DocumentationGenerator not initialized")
        
        # Total steps: critical files + 7 documentation sections
        total_sections = 7  # frontmatter, overview, technical_specs, development, usage, maintenance, appendices
        total_steps = len(critical_files) + total_sections
        
        try:
            self._update_progress(
                session_id, 
                "initializing", 
                0, 
                total_steps, 
                "Creating isolated documentation session"
            )
            
            # Create a temporary, isolated Copilot session just for doc generation
            # No event handlers means no WebSocket interference
            session_config = {
                "model": config.COPILOT_MODEL,
                "working_directory": str(working_directory),
                "streaming": False,  # Disable streaming to avoid chat interference
                "tools": [],  # No tools needed for doc generation
                "system_message": {
                    "mode": "append",
                    "content": self._build_system_prompt()
                }
            }
            
            # Disable infinite sessions for doc generation (keep it simple)
            temp_session = await self.client.create_session(session_config)
            logger.info(f"Created isolated Copilot session for doc generation: {session_id}")
            
            # PASS 1: Analyze each critical file individually
            critical_file_analyses = []
            
            for idx, (path, content) in enumerate(critical_files, 1):
                try:
                    self._update_progress(
                        session_id,
                        "analyzing_critical",
                        idx,
                        total_steps,
                        f"Analyzing critical file: {Path(path).name}"
                    )
                    
                    logger.info(f"Pass {idx}/{len(critical_files)}: Analyzing {path}...")
                    
                    prompt = self._build_critical_file_prompt(
                        path, 
                        content, 
                        idx, 
                        len(critical_files),
                        template_content,
                        selection_context
                    )
                    
                    # Send and wait for response WITHOUT streaming to WebSocket
                    result = await temp_session.send_and_wait(
                        {"prompt": prompt},
                        timeout=config.DOC_GEN_FILE_TIMEOUT  # Per-file timeout (configurable)
                    )
                    
                    analysis = ""
                    if result and hasattr(result, 'data') and hasattr(result.data, 'content'):
                        analysis = result.data.content
                        
                        # Truncate if too large
                        max_size = 50000
                        if len(analysis) > max_size:
                            logger.warning(f"Analysis for {path} is large ({len(analysis)} chars), truncating")
                            analysis = analysis[:max_size] + "\n\n*[Analysis truncated]*"
                        
                        critical_file_analyses.append({
                            "file": path,
                            "analysis": analysis
                        })
                        logger.info(f"✓ Pass {idx} complete: {len(analysis)} chars")
                    else:
                        logger.warning(f"No response for {path}")
                        critical_file_analyses.append({
                            "file": path,
                            "analysis": f"*Analysis unavailable for {path}*"
                        })
                
                except asyncio.TimeoutError:
                    logger.error(f"Timeout analyzing {path}")
                    critical_file_analyses.append({
                        "file": path,
                        "analysis": f"*Analysis timed out for {path}*"
                    })
                except Exception as e:
                    logger.error(f"Error analyzing {path}: {e}")
                    critical_file_analyses.append({
                        "file": path,
                        "analysis": f"*Error analyzing {path}: {str(e)}*"
                    })
            
            # PASS 2: Section-by-section consolidation (instead of one large pass)
            critical_summaries = "\n\n".join([
                f"## Critical File: {item['file']}\n{item['analysis']}"
                for item in critical_file_analyses
            ])
            
            non_critical_section = self._build_non_critical_summary(non_critical_files)
            
            # Define sections to generate
            sections = [
                ("frontmatter", "Frontmatter & Project Info"),
                ("overview", "Project Overview"),
                ("technical_specs", "Technical Specifications"),
                ("development", "Development Details"),
                ("usage", "Usage Instructions"),
                ("maintenance", "Maintenance & Roadmap"),
                ("appendices", "Appendices")
            ]
            
            documentation_sections = {}  # Initialize for error handling
            total_consolidation_steps = len(sections)
            
            logger.info(f"Starting section-by-section consolidation ({total_consolidation_steps} sections)...")
            
            for idx, (section_id, section_name) in enumerate(sections, 1):
                try:
                    self._update_progress(
                        session_id,
                        "consolidating",
                        len(critical_files) + idx,
                        len(critical_files) + total_consolidation_steps,
                        f"Generating {section_name}"
                    )
                    
                    logger.info(f"Section {idx}/{total_consolidation_steps}: Generating {section_name}...")
                    
                    section_prompt = self._build_section_prompt(
                        section_id,
                        critical_summaries,
                        non_critical_section,
                        template_content,
                        selection_context,
                        business_context
                    )
                    
                    # Generate this section
                    result = await temp_session.send_and_wait(
                        {"prompt": section_prompt},
                        timeout=config.DOC_GEN_SECTION_TIMEOUT  # Per-section timeout
                    )
                    
                    section_content = ""
                    if result and hasattr(result, 'data') and hasattr(result.data, 'content'):
                        section_content = result.data.content
                        logger.info(f"✓ Section {idx} complete: {len(section_content)} chars")
                        
                        # Validate section immediately after generation
                        is_valid, issues = self._validate_section_against_template(
                            section_content, 
                            section_id, 
                            {}
                        )
                        
                        if not is_valid:
                            logger.warning(f"⚠️  Section '{section_id}' validation warnings: {'; '.join(issues)}")
                            # Still keep the content - validation is informative, not blocking
                        
                    else:
                        logger.warning(f"No response for section {section_id}")
                        section_content = f"*Section {section_name} unavailable*\n\n"
                    
                    documentation_sections[section_id] = section_content
                    
                except asyncio.TimeoutError:
                    logger.error(f"Timeout generating section {section_id}")
                    documentation_sections[section_id] = f"*Section {section_name} timed out*\n\n"
                except Exception as e:
                    logger.error(f"Error generating section {section_id}: {e}")
                    documentation_sections[section_id] = f"*Error generating {section_name}: {str(e)}*\n\n"
            
            # Combine all sections into final document
            logger.info("Combining all sections into final document...")
            
            documentation = self._combine_sections(documentation_sections)
            
            # Clean up the temporary session
            try:
                await temp_session.terminate()
                logger.info("Isolated doc generation session terminated")
            except Exception as e:
                logger.warning(f"Error terminating doc session: {e}")
            
            # Mark as complete
            self._update_progress(
                session_id,
                "complete",
                total_steps,
                total_steps,
                "Documentation generation complete"
            )
            
            return documentation
        
        except asyncio.TimeoutError:
            # Timeout during section generation - return partial results
            logger.error(f"Timeout during section generation for {session_id}")
            self._update_progress(
                session_id,
                "partial",
                0,
                total_steps,
                "Timeout during section generation - returning partial documentation"
            )
            
            # Build partial documentation from completed sections
            if documentation_sections:
                partial_doc = self._combine_sections(documentation_sections)
                partial_doc += "\n\n---\n\n"
                partial_doc += "*Note: Documentation generation timed out during section generation. *"
                partial_doc += f"*Successfully generated {len(documentation_sections)} of {total_consolidation_steps} sections. *"
                partial_doc += f"*Sections with timeouts may show placeholder content.*\n"
                
                # Clean up session
                try:
                    await temp_session.terminate()
                except:
                    pass
                
                return partial_doc
            elif critical_file_analyses:
                # Fall back to file analyses if no sections were completed
                partial_doc = "# Low-Code Project Documentation\n\n"
                partial_doc += "*Note: Documentation generation timed out before section consolidation. *"
                partial_doc += "*Below are the individual file analyses that were completed.*\n\n"
                partial_doc += "## Individual Component Analyses\n\n"
                
                for item in critical_file_analyses:
                    partial_doc += f"### {item['file']}\n\n"
                    partial_doc += f"{item['analysis']}\n\n"
                    partial_doc += "---\n\n"
                
                partial_doc += f"\n\n*Analyzed {len(critical_file_analyses)} critical files successfully.*\n"
                
                # Clean up session
                try:
                    await temp_session.terminate()
                except:
                    pass
                
                return partial_doc
            else:
                raise
            
        except Exception as e:
            logger.exception(f"Error generating documentation for {session_id}")
            self._update_progress(
                session_id,
                "error",
                0,
                total_steps,
                f"Error: {str(e)}"
            )
            raise
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for documentation generation"""
        return """You are a Power Platform documentation specialist. Your role is to analyze solution components and generate comprehensive technical documentation.

POWER PLATFORM CONCEPTS:
- **Power Fx**: Low-code functional language (similar to Excel formulas) used in Canvas Apps
- **Power Automate Flows**: Workflow automation with triggers, actions, and conditions
- **Canvas Apps**: Custom UI applications with screens, controls, and formulas
- **Dataverse**: Microsoft's cloud database platform for business data

YOUR TASK:
Analyze the provided Power Platform components and generate clear, well-organized documentation that:
1. Explains what each component does from a business perspective
2. Documents key formulas, logic, and workflows
3. Identifies data sources and connections
4. Highlights dependencies and relationships
5. Follows the provided template structure

Be thorough but concise. Focus on business logic and important technical details."""
    
    def _build_incremental_system_prompt(self, doc_file_path: str, screenshots: Optional[List[Dict[str, Any]]] = None) -> str:
        """Build system prompt for incremental template editing approach"""
        return f"""[!] CRITICAL: This is a FILE EDITING task, not a conversation.

YOU MUST USE TOOLS TO EDIT THE FILE. DO NOT WRITE TEXT RESPONSES.

**DOCUMENTATION FILE:** `{doc_file_path}`

**PROHIBITED ACTIONS:**
[X] DO NOT write conversational responses describing what you would do
[X] DO NOT say "I will edit the file..." or "Here's what I found..."
[X] DO NOT provide summaries or explanations in text
[X] DO NOT describe tool calls - EXECUTE them

**REQUIRED ACTIONS:**
[OK] USE read_file to check current state
[OK] USE replace_string_in_file or multi_replace_string_in_file to ACTUALLY edit the file
[OK] Make the edits directly - your ONLY output should be tool calls
[OK] Edit the file immediately upon analyzing each component

---

**YOUR ROLE:** Power Platform documentation specialist using INCREMENTAL EDITING

**YOUR TASK:**
1. Read the current state of `{doc_file_path}` 
2. Identify which sections are relevant to the component you're analyzing
3. USE replace_string_in_file to fill in those sections with actual content
4. Preserve template structure and existing content
5. When screenshots are attached, USE YOUR VISION to analyze them and write detailed descriptions

**VISUAL CAPABILITIES:**
You can SEE image attachments. When screenshots are provided:
- Study them to identify UI elements, controls, layouts, data fields, flow steps
- Write detailed descriptions of what you observe directly into the documentation
- The visual analysis should add information BEYOND what the source code alone reveals
- Example: A screenshot of a screen may show a gallery with specific columns, color coding, icons — describe all of this

POWER PLATFORM CONCEPTS:
- **Power Fx**: Low-code formulas (like Excel) in Canvas Apps  
- **Power Automate**: Workflow automation with triggers and actions
- **Canvas Apps**: Custom UI apps with screens and controls
- **Dataverse**: Microsoft's cloud database for business data

[TOOLS]️ **AVAILABLE TOOLS:**

You have access to these file editing tools:

- **read_file**: Read current state of documentation file
  ```
  read_file(filePath="{doc_file_path}", startLine=1, endLine=100)
  ```

- **replace_string_in_file**: Replace specific text in documentation
  ```
  replace_string_in_file(
      filePath="{doc_file_path}",
      oldString="**Formulas:**\\n[Placeholder]",
      newString="**Formulas:**\\n- **Screen1.OnVisible:** ..."
  )
  ```

- **multi_replace_string_in_file**: Make multiple edits at once (more efficient)
  ```
  multi_replace_string_in_file(
      explanation="Add screen and formula info",
      replacements=[
          {{filePath: "...", oldString: "...", newString: "..."}},
          {{filePath: "...", oldString: "...", newString: "..."}}
      ]
  )
  ```

- **grep_search**: Find specific sections in the doc
  ```
  grep_search(query="### 3.4 Logic and Automation", isRegexp=false, includePattern="{doc_file_path}")
  ```

[TARGET] **EDITING WORKFLOW:**

For each file you analyze:

1. **Read** relevant section(s) with `read_file`
2. **Find** exact text to replace with `grep_search` if needed
3. **Replace** placeholder or append to existing content with `replace_string_in_file`
4. Include enough context (3-5 lines before/after) in `oldString` for precise matching

⚠️ **CRITICAL:**
- Always use file editing tools to modify `{doc_file_path}`
- Don't just describe changes - actually make them!
- Include sufficient context in oldString (multi-line with before/after)
- When appending to lists, read existing content first
- Build documentation incrementally, file by file

{self._build_screenshot_system_instructions(screenshots)}

Be precise with edits. Use the tools to actually modify the documentation file."""
    
    def _build_incremental_file_prompt(
        self,
        path: str,
        content: str,
        idx: int,
        total: int,
        doc_file_path: str,
        selection_context: str,
        business_context: str
    ) -> str:
        """Build prompt for incremental file analysis with direct template editing"""
        
        # Determine file type and likely relevant sections
        path_lower = path.lower()
        relevant_sections_hint = ""
        
        if '.fx.yaml' in path_lower:
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
- `### 3.3 User Interface` (if it's a screen)
- `### 3.4 Logic and Automation` (formulas)
- `### 2.2 Data Sources` (if data sources referenced)
"""
        elif 'canvasmanifest' in path_lower:
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
- `## Project Information` (project name, version)
- `### 2.1 Platform Overview` (app type, environment)
- `### 2.3 Technology Stack` (components count)
"""
        elif 'workflows' in path_lower and path_lower.endswith('.json'):
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
- `### 3.4 Logic and Automation` (Power Automate Flows)
- `### 2.2 Data Sources` (connectors used)
- `### 2.1 Platform Overview` (Power Automate integration)
"""
        elif 'datasources' in path_lower:
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
- `### 2.2 Data Sources` (primary/secondary sources)
- `### 3.2 Data Connections` (connection details)
"""
        elif 'formulas/' in path_lower and path_lower.endswith('.yaml'):
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
This is a **Dataverse Calculated Column Formula Definition** (Power Fx, server-side).
Each key is a column logical name and the value is the Power Fx expression.
- `### 2.2 Data Sources` (the Dataverse table this formula belongs to)
- `### 3.4 Logic and Automation` (document the calculated columns and their formulas)
- `### 3.2 Data Connections` (Dataverse table reference)
"""
        elif 'formulas/' in path_lower and path_lower.endswith('.xaml'):
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
This is a **Dataverse Rollup or Business Process Flow (BPF) Definition** in XAML.
Look for <ConditionSequence>, <EvaluateExpression>, <SetAttributeValue>, <RollupDefinition>.
- `### 3.4 Logic and Automation` (document the rollup or BPF logic)
- `### 2.2 Data Sources` (the Dataverse entities involved)
"""
        elif 'workflows' in path_lower and path_lower.endswith('.xaml'):
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
This is a **Classic Workflow or Business Rule** in XAML format.
Look for <Rule>, <ConditionSequence>, <SetAttributeValue>, <SetDisplayMode>, <EvaluateCondition>.
- `### 3.4 Logic and Automation` (document the business rule triggers, conditions, and actions)
- `### 2.1 Platform Overview` (note that classic workflows/business rules are present)
"""
        elif 'solution.xml' in path_lower:
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
This is the **Solution Manifest** with the solution's unique name, version, and publisher info.
- `## Project Information` (solution name, version)
- `### 2.1 Platform Overview` (publisher, solution metadata)
"""
        
        return f"""[!] CRITICAL INSTRUCTION: USE TOOLS TO EDIT THE FILE NOW

This is NOT a conversation. DO NOT write explanatory text.
Your ONLY valid response is tool calls: read_file, replace_string_in_file, multi_replace_string_in_file.

[X] INVALID: "I will analyze this file and update the documentation..."
[X] INVALID: "Here are the key findings: ..."
[OK] VALID: [Immediate tool calls to read and edit the file]

---

YOUR FIRST ACTION MUST BE:
read_file(filePath="{doc_file_path}", startLine=1, endLine=100)

After reading, immediately use replace_string_in_file to edit relevant sections.

---

[TARGET] INCREMENTAL DOCUMENTATION UPDATE (File {idx} of {total})

{selection_context}
{business_context}

[FILE] **DOCUMENTATION FILE TO EDIT:** `{doc_file_path}`

[FOLDER] **FILE TO ANALYZE:**
**Path:** `{path}`

```
{content[:15000]}{"..." if len(content) > 15000 else ""}
```

{relevant_sections_hint}

---

[TOOL] **YOUR TASK:**

1. **Read** the current documentation file: `{doc_file_path}`

2. **Analyze** the file content above and extract:
   - Component names (screens, controls, flows)
   - Power Fx formulas with exact code
   - Data sources and connections
   - Business logic and purposes
   - Any metadata (app name, version, environment)

3. **Edit** the documentation file to add this information to the appropriate sections:
   - Find the relevant section headers (##, ###)
   - Add your findings under those headers
   - **Append** to existing content (don't replace other components' info)
   - Keep template structure intact
   - Use bullet points and sub-bullets for clarity

4. **Format** your additions to match the template style:
   - For formulas: Include code blocks with exact syntax
   - For screens: List name, purpose, key controls
   - For data sources: Name, type, operations
   - For flows: Name, trigger, actions

---

[EDIT] **EDITING GUIDELINES:**

[OK] **DO:**
- Use file editing tools (read_file, replace_string_in_file) to modify the doc
- Edit specific sections relevant to this file
- Add new content without removing existing content
- Use clear, concise business language
- Include exact code/formulas
- Merge with existing entries (e.g., add to screens list)

[STOP] **DON'T:**
- Don't just describe changes - use the tools!
- Don't rewrite the entire file
- Don't remove placeholder text for sections you're not filling
- Don't duplicate information already in the doc
- Don't add conversational commentary

---

**Example Tool Usage:**

If analyzing a screen with formulas:

```
# Step 1: Read current state
read_file(filePath="{doc_file_path}", startLine=100, endLine=150)

# Step 2: Check what's already there
grep_search(query="### 3.4 Logic and Automation", isRegexp=false)

# Step 3: Replace placeholder with actual content
replace_string_in_file(
    filePath="{doc_file_path}",
    oldString='''### 3.4 Logic and Automation

**Formulas:**
[Placeholder]''',
    newString='''### 3.4 Logic and Automation

**Formulas:**
- **HomeScreen.Gallery1.Items:**
  ```
  SortByColumns(Filter(Orders, Status = "Active"), "Date", Descending)
  ```
  Purpose: Display active orders sorted by date'''
)
```

Or to append to an existing list:

```
# Read first to see what's there
read_file(filePath="{doc_file_path}", startLine=200, endLine=220)

# Then append
replace_string_in_file(
    filePath="{doc_file_path}",
    oldString='''- **HomeScreen.Gallery1.Items:**
  ```
  SortByColumns(Filter(Orders, Status = "Active"), "Date", Descending)
  ```
  Purpose: Display active orders sorted by date

---''',
    newString='''- **HomeScreen.Gallery1.Items:**
  ```
  SortByColumns(Filter(Orders, Status = "Active"), "Date", Descending)
  ```
  Purpose: Display active orders sorted by date
  
- **DetailScreen.SaveBtn.OnSelect:**
  ```
  SubmitForm(OrderForm); Navigate(HomeScreen, Fade)
  ```
  Purpose: Save order and return to home

---'''
)
```

---

[START] **START NOW:**

Step 1: Call read_file to see the current template state
Step 2: Analyze the file content provided above  
Step 3: Call replace_string_in_file to add your findings to relevant sections

BEGIN WITH TOOL USAGE IMMEDIATELY - NO TEXT RESPONSES."""
    
    def _build_incremental_final_prompt(
        self,
        doc_file_path: str,
        selection_context: str,
        business_context: str,
        files_analyzed: int,
        critical_files: List[tuple],
        non_critical_files: List[tuple],
        working_directory: Path,
        global_screenshots: Optional[List[Dict[str, Any]]] = None,
        all_screenshots: Optional[List[Dict[str, Any]]] = None,
        screenshots_snippets_file: Optional[str] = None
    ) -> str:
        """Build prompt for final formatting and gap-filling pass with exploration capability"""
        
        # Build file inventory for context
        files_inventory = "\n[INVENTORY] **ALL SOLUTION FILES AVAILABLE FOR EXPLORATION:**\n\n"
        files_inventory += "**Already Analyzed (Critical Files):**\n"
        for path, _ in critical_files:
            rel_path = Path(path).relative_to(working_directory) if Path(path).is_absolute() else Path(path)
            files_inventory += f"  - {rel_path}\n"
        
        files_inventory += "\n**Additional Files (Available for Gap-Filling):**\n"
        if non_critical_files:
            # Group by type for easier navigation
            data_sources = []
            connections = []
            other_files = []
            
            for path, _ in non_critical_files:
                rel_path = Path(path).relative_to(working_directory) if Path(path).is_absolute() else Path(path)
                path_str = str(rel_path)
                
                if 'DataSources' in path_str or 'datasource' in path_str.lower():
                    data_sources.append(rel_path)
                elif 'Connections' in path_str or 'connection' in path_str.lower():
                    connections.append(rel_path)
                else:
                    other_files.append(rel_path)
            
            if data_sources:
                files_inventory += "\n  **Data Sources** (useful for Section 2.2):\n"
                for f in data_sources[:10]:  # Limit to first 10 to avoid prompt bloat
                    files_inventory += f"    - {f}\n"
                if len(data_sources) > 10:
                    files_inventory += f"    ... and {len(data_sources) - 10} more data source files\n"
            
            if connections:
                files_inventory += "\n  **Connections** (useful for Section 3.2, 2.2):\n"
                for f in connections[:10]:
                    files_inventory += f"    - {f}\n"
                if len(connections) > 10:
                    files_inventory += f"    ... and {len(connections) - 10} more connection files\n"
            
            if other_files:
                files_inventory += "\n  **Other Supporting Files:**\n"
                for f in other_files[:15]:
                    files_inventory += f"    - {f}\n"
                if len(other_files) > 15:
                    files_inventory += f"    ... and {len(other_files) - 15} more files\n"
        else:
            files_inventory += "  (No additional files available)\n"
        
        files_inventory += f"\n**Working Directory:** `{working_directory}`\n"
        files_inventory += "\n**EXPLORATION TOOLS AVAILABLE:**\n"
        files_inventory += "  - `read_file()` - Read specific files to extract details\n"
        files_inventory += "  - `grep_search()` - Search for patterns across files\n"
        files_inventory += "  - `semantic_search()` - Find relevant code/content\n"
        files_inventory += "  - `list_dir()` - Explore directory structure\n\n"
        
        return f"""[!] CRITICAL: FILE EDITING TASK - USE TOOLS ONLY

DO NOT write text responses. USE read_file and replace_string_in_file to edit `{doc_file_path}`.

[X] PROHIBITED: "I'll now format the documentation..."
[X] PROHIBITED: "Here's the final version..."
[OK] REQUIRED: [Immediate tool calls to read and edit the file]

YOUR FIRST ACTION MUST BE:
read_file(filePath="{doc_file_path}", startLine=1, endLine=200)

After reading, use replace_string_in_file to fill frontmatter, generate overview, and complete remaining sections.

---

{files_inventory}

---

[TARGET] FINAL DOCUMENTATION POLISH

{selection_context}
{business_context}

[FILE] **DOCUMENTATION FILE:** `{doc_file_path}`

You've just analyzed {files_analyzed} Power Platform files and incrementally updated the documentation.

---

[TOOL] **YOUR FINAL TASKS:**

1. **Read** the current state of `{doc_file_path}`

2. **Fill Frontmatter:**
   - Extract project name from manifest data if available
   - Add today's date as "Last Updated"
   - Synthesize "Purpose" from components analyzed AND business context provided above

3. **Generate Project Overview (Section 1):**
   - Write 2-3 paragraphs synthesizing what the app does
   - **IMPORTANT**: Incorporate the business context above to explain the WHY (business purpose) not just the WHAT (technical components)
   - List objectives based on components/flows AND business goals mentioned in context
   - Count screens, flows, data sources for "Scope"

4. **Fill Empty Sections - WITH EXPLORATION:**
   - Review the documentation for gaps or placeholder text
   - **EXPLORE ADDITIONAL FILES** listed above when helpful:
     * **For Section 2.2 (Data Sources):** Read DataSource files and Connection files to identify:
       - External data connections (SharePoint, SQL, APIs)
       - Connection authentication methods
       - Data security and permissions
     * **For Section 3.2 (Data Connections):** Read Connection files for:
       - Connection configuration details
       - OAuth settings, service principals
       - Connection references and environment variables
     * **For other sections:** Use grep_search or semantic_search to find relevant content
   - Any section still showing placeholder text should be updated:
     * If no data exists even after exploration: Keep placeholder but make it specific (e.g., "*No custom components identified*")
     * If partial data: Complete the section using explored files

5. **Add Table of Contents:**
   - Generate TOC links based on actual sections present

6. **Format & Polish:**
   - Ensure consistent markdown formatting
   - Check for duplicate entries
   - Ensure all section headers match template
   - Add linebreaks for readability

7. **Create Glossary (Section 8.1):**
   - Add technical terms found in the documentation

---

[LIST] **QUALITY CHECKS:**

[OK] All major sections present (1-8)
[OK] Project Information complete with business context incorporated
[OK] Table of Contents generated
[OK] No placeholder text where real data exists
[OK] Additional files explored to fill data source and connection details
[OK] Consistent formatting throughout
[OK] Clear, professional language
[OK] Business context integrated into Purpose, Overview, and relevant sections

---

**OUTPUT:**

Make all necessary edits to `{doc_file_path}` to produce a polished, complete, professional documentation file.

{self._build_global_screenshots_prompt(global_screenshots, snippets_file_path=screenshots_snippets_file, all_screenshots=all_screenshots)}

{self._build_screenshot_verification_prompt(all_screenshots, snippets_file_path=screenshots_snippets_file)}

Focus on:
- **Completeness** (fill all fillable sections, explore additional files when needed)
- **Coherence** (sections flow logically)
- **Conciseness** (remove redundancy)
- **Clarity** (business-friendly language)
- **Context Integration** (weave business context into relevant sections to explain purpose and value)
- **Exploration** (leverage available files above to enrich data source and connection details)

[START] **START NOW:**

Step 1: read_file to see current documentation state
Step 2: replace_string_in_file to fill frontmatter (project name, date, purpose)
Step 3: replace_string_in_file to generate Project Overview incorporating business context
Step 4: replace_string_in_file to create Table of Contents
Step 5: **EXPLORE additional files** (DataSources, Connections) to enrich Section 2.2 and 3.2
Step 6: replace_string_in_file to fill enriched data source/connection details
Step 7: replace_string_in_file to fill any remaining gaps

BEGIN WITH TOOL CALLS IMMEDIATELY - NO CONVERSATIONAL TEXT."""
    
    def _build_critical_file_prompt(self, path, content, idx, total, template_content, selection_context):
        return f"""You are analyzing Power Platform files for structured documentation.

[TARGET] TASK: Analyze file and output in STRUCTURED FORMAT mapped to template sections (Pass {idx} of {total})

{selection_context}

[FOLDER] FILE TO ANALYZE:
**Path:** {path}

```
{content}
```

[LIST] TEMPLATE STRUCTURE (Use these EXACT section headers):
{template_content}

---

[EDIT] REQUIRED OUTPUT FORMAT:

For EACH relevant template section, output:

```
### [EXACT SECTION HEADER FROM TEMPLATE ABOVE]

[Structured content following template format]

---
```

[TIP] EXAMPLES BY FILE TYPE:

**Example A - Canvas App Screen (.fx.yaml file):**
```
### 3.3 User Interface

**Screens and Navigation:**
- **Screen Name:** DetailScreen
  - Purpose: Display and edit order details
  - Key Controls: 
    * OrderForm (Form): Editable order fields
    * SaveBtn (Button): Submit changes
    * CancelBtn (Button): Discard and return
  - Navigation: Accessed from HomeScreen.Gallery.OnSelect

---

### 3.4 Logic and Automation

**Formulas:**
- **SaveBtn.OnSelect:**
  ```
  SubmitForm(OrderForm); Navigate(HomeScreen, ScreenTransition.Fade)
  ```
  Purpose: Save form data and return to home screen

- **OrderForm.Item:**
  ```
  LookUp(Orders, ID = SelectedOrder.ID)
  ```
  Purpose: Load selected order data into form

---

### 2.2 Data Sources

- **Orders** (SharePoint List)
  - Type: SharePoint
  - Operations: Read, Write
  - Usage: Form data source for viewing/editing orders

---
```

**Example B - Power Automate Flow (workflow .json file):**
```
### 3.4 Logic and Automation

**Power Automate Flows:**
- **Flow Name:** Notify Manager on High Value Order
  - **Trigger:** When an item is created or modified (OrdersList)
  - **Condition:** Order amount > $5000
  - **Actions:**
    1. Get item details from OrdersList
    2. Get manager email from User Profile Service
    3. Send email notification to manager
    4. Update order status to "Pending Approval"
  - **Error Handling:** If email fails, log to ErrorLog list

---

### 2.2 Data Sources

- **OrdersList** (SharePoint)
  - Type: SharePoint List
  - Operations: Read (trigger), Write (status update)
  - Table/List: OrdersList on Sales site

- **User Profile Service** (Office 365)
  - Type: Office 365 Users connector
  - Operations: Read (get manager)

---
```

**Example C - Data Source Config (DataSources.json or Connections.json):**
```
### 2.2 Data Sources

- **CustomersDB** (Dataverse)
  - Type: Microsoft Dataverse
  - Tables: Customers, Accounts, Contacts
  - Operations: Read, Write

- **ProductCatalog** (SQL Server)
  - Type: SQL Server
  - Connection: ProductionDB server
  - Tables: Products, Categories, Pricing
  - Operations: Read-only

---

### 3.2 Data Connections

- **Dataverse Connector**
  - Authentication: OAuth 2.0 (user context)
  - Permissions: Read/Write on Customer tables
  - Environment: Production

- **SQL Server Connector**
  - Authentication: SQL Server authentication
  - Permissions: Read-only on ProductionDB
  - Connection String: [Encrypted]

---
```

**Example D - Manifest File (CanvasManifest.json):**
```
### 2.1 Platform Overview

- **Type of PowerApp:** Canvas App
- **Environment:** Production
- **Power Platform Integrations:** 
  - SharePoint (data source)
  - Power Automate (3 flows)
  - Office 365 Users (authentication)

---

### 2.3 Technology Stack

- **PowerApps Components:**
  - 5 screens (Home, Detail, Add, Edit, Settings)
  - 12 galleries, 8 forms, 24 buttons
  - Custom components: DatePickerPro, StatusBadge

- **Custom Code/Expressions:**
  - 47 Power Fx formulas
  - Date manipulation functions
  - Conditional visibility logic

---
```

⚠️ CRITICAL OUTPUT RULES:

[OK] **MUST DO:**
- Copy section headers EXACTLY from template (###, numbers, titles)
- Extract ACTUAL code, formulas, names - preserve exact syntax
- Follow template's bullet structure within each section
- End each section with "---" separator
- Only output sections with real data from THIS file
- Keep sections focused: 100-400 words each

[STOP] **NEVER DO:**
- Don't invent section names - use template headers only
- Don't paraphrase formulas - copy exact code
- Don't add conversational text ("I found...", "This file contains...")
- Don't output empty sections
- Don't include template sections not relevant to this file

[TARGET] **What to Extract:**
- Screen/component names and purposes
- Exact Power Fx formulas with control.property format
- Flow names, triggers, actions, conditions
- Data source names, types, tables, operations
- Connector types and authentication
- App type, environment, integrations

Output the structured analysis now (sections with --- separators only)."""
    
    def _build_non_critical_summary(self, non_critical_files: List[tuple]) -> str:
        """Build summary section for non-critical files"""
        if not non_critical_files:
            return "*No additional supporting files*"
        
        max_files = 50
        summaries = []
        
        for path, content in non_critical_files[:max_files]:
            file_type = self._identify_file_type(path)
            summaries.append(f"- **{path}**: {file_type}")
        
        result = f"**Supporting Files ({len(non_critical_files)} total):**\n\n"
        result += "\n".join(summaries)
        
        if len(non_critical_files) > max_files:
            result += f"\n\n*... and {len(non_critical_files) - max_files} more files*"
        
        return result
    
    def _identify_file_type(self, path: str) -> str:
        """Identify file type for summary"""
        path_lower = path.lower()
        
        if 'canvasmanifest' in path_lower:
            return "Canvas app manifest"
        elif 'datasources' in path_lower:
            return "Data source configuration"
        elif 'connections' in path_lower:
            return "Connection configuration"
        elif 'editorstate' in path_lower:
            return "UI editor state"
        elif '.json' in path_lower:
            return "JSON configuration"
        elif '.xml' in path_lower:
            return "XML configuration"
        elif any(ext in path_lower for ext in ['.png', '.jpg', '.gif', '.svg']):
            return "Image asset"
        else:
            return "Supporting file"
    
    def _build_consolidation_prompt(
        self,
        critical_summaries: str,
        non_critical_section: str,
        template_content: str,
        selection_context: str,
        business_context: str
    ) -> str:
        """Build prompt for final consolidation with template adherence"""
        business_section = ""
        if business_context:
            business_section = f"""
[PIN] BUSINESS CONTEXT PROVIDED BY USER:
{business_context}

Incorporate this context when synthesizing the Project Overview and explaining component purposes.
"""
        
        return f"""You are performing FINAL CONSOLIDATION of pre-structured Power Platform documentation.

[TARGET] TASK: Merge structured analyses into complete documentation following the template

{selection_context}
{business_section}

[DATA] INPUT - PRE-STRUCTURED ANALYSES:
Each analysis below is already formatted with template section headers (###). Your job is to collect, merge, and organize them.

{critical_summaries}

[LIST] TEMPLATE TO FOLLOW (Use these EXACT headers in this EXACT order):
{template_content}

---

[TOOL] CONSOLIDATION PROCESS:

**1. EXTRACT & MERGE SECTIONS**

From the analyses above, collect all content under each section header:
- Find all "### 2.2 Data Sources" entries → merge into one list
- Find all "### 3.3 User Interface" entries → merge all screens
- Find all "### 3.4 Logic and Automation" entries → merge formulas + flows
- etc.

**Deduplication Rules:**
- Same data source mentioned twice → keep one, merge details
- Same formula in multiple files → list once with clear location
- Same screen mentioned → combine descriptions

**2. FOLLOW TEMPLATE ORDER & HEADERS**

- Use EXACT section headers from template (##, ###, numbers, titles)
- Output sections in template order
- Include all major sections (use placeholder if empty)

**3. ADD REQUIRED FRONTMATTER**

- **Project Information section:** Extract app name from manifests, synthesize purpose
- **Table of Contents:** Generate from actual sections included
- **Section 1 (Project Overview):** Write 2-3 paragraph synthesis of what the app does

**4. FILL EMPTY SECTIONS**

- If no content for a section: "*No [specific items] identified in the analyzed files.*"
- Sections 5-7 typically need placeholders (Troubleshooting, Maintenance, Roadmap)

---

[EDIT] EXACT OUTPUT STRUCTURE:

```markdown
# Low-Code Project Documentation

## Project Information

- **Project Name:** [Extract from manifest or app name in analyses]
- **Version:** [If found in analyses]
- **Last Updated:** [Today's date]
- **Author(s):** Auto-generated Documentation
- **Status:** Documented
- **Purpose:** [Synthesize from all component descriptions]

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technical Specifications](#2-technical-specifications)
   - [2.1 Platform Overview](#21-platform-overview)
   - [2.2 Data Sources](#22-data-sources)
   - [2.3 Technology Stack](#23-technology-stack)
3. [Development Details](#3-development-details)
   - [3.1 Application Setup](#31-application-setup)
   - [3.2 Data Connections](#32-data-connections)
   - [3.3 User Interface](#33-user-interface)
   - [3.4 Logic and Automation](#34-logic-and-automation)
4. [Usage Instructions](#4-usage-instructions)
5. [Troubleshooting and FAQs](#5-troubleshooting-and-faqs)
6. [Maintenance](#6-maintenance)
7. [Roadmap](#7-roadmap)
8. [Appendices](#8-appendices)

---

## 1. Project Overview

[SYNTHESIZE 2-3 paragraphs covering:
- What this Power Platform application does (high-level)
- Main business purposes and goals
- Key capabilities and features
- Target users
Base this on all the component analyses above]

- **Description:** [1-2 sentences summary]
- **Objectives:** [Main goals from analyses]
- **Scope:** [What's included: X screens, Y flows, Z data sources]
- **Target Audience:** [If identifiable from analyses]

---

## 2. Technical Specifications

### 2.1 Platform Overview

[MERGE all "### 2.1 Platform Overview" content from analyses above]
[If none found, use: "*Platform details: Canvas App (identified from analyzed components)*"]

- **Type of PowerApp:** [Canvas App / Model-Driven / Portal]
- **Environment:** [Production / Sandbox / identified from manifests]
- **Power Platform Integrations:** [List all: Power Automate, SharePoint, Dataverse, etc.]

### 2.2 Data Sources

[MERGE all "### 2.2 Data Sources" content from analyses above]
[Combine duplicate sources - if "Orders (SharePoint)" appears in 3 files, list once]

**Primary Data Sources:**
[List main data sources with types and operations]

**Secondary Data Sources:**
[List additional sources]

### 2.3 Technology Stack

[MERGE all "### 2.3 Technology Stack" content from analyses above]
[If none found, synthesize from components seen: "X screens, Y formulas, Z flows"]

- **PowerApps Components:** [Screens, galleries, forms, controls identified]
- **Custom Code/Expressions:** [Number of Power Fx formulas, complexity]

---

## 3. Development Details

### 3.1 Application Setup

[If setup info found in analyses, include it]
[Otherwise: "*Standard Power Apps environment setup required. Application accessed through https://apps.powerapps.com*"]

### 3.2 Data Connections

[MERGE all "### 3.2 Data Connections" content from analyses above]
[If none: "*Data connections configured: [list connector types from 2.2 Data Sources]*"]

### 3.3 User Interface

[MERGE all "### 3.3 User Interface" content from analyses above]

**Screens and Navigation:**
[List ALL screens found with purposes and key controls]

**Design Standards:**
[If design info found in analyses, include it, otherwise omit]

### 3.4 Logic and Automation

[MERGE all "### 3.4 Logic and Automation" content from analyses above]

**Formulas:**
[List ALL Power Fx formulas with exact code and purposes]

**Power Automate Flows:**
[List ALL flows with triggers and actions]

---

## 4. Usage Instructions

### 4.1 How to Access the App

[If OnStart or access info in analyses, use it]
[Otherwise: "*Application is accessed through Power Apps portal. Requires appropriate user permissions.*"]

### 4.2 Features

[Brief description based on screens and logic identified]

### 4.3 User Roles

[If role info found, include; otherwise: "*User roles and permissions managed through app settings.*"]

---

## 5. Troubleshooting and FAQs

### 5.1 Common Issues

*To be documented based on user feedback and testing.*

### 5.2 Error Messages

[If error handling logic found in analyses, document it]
[Otherwise: "*Error handling implemented in application logic.*"]

### 5.3 Support Contact

*Contact your Power Platform administrator or IT support team.*

---

## 6. Maintenance

### 6.1 Scheduled Updates

*Update schedule to be determined by application owners.*

### 6.2 Version Control

[If version info in manifest: include it]
[Otherwise: "*Application versioning managed through Power Apps environment.*"]

### 6.3 Backup Strategy

*Automated backups through Microsoft Dataverse and SharePoint.*

### 6.4 Performance Monitoring

*Monitor through Power Apps analytics and usage metrics.*

---

## 7. Roadmap

*Future enhancements and features to be determined based on user feedback.*

---

## 8. Appendices

### 8.1 Glossary

- **Power Fx:** Low-code formula language used in Canvas Apps
- **Canvas App:** Custom application with screens and controls
- **Power Automate:** Workflow automation platform
- **Dataverse:** Microsoft's cloud database platform
[Add other terms found in documentation]

### 8.2 Screenshots or Diagrams

*Visual documentation available upon request.*

### 8.3 Custom Components or Code

[If custom components identified in analyses, list them here]
[Otherwise: "*No custom components identified in analysis.*"]
```

⚠️ CRITICAL REQUIREMENTS:

[OK] **MUST DO:**
- Use EXACT section headers from template (copy ## and ### exactly)
- Follow template section order precisely
- Include ALL major sections (use placeholders for empty ones)
- Merge duplicate entries intelligently
- Preserve all exact formulas, code, and names from analyses
- Generate complete Table of Contents
- Start with "# Low-Code Project Documentation"

[STOP] **NEVER DO:**
- Don't skip template sections
- Don't invent new section headers
- Don't add conversational text ("As we can see...", "Based on...")
- Don't repeat the same information multiple times
- Don't include meta-commentary about the consolidation process

[TARGET] **Merging Logic:**
- Same data source in 3 files → List once, combine details
- 10 formulas across files → List all 10 under "### 3.4 Logic and Automation"
- 5 screens across files → List all 5 under "### 3.3 User Interface"
- Manifest in 1 file → Use for "### 2.1 Platform Overview" and "Project Information"

Output the complete consolidated documentation now."""
    
    def _build_section_prompt(
        self,
        section_id: str,
        critical_summaries: str,
        non_critical_section: str,
        template_content: str,
        selection_context: str,
        business_context: str
    ) -> str:
        """Build prompt for generating a specific section of documentation"""
        
        business_section = ""
        if business_context:
            business_section = f"""
[PIN] BUSINESS CONTEXT PROVIDED BY USER:
{business_context}

Incorporate this context when relevant to this section.
"""
        
        section_instructions = {
            "frontmatter": """
[TARGET] TASK: Generate the document frontmatter and project information section.

OUTPUT EXACTLY:

```markdown
# Low-Code Project Documentation

## Project Information

- **Project Name:** [Extract from manifest or app name in analyses]
- **Version:** [If found in analyses, otherwise "1.0.0"]
- **Last Updated:** [Today's date]
- **Author(s):** Auto-generated Documentation
- **Status:** Documented
- **Purpose:** [Synthesize from all component descriptions - 1-2 sentences]
```

Extract the project name from CanvasManifest.json or app metadata in the analyses.
Synthesize the purpose from component descriptions and business context.""",
            
            "overview": """
[TARGET] TASK: Generate Section 1 - Project Overview

OUTPUT EXACTLY:

```markdown
## 1. Project Overview

[SYNTHESIZE 2-3 paragraphs covering:
- What this Power Platform application does (high-level)
- Main business purposes and goals (use business context if provided)
- Key capabilities and features identified in analyses
- Target users (if identifiable)]

- **Description:** [1-2 sentences summary]
- **Objectives:** [Main goals from analyses and business context]
- **Scope:** [What's included: X screens, Y flows, Z data sources - count from analyses]
- **Target Audience:** [If identifiable from analyses, otherwise "End users"]
```

Base this on the component analyses and business context provided.""",
            
            "technical_specs": """
[TARGET] TASK: Generate Section 2 - Technical Specifications

Merge all instances of sections 2.1, 2.2, and 2.3 from the analyses.

OUTPUT EXACTLY:

```markdown
## 2. Technical Specifications

### 2.1 Platform Overview

[MERGE all "### 2.1 Platform Overview" content from analyses]
[If none found, synthesize from manifest: "Canvas App on Power Platform"]

- **Type of PowerApp:** [Canvas App / Model-Driven - get from manifest]
- **Environment:** [If found in analyses, otherwise "Production"]
- **Power Platform Integrations:** [List ALL: Power Automate, SharePoint, Dataverse, etc.]

### 2.2 Data Sources

[MERGE all "### 2.2 Data Sources" content from analyses]
[Combine duplicate sources - list each unique source once with consolidated details]

**Primary Data Sources:**
[List main data sources with types and operations]

**Secondary Data Sources:**
[List additional sources if any]

### 2.3 Technology Stack

[MERGE all "### 2.3 Technology Stack" content from analyses]

- **PowerApps Components:** [Count and list: screens, galleries, forms, controls]
- **Custom Code/Expressions:** [Number of Power Fx formulas, complexity level]
```

Deduplicate data sources intelligently - if the same source appears multiple times, merge the details.""",
            
            "development": """
[TARGET] TASK: Generate Section 3 - Development Details

Merge all instances of sections 3.1, 3.2, 3.3, and 3.4 from the analyses.

OUTPUT EXACTLY:

```markdown
## 3. Development Details

### 3.1 Application Setup

[If setup info found in analyses, include it]
[Otherwise: "Standard Power Apps environment setup required. Application accessed through https://apps.powerapps.com"]

### 3.2 Data Connections

[MERGE all "### 3.2 Data Connections" content from analyses]
[List all connections with configuration details]

### 3.3 User Interface

[MERGE all "### 3.3 User Interface" content from analyses]

**Screens and Navigation:**
[List ALL screens found with purposes, navigation flow, and key controls]

**Design Standards:**
[If design patterns found in analyses, include; otherwise omit]

### 3.4 Logic and Automation

[MERGE all "### 3.4 Logic and Automation" content from analyses]

**Formulas:**
[List ALL Power Fx formulas with exact code, screen/control location, and purposes]

**Power Automate Flows:**
[List ALL flows with triggers, actions, and purposes]
```

This is a critical section - include ALL formulas and ALL screens found in the analyses.""",
            
            "usage": """
[TARGET] TASK: Generate Section 4 - Usage Instructions

OUTPUT EXACTLY:

```markdown
## 4. Usage Instructions

### 4.1 How to Access the App

[If access instructions or OnStart logic found in analyses, use it]
[Otherwise: "Application is accessed through Power Apps portal (https://apps.powerapps.com). Requires appropriate user permissions."]

### 4.2 Features

[Brief description of main features based on screens and workflows identified]
[List 3-5 key features with short descriptions]

### 4.3 User Roles

[If role/permission logic found in analyses, document it]
[Otherwise: "User roles and permissions managed through app settings."]
```

Keep this section practical and user-focused.""",
            
            "maintenance": """
[TARGET] TASK: Generate Sections 5, 6, 7 - Troubleshooting, Maintenance, Roadmap

OUTPUT EXACTLY:

```markdown
## 5. Troubleshooting and FAQs

### 5.1 Common Issues

*To be documented based on user feedback and testing.*

### 5.2 Error Messages

[If error handling logic found in analyses, document specific error scenarios]
[Otherwise: "Error handling implemented in application logic."]

### 5.3 Support Contact

*Contact your Power Platform administrator or IT support team.*

---

## 6. Maintenance

### 6.1 Scheduled Updates

*Update schedule to be determined by application owners.*

### 6.2 Version Control

[If version info in manifest, include it]
[Otherwise: "Application versioning managed through Power Apps environment."]

### 6.3 Backup Strategy

*Automated backups through Microsoft Dataverse and SharePoint.*

### 6.4 Performance Monitoring

*Monitor through Power Apps analytics and usage metrics.*

---

## 7. Roadmap

*Future enhancements and features to be determined based on user feedback.*
```

These sections typically need placeholders unless specific info is found in analyses.""",
            
            "appendices": """
[TARGET] TASK: Generate Section 8 - Appendices

OUTPUT EXACTLY:

```markdown
## 8. Appendices

### 8.1 Glossary

- **Power Fx:** Low-code formula language used in Canvas Apps
- **Canvas App:** Custom application with screens and controls
- **Power Automate:** Workflow automation platform
- **Dataverse:** Microsoft's cloud database platform
- **Power Platform:** Microsoft's low-code development platform
[Add other technical terms found in analyses]

### 8.2 Screenshots or Diagrams

*Visual documentation available upon request.*

### 8.3 Custom Components or Code

[If custom components identified in analyses, list them here with details]
[Otherwise: "No custom components identified in analysis."]

### 8.4 Data Schema

[If table/entity schemas found in analyses, document them]
[Otherwise: omit this subsection]
```

Include any technical terms, custom components, or schema details found in the analyses."""
        }
        
        instruction = section_instructions.get(section_id, "Generate this section based on the template.")
        
        return f"""You are generating ONE SPECIFIC SECTION of Power Platform documentation.

{selection_context}
{business_section}

[DATA] INPUT - PRE-STRUCTURED ANALYSES:
{critical_summaries}

{instruction}

⚠️ CRITICAL:
- Output ONLY the markdown for this section
- Use EXACT section headers from the instruction above
- Merge duplicate entries intelligently
- Preserve exact formulas, code, and names from analyses
- Do NOT add conversational text
- Do NOT add meta-commentary

Output the section now:"""
    
    def _extract_template_headers(self, template_content: str) -> Dict[str, List[str]]:
        """
        Extract all section headers from template for validation.
        Returns dict mapping section levels to expected headers.
        """
        import re
        
        headers = {
            'h1': [],  # # headers
            'h2': [],  # ## headers  
            'h3': []   # ### headers
        }
        
        for line in template_content.split('\n'):
            line = line.strip()
            if line.startswith('### '):
                headers['h3'].append(line[4:].strip())
            elif line.startswith('## '):
                headers['h2'].append(line[3:].strip())
            elif line.startswith('# '):
                headers['h1'].append(line[2:].strip())
        
        logger.info(f"Template validation: Found {len(headers['h2'])} main sections, {len(headers['h3'])} subsections")
        return headers
    
    def _validate_section_against_template(
        self, 
        section_content: str, 
        section_id: str,
        template_headers: Dict[str, List[str]]
    ) -> tuple:
        """
        Validate that generated section contains expected headers.
        Returns (is_valid, issues_list).
        """
        import re
        
        issues = []
        
        # Expected headers by section
        expected_by_section = {
            'frontmatter': ['# Low-Code Project Documentation', '## Project Information'],
            'overview': ['## 1. Project Overview'],
            'technical_specs': ['## 2. Technical Specifications', '### 2.1 Platform Overview', 
                               '### 2.2 Data Sources', '### 2.3 Technology Stack'],
            'development': ['## 3. Development Details', '### 3.1 Application Setup',
                           '### 3.2 Data Connections', '### 3.3 User Interface', 
                           '### 3.4 Logic and Automation'],
            'usage': ['## 4. Usage Instructions'],
            'maintenance': ['## 5. Troubleshooting and FAQs', '## 6. Maintenance', '## 7. Roadmap'],
            'appendices': ['## 8. Appendices']
        }
        
        expected_headers = expected_by_section.get(section_id, [])
        
        if not expected_headers:
            return True, []  # No validation for unknown sections
        
        # Check for each expected header
        for expected in expected_headers:
            # Normalize comparison (ignore extra spaces, case-insensitive for better matching)
            if expected.lower() not in section_content.lower():
                # More lenient check - look for key parts
                key_part = expected.split('.')[-1].strip() if '.' in expected else expected.replace('#', '').strip()
                if key_part.lower() not in section_content.lower():
                    issues.append(f"Missing expected header: {expected}")
        
        is_valid = len(issues) == 0
        
        if not is_valid:
            logger.warning(f"Validation issues in section '{section_id}': {', '.join(issues)}")
        else:
            logger.info(f"✓ Section '{section_id}' validated successfully")
        
        return is_valid, issues
    
    def _combine_sections(self, sections: Dict[str, str]) -> str:
        """Combine generated sections into final documentation with validation"""
        
        # Generate table of contents
        toc = """---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technical Specifications](#2-technical-specifications)
   - [2.1 Platform Overview](#21-platform-overview)
   - [2.2 Data Sources](#22-data-sources)
   - [2.3 Technology Stack](#23-technology-stack)
3. [Development Details](#3-development-details)
   - [3.1 Application Setup](#31-application-setup)
   - [3.2 Data Connections](#32-data-connections)
   - [3.3 User Interface](#33-user-interface)
   - [3.4 Logic and Automation](#34-logic-and-automation)
4. [Usage Instructions](#4-usage-instructions)
5. [Troubleshooting and FAQs](#5-troubleshooting-and-faqs)
6. [Maintenance](#6-maintenance)
7. [Roadmap](#7-roadmap)
8. [Appendices](#8-appendices)

---

"""
        
        # Validate each section before combining
        validation_results = {}
        for section_id, content in sections.items():
            is_valid, issues = self._validate_section_against_template(content, section_id, {})
            validation_results[section_id] = {"valid": is_valid, "issues": issues}
        
        # Log overall validation status
        failed_sections = [sid for sid, result in validation_results.items() if not result["valid"]]
        if failed_sections:
            logger.warning(f"⚠️  Template validation warnings for sections: {', '.join(failed_sections)}")
        else:
            logger.info(f"✓ All {len(sections)} sections passed template validation")
        
        # Combine in order
        documentation = sections.get("frontmatter", "# Low-Code Project Documentation\n\n")
        documentation += toc
        documentation += sections.get("overview", "")
        documentation += "\n\n" + sections.get("technical_specs", "")
        documentation += "\n\n" + sections.get("development", "")
        documentation += "\n\n" + sections.get("usage", "")
        documentation += "\n\n" + sections.get("maintenance", "")
        documentation += "\n\n" + sections.get("appendices", "")
        
        logger.info(f"✓ Final documentation combined: {len(documentation)} chars")
        
        # Final validation: Check for all major sections in complete document
        major_sections = [
            "## 1. Project Overview",
            "## 2. Technical Specifications", 
            "## 3. Development Details",
            "## 4. Usage Instructions",
            "## 8. Appendices"
        ]
        
        missing_sections = [sec for sec in major_sections if sec not in documentation]
        if missing_sections:
            logger.error(f"[X] Final document missing sections: {', '.join(missing_sections)}")
        else:
            logger.info(f"✓ Final document contains all {len(major_sections)} major sections")
        
        # Truncate if suspiciously large
        max_size = 500000
        if len(documentation) > max_size:
            logger.warning(f"Documentation is very large ({len(documentation)} chars), truncating")
            documentation = documentation[:max_size] + "\n\n*[Documentation truncated due to excessive length]*"
        
        return documentation
    
    
# Global singleton instance
_doc_generator: Optional[DocumentationGenerator] = None


async def get_doc_generator() -> DocumentationGenerator:
    """Get or create the global documentation generator instance"""
    global _doc_generator
    
    if _doc_generator is None:
        _doc_generator = DocumentationGenerator()
        await _doc_generator.initialize()
    
    return _doc_generator
