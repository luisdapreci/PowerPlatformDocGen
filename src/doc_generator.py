"""
Dedicated Documentation Generator
Handles documentation generation separately from chat sessions to avoid interference
"""

import asyncio
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
                         'mime_type'
            
        Returns:
            Path to generated documentation file (in working directory)
        """
        if not self.client:
            raise RuntimeError("DocumentationGenerator not initialized")
        
        # Calculate total screenshot passes (computed after grouping below)
        num_screenshots = len(screenshots) if screenshots else 0
        
        # Define documentation sections for dedicated per-section passes
        doc_sections = [
            ("frontmatter", "Frontmatter & Project Info"),
            ("overview", "Project Overview"),
            ("technical_specs", "Technical Specifications"),
            ("development", "Development Details"),
            ("usage", "Usage Instructions"),
            ("maintenance", "Troubleshooting, Maintenance & Roadmap"),
            ("appendices", "Appendices & Table of Contents"),
        ]
        total_steps = len(critical_files) + num_screenshots + len(doc_sections)
        
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
                # Use parent of extracted/ so screenshots/ sibling dir is within working_directory.
                # Copilot CLI restricts file access to working_directory; screenshots are at
                # temp/{session_id}/screenshots/ while extracted/ is a sibling — using the parent
                # makes both accessible for image attachments and doc file writes.
                "working_directory": str(working_directory.parent),
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
            

            
            # Single monotonically increasing step counter across all passes
            current_step = 0
            screenshot_step = 0
            
            # PASS 1: Analyze each file and directly edit relevant template sections
            for idx, (path, content) in enumerate(critical_files, 1):
                try:
                    current_step += 1
                    self._update_progress(
                        session_id,
                        "analyzing",
                        current_step,
                        total_steps,
                        f"Analyzing and updating doc with: {Path(path).name}"
                    )
                    
                    logger.info(f"Pass {idx}/{len(critical_files)}: Analyzing {path} and editing template...")
                    
                    # Snapshot doc before this pass
                    _before_lines = doc_file.read_text(encoding='utf-8').splitlines()
                    
                    prompt = self._build_incremental_file_prompt(
                        path,
                        content,
                        idx,
                        len(critical_files),
                        str(doc_file),
                        selection_context,
                        business_section
                    )
                    
                    # Send prompt (no screenshot attachments — screenshots get their own passes)
                    send_payload = {"prompt": prompt}
                    
                    result = await temp_session.send_and_wait(
                        send_payload,
                        timeout=config.DOC_GEN_FILE_TIMEOUT
                    )
                    
                    # Compute line diff after pass
                    _after_lines = doc_file.read_text(encoding='utf-8').splitlines()
                    _added = max(0, len(_after_lines) - len(_before_lines))
                    _removed = max(0, len(_before_lines) - len(_after_lines))
                    _changed = sum(1 for a, b in zip(_before_lines, _after_lines) if a != b)
                    logger.info(f"✓ Pass {idx} complete: +{_added} -{_removed} lines, {_changed} lines changed")
                    self._update_progress(
                        session_id, "analyzing", current_step, total_steps,
                        f"✓ {Path(path).name}",
                        diff={"added": _added, "removed": _removed, "changed": _changed}
                    )
                
                except asyncio.TimeoutError:
                    logger.error(f"Timeout analyzing {path}")
                except Exception as e:
                    logger.error(f"Error analyzing {path}: {e}")
                
                # SCREENSHOT PASSES: After each component file, process its assigned screenshots
                file_screenshots = []
                norm_path = path.replace('\\', '/')
                for comp_path, ss_list in screenshots_by_component.items():
                    norm_comp = comp_path.replace('\\', '/')
                    if norm_comp in norm_path or norm_path in norm_comp:
                        file_screenshots.extend(ss_list)
                    elif Path(comp_path).stem in norm_path:
                        file_screenshots.extend(ss_list)
                
                for ss in file_screenshots:
                    screenshot_step += 1
                    current_step += 1
                    # Find this screenshot's index in the full list
                    ss_index = next((i for i, s in enumerate(screenshots, 1) if s.get('path') == ss.get('path')), screenshot_step)
                    
                    self._update_progress(
                        session_id,
                        "screenshot_analysis",
                        current_step,
                        total_steps,
                        f"Analyzing screenshot {screenshot_step}/{num_screenshots}: {ss.get('context', 'screenshot')[:50]}"
                    )
                    
                    logger.info(f"Screenshot pass {screenshot_step}/{num_screenshots}: {ss.get('context', 'No context')[:60]}")
                    
                    ss_prompt = self._build_screenshot_pass_prompt(
                        screenshot=ss,
                        screenshot_index=ss_index,
                        total_screenshots=num_screenshots,
                        doc_file_path=str(doc_file),
                        component_context=path
                    )
                    
                    _ss_before = doc_file.read_text(encoding='utf-8')
                    try:
                        ss_result = await temp_session.send_and_wait(
                            {
                                "prompt": ss_prompt,
                                "attachments": [{"type": "file", "path": ss.get('ai_path', ss['path'])}]
                            },
                            timeout=config.DOC_GEN_SCREENSHOT_TIMEOUT
                        )
                        _ss_after = doc_file.read_text(encoding='utf-8')
                        if _ss_after != _ss_before:
                            _before_lines = _ss_before.splitlines()
                            _after_lines = _ss_after.splitlines()
                            _added = max(0, len(_after_lines) - len(_before_lines))
                            _removed = max(0, len(_before_lines) - len(_after_lines))
                            _changed = sum(1 for a, b in zip(_before_lines, _after_lines) if a != b)
                            logger.info(f"✓ Pass {idx} screenshot {screenshot_step} complete: +{_added} -{_removed} lines, {_changed} lines changed")
                            logger.info(f"✓ Screenshot pass {screenshot_step} complete: +{_added} -{_removed} lines, {_changed} lines changed")
                        else:
                            logger.warning(f"Screenshot pass {screenshot_step}: no file edits detected, applying fallback embed")
                            _ss_text = ""
                            if ss_result and hasattr(ss_result, 'data') and hasattr(ss_result.data, 'content'):
                                _ss_text = ss_result.data.content or ""
                            self._fallback_embed_screenshot(doc_file, ss, ss_index, _ss_text)
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout on screenshot pass {screenshot_step}")
                        self._fallback_embed_screenshot(doc_file, ss, ss_index)
                    except Exception as e:
                        logger.error(f"Error on screenshot pass {screenshot_step}: {e}")
                        self._fallback_embed_screenshot(doc_file, ss, ss_index)
            
            # GLOBAL SCREENSHOT PASSES: Process screenshots not tied to any component
            for ss in global_screenshots:
                screenshot_step += 1
                current_step += 1
                ss_index = next((i for i, s in enumerate(screenshots, 1) if s.get('path') == ss.get('path')), screenshot_step)
                
                self._update_progress(
                    session_id,
                    "screenshot_analysis",
                    current_step,
                    total_steps,
                    f"Analyzing global screenshot {screenshot_step}/{num_screenshots}: {ss.get('context', 'screenshot')[:50]}"
                )
                
                logger.info(f"Global screenshot pass {screenshot_step}/{num_screenshots}: {ss.get('context', 'No context')[:60]}")
                
                ss_prompt = self._build_screenshot_pass_prompt(
                    screenshot=ss,
                    screenshot_index=ss_index,
                    total_screenshots=num_screenshots,
                    doc_file_path=str(doc_file)
                )
                
                _ss_before = doc_file.read_text(encoding='utf-8')
                try:
                    ss_result = await temp_session.send_and_wait(
                        {
                            "prompt": ss_prompt,
                            "attachments": [{"type": "file", "path": ss.get('ai_path', ss['path'])}]
                        },
                        timeout=config.DOC_GEN_SCREENSHOT_TIMEOUT
                    )
                    _ss_after = doc_file.read_text(encoding='utf-8')
                    if _ss_after != _ss_before:
                        _before_lines = _ss_before.splitlines()
                        _after_lines = _ss_after.splitlines()
                        _added = max(0, len(_after_lines) - len(_before_lines))
                        _removed = max(0, len(_before_lines) - len(_after_lines))
                        _changed = sum(1 for a, b in zip(_before_lines, _after_lines) if a != b)
                        logger.info(f"✓ Global screenshot pass {screenshot_step} complete: +{_added} -{_removed} lines, {_changed} lines changed")
                    else:
                        logger.warning(f"Global screenshot pass {screenshot_step}: no file edits detected, applying fallback embed")
                        _ss_text = ""
                        if ss_result and hasattr(ss_result, 'data') and hasattr(ss_result.data, 'content'):
                            _ss_text = ss_result.data.content or ""
                        self._fallback_embed_screenshot(doc_file, ss, ss_index, _ss_text)
                except asyncio.TimeoutError:
                    logger.error(f"Timeout on global screenshot pass {screenshot_step}")
                    self._fallback_embed_screenshot(doc_file, ss, ss_index)
                except Exception as e:
                    logger.error(f"Error on global screenshot pass {screenshot_step}: {e}")
                    self._fallback_embed_screenshot(doc_file, ss, ss_index)
            
            # SECTION-BY-SECTION PASSES: Dedicated pass for each documentation section
            logger.info(f"Starting {len(doc_sections)} dedicated section passes...")
            
            for sec_idx, (section_id, section_name) in enumerate(doc_sections, 1):
                try:
                    current_step += 1
                    self._update_progress(
                        session_id,
                        "section_generation",
                        current_step,
                        total_steps,
                        f"Generating: {section_name}"
                    )
                    
                    logger.info(f"Section pass {sec_idx}/{len(doc_sections)}: {section_name}...")
                    
                    # Snapshot doc before this section pass
                    _before_lines = doc_file.read_text(encoding='utf-8').splitlines()
                    
                    section_prompt = self._build_section_editing_prompt(
                        section_id=section_id,
                        section_name=section_name,
                        doc_file_path=str(doc_file),
                        selection_context=selection_context,
                        business_section=business_section,
                        files_analyzed=len(critical_files),
                        critical_files=critical_files,
                        non_critical_files=non_critical_files,
                        working_directory=working_directory,
                    )
                    
                    result = await temp_session.send_and_wait(
                        {"prompt": section_prompt},
                        timeout=config.DOC_GEN_SECTION_TIMEOUT
                    )
                    
                    # Compute line diff after section pass
                    _after_lines = doc_file.read_text(encoding='utf-8').splitlines()
                    _added = max(0, len(_after_lines) - len(_before_lines))
                    _removed = max(0, len(_before_lines) - len(_after_lines))
                    _changed = sum(1 for a, b in zip(_before_lines, _after_lines) if a != b)
                    logger.info(f"✓ Section '{section_id}' complete: +{_added} -{_removed} lines, {_changed} lines changed")
                    self._update_progress(
                        session_id, "section_generation", current_step, total_steps,
                        f"✓ {section_name}",
                        diff={"added": _added, "removed": _removed, "changed": _changed}
                    )
                
                except asyncio.TimeoutError:
                    logger.error(f"Timeout generating section '{section_id}', continuing...")
                except Exception as e:
                    logger.error(f"Error generating section '{section_id}': {e}")
            
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
        message: str,
        diff: dict = None
    ):
        """Update progress tracking"""
        progress = {
            "stage": stage,
            "current": current,
            "total": total,
            "message": message,
            "percentage": int((current / total) * 100) if total > 0 else 0,
            "updated_at": datetime.now().isoformat()
        }
        if diff:
            progress["diff"] = diff
        self._generation_progress[session_id] = progress
        logger.info(f"[{session_id}] Progress: {stage} - {current}/{total} - {message}")
    
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
2. **EMBED** the screenshot using `![caption](screenshot_file_path)` with the screenshot's file path
3. **PLACE** each image in the MOST RELEVANT section:
   - App/screen screenshots → `### 3.3 User Interface` or `### 4.2 Features`
   - Flow/automation screenshots → `### 3.4 Logic and Automation`
   - Data/output screenshots → `### 2.2 Data Sources` or `### 8.2 Screenshots or Diagrams`
   - General/overview screenshots → `## 1. Project Overview` or `### 8.2 Screenshots or Diagrams`
4. **ADD A RICH CAPTION** below each image: `*Figure N: <detailed description of what the screenshot shows, including key UI elements and data>*`

**IMPORTANT:** The visual analysis should SIGNIFICANTLY ENRICH the documentation.
Do not just embed images — describe what you see in them to create thorough documentation.
"""
    
    @staticmethod
    def _build_global_screenshots_prompt(
        global_screenshots: Optional[List[Dict[str, Any]]] = None,
        all_screenshots: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Build prompt section for global (non-component) screenshots in the final pass."""
        if not global_screenshots:
            return ""
        
        section = f"\n[IMAGE] **GLOBAL SCREENSHOTS TO EMBED ({len(global_screenshots)}):**\n\n"
        section += "These screenshots are not tied to a specific component. Analyze each one and place it in the most relevant documentation section.\n\n"
        for i, ss in enumerate(global_screenshots, 1):
            context = ss.get('context', 'No context provided')
            section += f"**Global Screenshot {i}:** {context}\n"
        section += "\n**TASK — VISUAL ANALYSIS + EMBEDDING for each global screenshot:**\n\n"
        section += "**A) VISUAL ANALYSIS (enrich the documentation with what you SEE):**\n"
        section += "   - Study each attached image carefully — describe UI layouts, controls, data fields, flow steps\n"
        section += "   - Write detailed observations into the most relevant doc sections\n\n"
        section += "**B) IMAGE EMBEDDING:**\n"
        section += "   1. Determine the best section for placement based on content and context\n"
        section += "   2. Insert `![caption](screenshot_path)` using the screenshot's file path\n"
        section += "   3. Add a rich caption: `*Figure N: <detailed description of what the screenshot shows>*`\n\n"
        return section
    
    @staticmethod
    def _build_screenshot_verification_prompt(
        all_screenshots: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Build a verification prompt to ensure all screenshots were embedded."""
        if not all_screenshots:
            return ""
        
        section = f"\n[CHECK] **SCREENSHOT VERIFICATION ({len(all_screenshots)} total):**\n\n"
        section += "After completing all other tasks, verify that EVERY screenshot below appears in the documentation.\n"
        section += "Search the document for `![` markers to confirm embedding.\n\n"
        for i, ss in enumerate(all_screenshots, 1):
            context = ss.get('context', 'No context provided')
            comp = ss.get('component_path', 'Global')
            section += f"  {i}. \"{context}\" (component: {comp or 'Global'})\n"
        section += f"\nIf any screenshot is MISSING from the document, embed it now using `replace_string_in_file`.\n"
        section += "Place missing screenshots in `### 8.2 Screenshots or Diagrams` as a fallback.\n\n"
        return section
    
    @staticmethod
    def _fallback_embed_screenshot(
        doc_file: Path,
        screenshot: Dict[str, Any],
        screenshot_index: int,
        ai_description: str = ""
    ) -> None:
        """Manually embed a screenshot into the doc when Copilot didn't edit the file."""
        context = screenshot.get('context', 'Screenshot')
        img_path = screenshot.get('path', '')

        # Build the embed block — no sub-heading, inline with existing section prose
        embed_block = "\n"
        if ai_description and len(ai_description.strip()) > 50:
            desc = ai_description.strip()[:800]
            if len(ai_description.strip()) > 800:
                desc += "..."
            embed_block += f"{desc}\n\n"
        embed_block += f"![{context}]({img_path})\n"
        embed_block += f"*Figure {screenshot_index}: {context}*\n"

        doc_content = doc_file.read_text(encoding='utf-8')
        section_marker = "### 8.2 Screenshots or Diagrams"
        if section_marker in doc_content:
            insert_pos = doc_content.index(section_marker) + len(section_marker)
            next_nl = doc_content.find('\n', insert_pos)
            if next_nl != -1:
                new_content = doc_content[:next_nl + 1] + embed_block + doc_content[next_nl + 1:]
            else:
                new_content = doc_content + embed_block
        else:
            new_content = doc_content + f"\n\n### 8.2 Screenshots or Diagrams\n{embed_block}"
        doc_file.write_text(new_content, encoding='utf-8')
        logger.info(f"✓ Fallback embed applied for screenshot {screenshot_index}: {context[:60]}")

    def _build_screenshot_pass_prompt(
        self,
        screenshot: Dict[str, Any],
        screenshot_index: int,
        total_screenshots: int,
        doc_file_path: str,
        component_context: str = ""
    ) -> str:
        """Build prompt for a dedicated single-screenshot analysis pass.
        
        Each screenshot gets its own AI pass where the model:
        1. Looks at the image with full visual attention
        2. Writes documentation based on what it sees
        3. Inserts the image reference in the most relevant location
        """
        context = screenshot.get('context', 'No context provided')
        comp = screenshot.get('component_path', 'Global')
        
        component_hint = ""
        if component_context:
            component_hint = f"\nThis screenshot is associated with component: **{component_context}**\n"
            component_hint += "Focus your analysis on how this image relates to that component's documentation.\n"
        else:
            component_hint = "\nThis is a **global screenshot** not tied to a specific component.\n"
            component_hint += "Place it in the most relevant section based on what you see in the image.\n"
        
        # Section placement hints based on component context
        if component_context:
            ctx_lower = component_context.lower()
            if '.fx.yaml' in ctx_lower or 'screen' in ctx_lower or 'canvasapp' in ctx_lower:
                section_hint = """**LIKELY RELEVANT SECTIONS:**
- `### 3.3 User Interface` — describe screen layout, controls, navigation visible in the screenshot
- `### 4.2 Features` — describe user-facing features shown
- `### 8.2 Screenshots or Diagrams` — fallback if no better fit"""
            elif 'desktop' in ctx_lower or 'pad' in ctx_lower or 'robin' in ctx_lower:
                section_hint = """**LIKELY RELEVANT SECTIONS:**
- `### 3.4 Logic and Automation` — describe desktop automation steps, UI element interactions, browser automation visible
- `### 3.3 User Interface` — if showing the desktop app UI being automated
- `### 8.2 Screenshots or Diagrams` — fallback if no better fit"""
            elif 'bot' in ctx_lower or 'copilot' in ctx_lower or 'agent' in ctx_lower or 'topic' in ctx_lower:
                section_hint = """**LIKELY RELEVANT SECTIONS:**
- `### 3.4 Logic and Automation` — describe agent topics, conversation flow, adaptive cards visible
- `### 3.3 User Interface` — if showing the agent's chat interface or adaptive cards
- `### 8.2 Screenshots or Diagrams` — fallback if no better fit"""
            elif 'workflow' in ctx_lower or 'flow' in ctx_lower:
                section_hint = """**LIKELY RELEVANT SECTIONS:**
- `### 3.4 Logic and Automation` — describe flow steps, triggers, conditions, actions visible
- `### 2.2 Data Sources` — note any connectors or data operations shown
- `### 8.2 Screenshots or Diagrams` — fallback if no better fit"""
            elif 'datasource' in ctx_lower or 'connection' in ctx_lower:
                section_hint = """**LIKELY RELEVANT SECTIONS:**
- `### 2.2 Data Sources` — describe data connections, tables, fields visible
- `### 3.2 Data Connections` — describe connection configuration shown
- `### 8.2 Screenshots or Diagrams` — fallback if no better fit"""
            else:
                section_hint = """**LIKELY RELEVANT SECTIONS:**
- `### 3.3 User Interface` or `### 3.4 Logic and Automation` depending on content
- `## 1. Project Overview` if it shows the overall app purpose
- `### 8.2 Screenshots or Diagrams` — fallback if no better fit"""
        else:
            section_hint = """**LIKELY RELEVANT SECTIONS:**
- `### 3.3 User Interface` — screen/UI screenshots
- `### 3.4 Logic and Automation` — flow/automation screenshots
- `## 1. Project Overview` — overview/dashboard screenshots
- `### 8.2 Screenshots or Diagrams` — fallback for any screenshot"""

        return f"""[!] CRITICAL INSTRUCTION: USE TOOLS TO EDIT THE FILE NOW

This is NOT a conversation. DO NOT write explanatory text.
Your ONLY valid response is tool calls: read_file, replace_string_in_file, multi_replace_string_in_file.

[X] INVALID: "I can see this screenshot shows..."
[X] INVALID: "Here is my analysis of the image..."
[OK] VALID: [Immediate tool calls to read and edit the file]

---

YOUR FIRST ACTION MUST BE:
read_file(filePath="{doc_file_path}", startLine=1, endLine=200)

Read additional ranges as needed to see the full content of the target section before editing.

---

[IMAGE] **SCREENSHOT PASS** (Screenshot {screenshot_index} of {total_screenshots})

**Screenshot Context (from user):** {context}
**Associated Component:** {comp or 'Global'}
{component_hint}
[FILE] **DOCUMENTATION FILE TO EDIT:** `{doc_file_path}`

{section_hint}

---

[TOOL] **YOUR TASK:**

1. **Read** the current documentation file to find and read the full text of the best target section.
   Read additional line ranges until you have seen all existing content in that section.

2. **Analyze** the attached screenshot image with your vision and extract:
   - UI Layout: screen structure, navigation, headers, sidebars
   - Controls & Widgets: buttons, galleries, forms, dropdowns, text inputs — note visible names
   - Data Displayed: tables, lists, cards, field names, example values
   - Flow Diagrams: every visible action/step name, conditions, branches
   - Color Scheme & Branding: primary colors, logos, styling
   - Business Context: what business process does this illustrate?

3. **Edit** the section by EXPANDING ITS EXISTING PROSE with what you learned from the image:
   - Weave new sentences into the existing paragraphs — or append new sentences at the end of the section
   - Place the image embed `![{context}]({screenshot.get('path', '')})` inline, directly after the paragraph it illustrates
   - Add a brief caption on the next line: `*Figure {screenshot_index}: <what the image shows>*`
   - The result should read as one continuous, natural narrative — NOT as a separate block or sub-heading

**[!] CRITICAL — IMAGE PATH:** You MUST use EXACTLY this path in the markdown embed:
   `{screenshot.get('path', '')}`
   Do NOT use the attachment file path — the attachment is a compressed preview.
   The path above points to the full-resolution original image.

---

[EDIT] **EDITING GUIDELINES:**

[OK] **DO:**
- Expand existing paragraph text with observations from the image (UI elements, flow steps, data shown)
- Place `![{context}]({screenshot.get('path', '')})` immediately after the paragraph it supports
- Use `replace_string_in_file` — include 3-5 lines of unchanged context before/after
- Read multiple line ranges to see the full section before editing

[STOP] **DON'T:**
- **DON'T create a new sub-heading** like `#### Screenshot N:` or `#### Figure N:` — images live inline within sections
- **DON'T append a standalone block** at the end of the file — edit the most relevant existing section
- Don't put everything in Section 8.2 — expand the best-fit section with the visual detail
- Don't skip the image embed — `![{context}]({screenshot.get('path', '')})` must appear in the doc
- **NEVER use a path containing `_optimized`** — always use the exact path: `{screenshot.get('path', '')}`
- Don't duplicate content already in the doc
- Don't write text responses — only tool calls

NO TEXT RESPONSES — ONLY TOOL CALLS."""

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
        all_screenshots: Optional[List[Dict[str, Any]]] = None
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

{self._build_global_screenshots_prompt(global_screenshots, all_screenshots=all_screenshots)}

{self._build_screenshot_verification_prompt(all_screenshots)}

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
    
    def _build_section_editing_prompt(
        self,
        section_id: str,
        section_name: str,
        doc_file_path: str,
        selection_context: str,
        business_section: str,
        files_analyzed: int,
        critical_files: List[tuple],
        non_critical_files: List[tuple],
        working_directory: Path,
    ) -> str:
        """Build a focused prompt for editing one specific documentation section."""
        
        # Build file inventory (only for sections that benefit from exploration)
        files_inventory = ""
        if section_id in ("technical_specs", "development", "overview"):
            files_inventory = self._build_files_inventory(
                critical_files, non_critical_files, working_directory
            )
        
        section_instructions = {
            "frontmatter": f"""[TARGET] **SECTION: Frontmatter & Project Information**

Edit the top of `{doc_file_path}` to fill in:

1. **Project Name** — extract from manifest data already in the doc, or from app metadata
2. **Version** — use version from manifest or "1.0.0"
3. **Last Updated** — today's date
4. **Author(s)** — "Auto-generated Documentation"
5. **Status** — "Documented"
6. **Purpose** — synthesize a 1-2 sentence purpose from components analyzed and business context

Read the file first to find manifest/app data already written by earlier passes.
Only edit the `## Project Information` block — do NOT touch other sections.""",

            "overview": f"""[TARGET] **SECTION 1: Project Overview**

Edit `{doc_file_path}` to fill Section 1 — Project Overview:

1. Read the current doc to see what components/screens/flows were documented
2. Write 2-3 paragraphs in `## 1. Project Overview` synthesizing:
   - What this Power Platform app does (high-level)
   - Main business purposes and goals
   - Key capabilities identified in earlier passes
3. Fill the sub-fields:
   - **Description:** 1-2 sentence summary
   - **Objectives:** Main goals from components and business context
   - **Scope:** Count screens, flows, data sources from what's in the doc
   - **Target Audience:** If identifiable, otherwise "End users"
   - **Stakeholders:** If identifiable, otherwise placeholder

{business_section}

Only edit Section 1 — do NOT touch other sections.""",

            "technical_specs": f"""[TARGET] **SECTION 2: Technical Specifications (2.1, 2.2, 2.3)**

Edit `{doc_file_path}` to complete Section 2 — Technical Specifications:

1. **Read the current doc** to see what's already filled from per-file passes
2. **EXPLORE additional files** to enrich data sources and connections:
{files_inventory}
3. Fill/update these subsections:
   - **2.1 Platform Overview:** App type, environment, integrations
   - **2.2 Data Sources:** Explore DataSource/Connection files listed above to find:
     * All data connections (SharePoint, SQL, APIs, Dataverse)
     * Connection authentication (OAuth, service principal)
     * Data security and permissions
   - **2.3 Technology Stack:** Components, custom code, expressions count

Use `read_file` to explore the additional files above when helpful.
Use `replace_string_in_file` to update Section 2.

Only edit Section 2 — do NOT touch other sections.""",

            "development": f"""[TARGET] **SECTION 3: Development Details (3.1, 3.2, 3.3, 3.4)**

Edit `{doc_file_path}` to gap-fill Section 3 — Development Details:

1. **Read the current doc** — per-file passes already populated much of Section 3
2. **Fill gaps** in these subsections:
   - **3.1 Application Setup:** Environment requirements, setup instructions
   - **3.2 Data Connections:** Connector configs, security settings (explore Connection files if needed)
   - **3.3 User Interface:** Ensure all screens listed, add navigation flow summary
   - **3.4 Logic and Automation:** Ensure all formulas and flows complete
3. **De-duplicate** — if the same screen or formula appears twice, merge entries
4. Remove any remaining placeholder text that should have real data

{files_inventory}

Only edit Section 3 — do NOT touch other sections.""",

            "usage": f"""[TARGET] **SECTION 4: Usage Instructions**

Edit `{doc_file_path}` to fill Section 4 — Usage Instructions:

1. **Read the current doc** to understand what screens/features exist
2. Fill these subsections:
   - **4.1 How to Access the App:** URL or access method, device compatibility
   - **4.2 Features:** List 3-5 key features based on documented screens and flows
   - **4.3 User Roles:** Role-based permissions if identifiable, otherwise standard placeholder

Base feature descriptions on the screens and logic already documented in Section 3.

Only edit Section 4 — do NOT touch other sections.""",

            "maintenance": f"""[TARGET] **SECTIONS 5, 6, 7: Troubleshooting, Maintenance, Roadmap**

Edit `{doc_file_path}` to fill Sections 5-7:

1. **Section 5 — Troubleshooting and FAQs:**
   - 5.1 Common Issues: Add relevant items if error handling was found in code, otherwise placeholder
   - 5.2 Error Messages: Document any error handling patterns found in the analyses
   - 5.3 Support Contact: Standard placeholder

2. **Section 6 — Maintenance:**
   - 6.1 Scheduled Updates: Placeholder
   - 6.2 Version Control: Include version if found in manifest
   - 6.3 Backup Strategy: Standard recommendation
   - 6.4 Performance Monitoring: Standard recommendation

3. **Section 7 — Roadmap:**
   - Placeholder for future enhancements

Replace template placeholder text with specific or standard text. Don't leave raw template instructions.

Only edit Sections 5-7 — do NOT touch other sections.""",

            "appendices": f"""[TARGET] **SECTION 8: Appendices + Table of Contents**

Edit `{doc_file_path}` to complete Section 8 and add Table of Contents:

**Part A — Section 8 Appendices:**
1. **8.1 Glossary:** Add definitions for technical terms found in the documentation
   (Power Fx, Canvas App, Power Automate, Dataverse, plus any domain-specific terms)
2. **8.2 Screenshots or Diagrams:** If screenshots were embedded earlier, leave as-is.
   Otherwise: "*Visual documentation available upon request.*"
3. **8.3 Custom Components or Code:** List any custom components found, or placeholder

**Part B — Table of Contents:**

Read the full document to identify all section headers present, then generate a
Table of Contents in the `## Table of Contents` section with markdown links:

```
## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technical Specifications](#2-technical-specifications)
   - [2.1 Platform Overview](#21-platform-overview)
   - [2.2 Data Sources](#22-data-sources)
   - [2.3 Technology Stack](#23-technology-stack)
3. [Development Details](#3-development-details)
   ...etc based on actual sections present
```

**Part C — Final cleanup:**
- Replace any remaining raw template instructions with actual content or "*Not available*"
- Remove any duplicate entries
- Ensure consistent markdown formatting

Edit Sections 8, Table of Contents, and do final cleanup only.""",
        }
        
        instruction = section_instructions.get(section_id, f"Complete the {section_name} section of the documentation.")
        
        return f"""[!] CRITICAL: SECTION EDITING TASK — USE TOOLS ONLY

DO NOT write text. USE read_file and replace_string_in_file to edit `{doc_file_path}`.

---

{selection_context}

**DOCUMENTATION FILE:** `{doc_file_path}`
**You have analyzed {files_analyzed} files in previous passes.**

---

{instruction}

---

[EDIT] **GUIDELINES:**

[OK] **DO:**
- Read the file first with read_file to see current state
- Use replace_string_in_file for precise edits
- Include 3-5 lines of context in oldString for accurate matching
- Preserve content from other sections

[STOP] **DON'T:**
- Don't write conversational text — only use tools
- Don't edit sections outside your assigned scope
- Don't remove content added by earlier passes
- Don't rewrite the entire file

[START] **BEGIN IMMEDIATELY WITH TOOL CALLS.**"""

    def _build_files_inventory(
        self,
        critical_files: List[tuple],
        non_critical_files: List[tuple],
        working_directory: Path,
    ) -> str:
        """Build a file inventory string for section prompts that need file exploration."""
        inventory = "\n**Additional Files Available for Exploration:**\n"
        
        if not non_critical_files:
            inventory += "  (No additional files available)\n"
            return inventory
        
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
            inventory += "\n  **Data Sources:**\n"
            for f in data_sources[:10]:
                inventory += f"    - {f}\n"
            if len(data_sources) > 10:
                inventory += f"    ... and {len(data_sources) - 10} more\n"
        
        if connections:
            inventory += "\n  **Connections:**\n"
            for f in connections[:10]:
                inventory += f"    - {f}\n"
            if len(connections) > 10:
                inventory += f"    ... and {len(connections) - 10} more\n"
        
        if other_files:
            inventory += "\n  **Other Supporting Files:**\n"
            for f in other_files[:15]:
                inventory += f"    - {f}\n"
            if len(other_files) > 15:
                inventory += f"    ... and {len(other_files) - 15} more\n"
        
        inventory += f"\n**Working Directory:** `{working_directory}`\n"
        inventory += "**Tools:** read_file, grep_search, list_dir available for exploration.\n"
        
        return inventory

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
    
    async def generate_user_guide(
        self,
        session_id: str,
        working_directory: Path,
        source_markdown: str,
        template_path: Path,
        images_dir: Optional[Path] = None,
        business_context: str = "",
    ) -> str:
        """
        Generate a user guide by transforming technical documentation into
        end-user-friendly content using the UserGuideTemplate.

        Approach: duplicate the template and edit it in-place via Copilot,
        preserving the template's structure, section ordering, and formatting.

        Args:
            session_id: Session identifier for progress tracking
            working_directory: Path where the user guide file will be created
            source_markdown: Full text of the source technical documentation
            template_path: Path to UserGuideTemplate.md
            images_dir: Path to images directory (copied alongside the guide)
            business_context: Optional user-provided business context

        Returns:
            Generated user guide markdown content
        """
        if not self.client:
            raise RuntimeError("DocumentationGenerator not initialized")

        # Define user guide sections for per-section refinement passes
        ug_sections = [
            ("header_welcome", "App Header & Welcome Description"),
            ("glossary", "Glossary"),
            ("capabilities", "What You Can Do & Getting Started"),
            ("capability_sections", "Per-Capability Detailed Sections"),
            ("tips_faq", "Tips for Success & Common Questions"),
            ("support_limits", "Getting Help, Known Limitations & Quick Reference"),
            ("version_info", "Version Information & Final Cleanup"),
        ]

        # Pass 1 (bulk population) + per-section passes
        total_steps = 1 + len(ug_sections)

        try:
            self._update_progress(
                session_id, "initializing", 0, total_steps,
                "Preparing user guide template"
            )

            # 1. Copy template to working directory
            import shutil
            doc_file = working_directory / f"{session_id}_UserGuide.md"
            shutil.copy(template_path, doc_file)
            logger.info(f"Created user guide template copy: {doc_file}")

            # 2. Copy images directory into working directory so Copilot and
            #    output both have access to the images
            if images_dir and images_dir.exists():
                dest_images = working_directory / "images"
                if not dest_images.exists():
                    shutil.copytree(images_dir, dest_images)
                    logger.info(f"Copied {sum(1 for _ in dest_images.iterdir())} images to {dest_images}")

            # 3. Create isolated Copilot session
            session_config = {
                "model": config.COPILOT_MODEL,
                "working_directory": str(working_directory),
                "streaming": False,
                "on_permission_request": lambda req, ctx: (
                    PermissionRequestResult(kind="denied-by-rules")
                    if req.kind.value == "shell"
                    else PermissionRequestResult(kind="approved")
                ),
                "system_message": {
                    "mode": "append",
                    "content": self._build_user_guide_system_prompt(
                        str(doc_file), source_markdown
                    )
                }
            }

            temp_session = await self.client.create_session(session_config)
            logger.info(f"Created user guide editing session for {session_id}")

            business_section = ""
            if business_context:
                business_section = f"\n\n**USER BUSINESS CONTEXT:**\n{business_context}\n"

            current_step = 0

            # ── PASS 1: Bulk population ──────────────────────────
            current_step += 1
            self._update_progress(
                session_id, "transforming", current_step, total_steps,
                "Transforming technical docs into user guide (bulk pass)"
            )

            _before_lines = doc_file.read_text(encoding="utf-8").splitlines()

            bulk_prompt = self._build_user_guide_bulk_prompt(
                doc_file_path=str(doc_file),
                source_markdown=source_markdown,
                business_section=business_section,
                images_dir=str(working_directory / "images") if images_dir else None,
            )

            await temp_session.send_and_wait(
                {"prompt": bulk_prompt},
                timeout=config.DOC_GEN_SECTION_TIMEOUT * 2  # longer for bulk
            )

            _after_lines = doc_file.read_text(encoding="utf-8").splitlines()
            _added = max(0, len(_after_lines) - len(_before_lines))
            _changed = sum(1 for a, b in zip(_before_lines, _after_lines) if a != b)
            logger.info(f"✓ Bulk pass complete: +{_added} lines, {_changed} lines changed")
            self._update_progress(
                session_id, "transforming", current_step, total_steps,
                "✓ Bulk population complete",
                diff={"added": _added, "removed": 0, "changed": _changed}
            )

            # ── PASS 2: Per-section refinement ───────────────────
            for sec_idx, (section_id, section_name) in enumerate(ug_sections, 1):
                try:
                    current_step += 1
                    self._update_progress(
                        session_id, "refining", current_step, total_steps,
                        f"Refining: {section_name}"
                    )

                    logger.info(f"Section pass {sec_idx}/{len(ug_sections)}: {section_name}...")
                    _before_lines = doc_file.read_text(encoding="utf-8").splitlines()

                    section_prompt = self._build_user_guide_section_prompt(
                        section_id=section_id,
                        section_name=section_name,
                        doc_file_path=str(doc_file),
                        source_markdown=source_markdown,
                        business_section=business_section,
                        images_dir=str(working_directory / "images") if images_dir else None,
                    )

                    await temp_session.send_and_wait(
                        {"prompt": section_prompt},
                        timeout=config.DOC_GEN_SECTION_TIMEOUT
                    )

                    _after_lines = doc_file.read_text(encoding="utf-8").splitlines()
                    _added = max(0, len(_after_lines) - len(_before_lines))
                    _removed = max(0, len(_before_lines) - len(_after_lines))
                    _changed = sum(1 for a, b in zip(_before_lines, _after_lines) if a != b)
                    logger.info(
                        f"✓ Section '{section_id}' complete: +{_added} -{_removed} lines, {_changed} changed"
                    )
                    self._update_progress(
                        session_id, "refining", current_step, total_steps,
                        f"✓ {section_name}",
                        diff={"added": _added, "removed": _removed, "changed": _changed}
                    )

                except asyncio.TimeoutError:
                    logger.error(f"Timeout refining section '{section_id}', continuing...")
                except Exception as e:
                    logger.error(f"Error refining section '{section_id}': {e}")

            # ── Post-processing ──────────────────────────────────
            documentation = doc_file.read_text(encoding="utf-8")

            # Fix any absolute image paths → relative images/ paths
            documentation = self._fix_user_guide_image_paths(
                documentation, working_directory
            )
            doc_file.write_text(documentation, encoding="utf-8")

            logger.info(f"✓ User guide ready: {len(documentation)} chars")

            # Clean up session
            try:
                if hasattr(temp_session, "close"):
                    await temp_session.close()
                logger.info("User guide editing session closed")
            except Exception as e:
                logger.warning(f"Error closing session: {e}")

            self._update_progress(
                session_id, "complete", total_steps, total_steps,
                "User guide generation complete"
            )
            return documentation

        except Exception as e:
            logger.exception(f"Error generating user guide for {session_id}")
            self._update_progress(
                session_id, "error", 0, total_steps,
                f"Error: {str(e)}"
            )
            raise

    # ── User Guide prompt builders ────────────────────────────────

    def _build_user_guide_system_prompt(
        self, doc_file_path: str, source_markdown: str
    ) -> str:
        """System prompt for user guide transformation sessions."""

        # Truncate source to avoid exceeding context limits while keeping as much as possible
        max_source_chars = 80000
        truncated = source_markdown[:max_source_chars]
        if len(source_markdown) > max_source_chars:
            truncated += "\n\n... [source documentation truncated] ..."

        return f"""[!] CRITICAL: This is a FILE EDITING task, not a conversation.

YOU MUST USE TOOLS TO EDIT THE FILE. DO NOT WRITE TEXT RESPONSES.

**USER GUIDE FILE:** `{doc_file_path}`

**YOUR ROLE:** Expert technical writer transforming Power Platform technical
documentation into an end-user guide.

**AUDIENCE:** Non-technical business users who use the app daily.
They do NOT care about formulas, Dataverse schemas, or deployment details.
They care about: what the app does, how to use it step-by-step, what to do when
something goes wrong, and where to get help.

**WRITING STYLE:**
- Simple, friendly, direct language — no jargon
- Second person ("you") and active voice
- Short sentences and paragraphs
- Step-by-step numbered instructions for tasks
- "How to…" framing for capability sections
- Include tips, warnings, and notes where helpful

**IMAGE HANDLING — CRITICAL:**
The source technical documentation references images in `images/` directory.
You MUST preserve and re-embed ALL relevant image references from the source
docs into the user guide. Use relative paths: `![caption](images/filename.ext)`
Screenshots help users see exactly what to expect — a user guide without
screenshots is incomplete.

When embedding images:
- Place each screenshot RIGHT AFTER the step or description it illustrates
- Write a brief, user-friendly caption
- Use the EXACT filenames from the source documentation

**PROHIBITED ACTIONS:**
[X] DO NOT write conversational responses
[X] DO NOT invent features not mentioned in the source documentation
[X] DO NOT include technical implementation details (formulas, code, schemas)
[X] DO NOT leave template placeholders like {{CAPABILITY_1}} in the output

**REQUIRED ACTIONS:**
[OK] USE read_file to check the current template state
[OK] USE replace_string_in_file to edit sections in place
[OK] Rewrite technical content into user-friendly language
[OK] Preserve the template's section structure

**SOURCE TECHNICAL DOCUMENTATION:**
(Use this as your knowledge base — rewrite for end users)

---
{truncated}
---

[TOOLS] Available: read_file, replace_string_in_file, multi_replace_string_in_file, grep_search
"""

    def _build_user_guide_bulk_prompt(
        self,
        doc_file_path: str,
        source_markdown: str,
        business_section: str = "",
        images_dir: Optional[str] = None,
    ) -> str:
        """Prompt for the bulk population pass — fill ALL template placeholders."""

        images_hint = ""
        if images_dir:
            images_hint = f"""
**IMAGES DIRECTORY:** `{images_dir}`
List this directory to see available screenshots. Embed them using `![caption](images/filename)`.
"""

        return f"""[!] CRITICAL INSTRUCTION: USE TOOLS TO EDIT THE FILE NOW

This is NOT a conversation. Your ONLY valid response is tool calls.

YOUR FIRST ACTION MUST BE:
read_file(filePath="{doc_file_path}", startLine=1, endLine=200)

---

[TARGET] **BULK POPULATION — Fill the entire User Guide template**

{business_section}
{images_hint}

**DOCUMENTATION FILE TO EDIT:** `{doc_file_path}`

**YOUR TASK:**

1. **Read** the full user guide template file
2. **Analyze** the source technical documentation (in your system context) and extract:
   - App name, purpose, and target audience
   - User-facing features/capabilities (screens, buttons, workflows users interact with)
   - How to access the app (URL, login method, device support)
   - Step-by-step usage instructions for each feature
   - Common issues and their solutions
   - Screenshots and their contexts
3. **Replace** ALL template placeholders with real content:
   - `{{APP_NAME}}` → actual app name
   - `{{APP_WELCOME_DESCRIPTION}}` → friendly 2-4 sentence welcome
   - `{{CAPABILITY_1}}`, `{{CAPABILITY_2}}`, etc. → real feature names
   - Every `{{PLACEHOLDER}}` must be replaced with actual content
4. **Create** one section per user-facing capability:
   - Each section: heading, description, step-by-step instructions, screenshot embed, tip
   - Remove the generic `## {{CAPABILITY_N}}` blocks and replace with real capability sections
5. **Embed screenshots** from the source docs into relevant sections

**CRITICAL RULES:**
- Replace EVERY `{{...}}` placeholder — none should remain
- Write for non-technical users — NO code, NO formulas, NO schemas
- If a capability has steps, use numbered lists (1. Click... 2. Select... 3. ...)
- If the source docs have images, embed them in the most relevant section
- Keep the template's overall structure (Glossary → Getting Started → Capabilities → Tips → FAQ → Help)
- If information isn't available in the source docs, write a reasonable placeholder based on context

---

[START] BEGIN WITH TOOL USAGE IMMEDIATELY."""

    def _build_user_guide_section_prompt(
        self,
        section_id: str,
        section_name: str,
        doc_file_path: str,
        source_markdown: str,
        business_section: str = "",
        images_dir: Optional[str] = None,
    ) -> str:
        """Build a focused prompt for refining one user guide section."""

        images_hint = ""
        if images_dir:
            images_hint = f"\n**IMAGES:** List `{images_dir}` for available screenshots. Embed as `![caption](images/filename)`.\n"

        section_instructions = {
            "header_welcome": f"""[TARGET] **App Header & Welcome Description**

Edit the TOP of `{doc_file_path}`:

1. Ensure `# {{APP_NAME}}` is replaced with the actual app name
2. Write a warm, clear 2-4 sentence welcome: what the app does, who it's for, what problem it solves
3. Add an appropriate `> **Note:**` if the app has important scope boundaries
4. Remove any remaining template instruction comments (lines starting with `> *`)

Only edit the header and welcome sections — do NOT touch other sections.""",

            "glossary": f"""[TARGET] **Glossary**

Edit the Glossary section of `{doc_file_path}`:

1. Extract business terms and acronyms from the source technical documentation
2. Define each in plain language (not technical definitions)
3. Remove template placeholder rows (`{{TERM_1}}`, etc.)
4. If no special terms exist, replace the section content with: "*No special terminology is needed to use this app.*"
5. Remove template instruction comments

Only edit the Glossary section.""",

            "capabilities": f"""[TARGET] **What You Can Do & Getting Started**

Edit `{doc_file_path}` — the "What You Can Do" and "Getting Started" sections:

1. **What You Can Do:** Create a bullet list of user-facing capabilities derived from
   the technical docs' features/screens/flows. Write them as user actions:
   "View and filter records", "Export data to Excel", "Create new entries", etc.
2. **Getting Started:** Fill in:
   - How to open the app (URL, navigation path, or launch method)
   - Sign-in requirements
   - Supported devices
   - First-time setup or landing screen description
3. Embed a screenshot of the home/landing screen if available
4. Remove all `{{...}}` placeholders and template comments

Only edit these two sections.""",

            "capability_sections": f"""[TARGET] **Per-Capability Detailed Sections**

Edit `{doc_file_path}` — the individual capability sections:

1. For each capability listed in "What You Can Do", ensure there is a dedicated `## ` section
2. Each section must include:
   - A brief description of what the user can do and when they'd use it
   - **Step-by-step numbered instructions** (1. Click... 2. Select... 3. ...)
   - A screenshot embed if available: `![caption](images/filename)`
   - A practical tip if relevant
3. Remove template placeholders (`{{CAPABILITY_1_DESCRIPTION}}`, etc.)
4. Remove any generic `## {{CAPABILITY_N}}` blocks that weren't populated
5. If the source docs mention additional features not yet covered, add new sections for them
{images_hint}
Only edit the capability sections (between "Getting Started" and "Tips for Success").""",

            "tips_faq": f"""[TARGET] **Tips for Success & Common Questions**

Edit `{doc_file_path}` — Tips and FAQ sections:

1. **Tips for Success:**
   - Group practical advice by theme (e.g., "Data Entry", "Navigation", "Troubleshooting")
   - 2-4 bullets per theme
   - Derive from technical docs' best practices, error handling, and usage patterns
   - Remove `{{TIPS_THEME_1}}` and similar placeholders
2. **Common Questions:**
   - Write 3-6 Q&A pairs addressing the most likely user confusion points
   - Derive from technical docs' troubleshooting, known issues, and FAQs
   - Format: `**Q:** question` / `A: answer`
   - Remove `{{QUESTION_1}}` and similar placeholders

Only edit Tips for Success and Common Questions sections.""",

            "support_limits": f"""[TARGET] **Getting Help, Known Limitations & Quick Reference**

Edit `{doc_file_path}` — support, limitations, and quick reference sections:

1. **Getting Help:** Fill in the escalation path (3 steps).
   If source docs mention support contacts, use them. Otherwise write reasonable defaults.
2. **Known Limitations:** List any confirmed bugs, edge cases, or missing capabilities
   found in the source docs, with workarounds. If none, write:
   "*No known limitations at this time.*"
3. **Quick Reference:** Build the "I want to..." table:
   - One row per common task (open app, filter, export, create record, etc.)
   - "How to do it" column: brief instruction
   - Derive from the capability sections already written
4. Remove all `{{...}}` placeholders

Only edit these three sections.""",

            "version_info": f"""[TARGET] **Version Information & Final Cleanup**

Edit `{doc_file_path}` — final section and whole-document cleanup:

1. **Version Information:** Fill in App name, Document Version ("1.0"), Last Updated date
2. **Final Cleanup — scan the ENTIRE document:**
   - Remove ALL remaining `{{...}}` placeholders — replace with real content or remove the line
   - Remove ALL template instruction comments (lines like `> *Define terms...`)
   - Ensure no duplicate sections
   - Ensure consistent heading levels (# for title, ## for main sections, ### for sub)
   - Verify all image references use `images/filename` relative paths
   - Check that the document reads naturally from top to bottom

Read the full file and fix any remaining issues.""",
        }

        instruction = section_instructions.get(
            section_id,
            f"Complete the {section_name} section of the user guide."
        )

        return f"""[!] CRITICAL: SECTION EDITING TASK — USE TOOLS ONLY

DO NOT write text. USE read_file and replace_string_in_file to edit `{doc_file_path}`.

---

{business_section}

**USER GUIDE FILE:** `{doc_file_path}`

---

{instruction}

---

[EDIT] **GUIDELINES:**

[OK] Read the file first with read_file
[OK] Use replace_string_in_file for precise edits — include 3-5 lines of context
[OK] Preserve content from other sections
[OK] Write for non-technical end users

[STOP] Don't write conversational text — only use tools
[STOP] Don't edit sections outside your assigned scope
[STOP] Don't include code, formulas, or technical implementation details
[STOP] Don't leave any {{...}} placeholders in the sections you edit

BEGIN WITH TOOL USAGE IMMEDIATELY."""

    @staticmethod
    def _fix_user_guide_image_paths(
        markdown: str, working_directory: Path
    ) -> str:
        """Normalize image paths in the user guide to relative images/ paths."""
        import re as _re

        # Remove _optimized suffixes
        markdown = _re.sub(
            r'_optimized(?=\.(png|jpe?g|gif|webp))',
            '', markdown, flags=_re.IGNORECASE
        )

        # Replace any absolute paths containing the working directory with relative
        wd_str = str(working_directory).replace('\\', '/')
        markdown = markdown.replace(wd_str + '/images/', 'images/')
        markdown = markdown.replace(wd_str + '\\images\\', 'images/')

        # Also handle Windows-style absolute paths
        wd_win = str(working_directory).replace('/', '\\')
        markdown = markdown.replace(wd_win + '\\images\\', 'images/')

        return markdown

    # ========================================================================
    # QA TEST SCRIPTS GENERATION
    # ========================================================================

    async def generate_test_scripts(
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
        Generate QA test scripts by incrementally editing the TestScriptsTemplate.
        Follows the same incremental editing pattern as generate_documentation().
        """
        if not self.client:
            raise RuntimeError("DocumentationGenerator not initialized")

        num_screenshots = len(screenshots) if screenshots else 0

        qa_sections = [
            ("test_plan_info", "Test Plan Information"),
            ("test_environment", "Test Environment & Data"),
            ("canvas_tests", "Canvas App Test Scenarios"),
            ("flow_tests", "Power Automate Flow Test Scenarios"),
            ("integration_tests", "Integration Test Scenarios"),
            ("edge_boundary", "Edge Case & Boundary Tests"),
            ("perf_security_a11y", "Performance, Security & Accessibility"),
            ("regression_checklist", "Regression Checklist & Cleanup"),
        ]
        total_steps = len(critical_files) + num_screenshots + len(qa_sections)

        try:
            self._update_progress(
                session_id, "initializing", 0, total_steps,
                "Creating test scripts template and session"
            )

            doc_file = working_directory / f"{session_id}_TestScripts.md"
            import shutil
            shutil.copy(template_path, doc_file)
            logger.info(f"Created test scripts template copy: {doc_file}")

            session_config = {
                "model": config.COPILOT_MODEL,
                "working_directory": str(working_directory.parent),
                "streaming": False,
                "on_permission_request": lambda req, ctx: (
                    PermissionRequestResult(kind="denied-by-rules")
                    if req.kind.value == "shell"
                    else PermissionRequestResult(kind="approved")
                ),
                "system_message": {
                    "mode": "append",
                    "content": self._build_qa_system_prompt(
                        str(doc_file), screenshots=screenshots
                    )
                }
            }

            temp_session = await self.client.create_session(session_config)
            logger.info(f"Created QA test scripts session for {session_id}")

            business_section = ""
            if business_context:
                business_section = f"\n\n**USER BUSINESS CONTEXT:**\n{business_context}\n"

            screenshots = screenshots or []
            screenshots_by_component = {}
            global_screenshots = []
            for ss in screenshots:
                cp = ss.get('component_path')
                if cp:
                    screenshots_by_component.setdefault(cp, []).append(ss)
                else:
                    global_screenshots.append(ss)

            current_step = 0
            screenshot_step = 0

            # PASS 1: Analyze each file and extract test scenarios
            for idx, (path, content) in enumerate(critical_files, 1):
                try:
                    current_step += 1
                    self._update_progress(
                        session_id, "analyzing", current_step, total_steps,
                        f"Extracting test scenarios from: {Path(path).name}"
                    )

                    _before_lines = doc_file.read_text(encoding='utf-8').splitlines()

                    prompt = self._build_incremental_qa_file_prompt(
                        path, content, idx, len(critical_files),
                        str(doc_file), selection_context, business_section
                    )

                    await temp_session.send_and_wait(
                        {"prompt": prompt},
                        timeout=config.DOC_GEN_FILE_TIMEOUT
                    )

                    _after_lines = doc_file.read_text(encoding='utf-8').splitlines()
                    _added = max(0, len(_after_lines) - len(_before_lines))
                    _removed = max(0, len(_before_lines) - len(_after_lines))
                    _changed = sum(1 for a, b in zip(_before_lines, _after_lines) if a != b)
                    logger.info(f"✓ QA Pass {idx} complete: +{_added} -{_removed} lines, {_changed} lines changed")
                    self._update_progress(
                        session_id, "analyzing", current_step, total_steps,
                        f"✓ {Path(path).name}",
                        diff={"added": _added, "removed": _removed, "changed": _changed}
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Timeout analyzing {path} for QA")
                except Exception as e:
                    logger.error(f"Error analyzing {path} for QA: {e}")

                # Process screenshots associated with this file
                file_screenshots = []
                norm_path = path.replace('\\', '/')
                for comp_path, ss_list in screenshots_by_component.items():
                    norm_comp = comp_path.replace('\\', '/')
                    if norm_comp in norm_path or norm_path in norm_comp:
                        file_screenshots.extend(ss_list)
                    elif Path(comp_path).stem in norm_path:
                        file_screenshots.extend(ss_list)

                for ss in file_screenshots:
                    screenshot_step += 1
                    current_step += 1
                    ss_index = next((i for i, s in enumerate(screenshots, 1) if s.get('path') == ss.get('path')), screenshot_step)
                    self._update_progress(
                        session_id, "screenshot_analysis", current_step, total_steps,
                        f"Analyzing screenshot {screenshot_step}/{num_screenshots} for test context"
                    )
                    ss_prompt = self._build_screenshot_pass_prompt(
                        screenshot=ss, screenshot_index=ss_index,
                        total_screenshots=num_screenshots,
                        doc_file_path=str(doc_file), component_context=path
                    )
                    try:
                        await temp_session.send_and_wait(
                            {"prompt": ss_prompt, "attachments": [{"type": "file", "path": ss.get('ai_path', ss['path'])}]},
                            timeout=config.DOC_GEN_SCREENSHOT_TIMEOUT
                        )
                    except Exception as e:
                        logger.error(f"Error on QA screenshot pass {screenshot_step}: {e}")

            # Process global screenshots
            for ss in global_screenshots:
                screenshot_step += 1
                current_step += 1
                ss_index = next((i for i, s in enumerate(screenshots, 1) if s.get('path') == ss.get('path')), screenshot_step)
                self._update_progress(
                    session_id, "screenshot_analysis", current_step, total_steps,
                    f"Analyzing global screenshot {screenshot_step}/{num_screenshots}"
                )
                ss_prompt = self._build_screenshot_pass_prompt(
                    screenshot=ss, screenshot_index=ss_index,
                    total_screenshots=num_screenshots, doc_file_path=str(doc_file)
                )
                try:
                    await temp_session.send_and_wait(
                        {"prompt": ss_prompt, "attachments": [{"type": "file", "path": ss.get('ai_path', ss['path'])}]},
                        timeout=config.DOC_GEN_SCREENSHOT_TIMEOUT
                    )
                except Exception as e:
                    logger.error(f"Error on QA global screenshot pass {screenshot_step}: {e}")

            # PASS 2: Section-by-section test script generation
            for sec_idx, (section_id, section_name) in enumerate(qa_sections, 1):
                try:
                    current_step += 1
                    self._update_progress(
                        session_id, "section_generation", current_step, total_steps,
                        f"Generating: {section_name}"
                    )
                    _before_lines = doc_file.read_text(encoding='utf-8').splitlines()

                    section_prompt = self._build_qa_section_editing_prompt(
                        section_id=section_id, section_name=section_name,
                        doc_file_path=str(doc_file), selection_context=selection_context,
                        business_section=business_section,
                        files_analyzed=len(critical_files),
                        critical_files=critical_files,
                        non_critical_files=non_critical_files,
                        working_directory=working_directory,
                    )
                    await temp_session.send_and_wait(
                        {"prompt": section_prompt},
                        timeout=config.DOC_GEN_SECTION_TIMEOUT
                    )

                    _after_lines = doc_file.read_text(encoding='utf-8').splitlines()
                    _added = max(0, len(_after_lines) - len(_before_lines))
                    _removed = max(0, len(_before_lines) - len(_after_lines))
                    _changed = sum(1 for a, b in zip(_before_lines, _after_lines) if a != b)
                    logger.info(f"✓ QA Section '{section_id}' complete: +{_added} -{_removed} lines, {_changed} lines changed")
                    self._update_progress(
                        session_id, "section_generation", current_step, total_steps,
                        f"✓ {section_name}",
                        diff={"added": _added, "removed": _removed, "changed": _changed}
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Timeout generating QA section '{section_id}'")
                except Exception as e:
                    logger.error(f"Error generating QA section '{section_id}': {e}")

            documentation = doc_file.read_text(encoding='utf-8')
            logger.info(f"✓ Test scripts ready: {len(documentation)} chars")

            try:
                if hasattr(temp_session, 'close'):
                    await temp_session.close()
            except Exception as e:
                logger.warning(f"Error closing QA session: {e}")

            self._update_progress(
                session_id, "test_scripts_complete", total_steps, total_steps,
                "Test scripts generation complete"
            )
            return documentation

        except Exception as e:
            logger.exception(f"Error in test scripts generation for {session_id}")
            self._update_progress(session_id, "error", 0, total_steps, f"Error: {str(e)}")
            raise

    def _build_qa_system_prompt(
        self,
        doc_file_path: str,
        screenshots: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Build system prompt for QA test scripts generation."""
        role_desc = "Power Platform QA test engineer"
        task_desc = (
            "Write comprehensive QA test scripts including functional tests, "
            "edge cases, boundary tests, and regression scenarios. "
            "For Power Fx formulas, generate test cases that cover: happy path, empty/null inputs, "
            "boundary values, delegation limits, error conditions, and concurrent user scenarios. "
            "For Power Automate flows, generate test cases that cover: trigger conditions, "
            "action success/failure paths, connector timeouts, run-after configurations, "
            "and data transformation validation."
        )

        screenshot_instructions = self._build_screenshot_system_instructions(screenshots) if screenshots else ""

        return f"""[!] CRITICAL: This is a FILE EDITING task, not a conversation.

YOU MUST USE TOOLS TO EDIT THE FILE. DO NOT WRITE TEXT RESPONSES.

**DOCUMENT FILE:** `{doc_file_path}`

**PROHIBITED ACTIONS:**
[X] DO NOT write conversational responses describing what you would do
[X] DO NOT say "I will analyze..." or "Here's what I found..."
[X] DO NOT provide summaries or explanations in text
[X] DO NOT describe tool calls - EXECUTE them

**REQUIRED ACTIONS:**
[OK] USE read_file to check current state
[OK] USE replace_string_in_file or multi_replace_string_in_file to ACTUALLY edit the file
[OK] Make the edits directly - your ONLY output should be tool calls
[OK] Edit the file immediately upon analyzing each component

---

**YOUR ROLE:** {role_desc} using INCREMENTAL EDITING

**YOUR TASK:** {task_desc}

1. Read the current state of `{doc_file_path}`
2. Identify which sections are relevant to the component you're analyzing
3. USE replace_string_in_file to fill in those sections with actual content
4. Preserve template structure and existing content

POWER PLATFORM EXPERTISE:
- **Power Fx**: Low-code formula language in Canvas Apps — KNOW that:
  * `Filter()`, `Search()`, `LookUp()` on large tables may NOT be delegable depending on the data source
  * `Collect()` / `ClearCollect()` load data client-side — risky with large datasets
  * `Patch()` can silently fail without error handling — always check with `IfError()` or `IsError()`
  * `Set()` creates global variables, `UpdateContext()` creates screen-scoped — prefer scoped
  * `Navigate()` with `ScreenTransition` can cause flicker or performance issues
  * Nested `ForAll()` loops can be extremely slow — O(n²) behavior
  * `concurrent=true` in `OnStart` can cause race conditions if variables depend on each other
- **Power Automate (JSON format)**: Workflow definitions where:
  * `"triggers"` section defines when the flow runs — check trigger conditions carefully
  * `"actions"` are the steps — look for missing `"runAfter"` failure/error paths
  * Scope actions should wrap risky operations for try-catch error handling
  * HTTP connectors without retry policies can cause silent failures
  * `Apply_to_each` loops without concurrency limits default to sequential
  * Expression syntax: `@{{triggerBody()?['property']}}` — null-safe `?` operator is critical
  * Connection references in `"$connections"` — check for hardcoded vs environment variables
- **Canvas Apps**: Custom UI apps with screens and controls
- **Dataverse**: Microsoft's cloud database for business data

[TOOLS] **AVAILABLE TOOLS:**

- **read_file**: Read current state of the document file
- **replace_string_in_file**: Replace specific text in the document
- **multi_replace_string_in_file**: Make multiple edits at once
- **grep_search**: Find specific sections in the doc

{screenshot_instructions}

Be precise with edits. Use the tools to actually modify the document file."""

    def _build_incremental_qa_file_prompt(
        self,
        path: str,
        content: str,
        idx: int,
        total: int,
        doc_file_path: str,
        selection_context: str,
        business_context: str
    ) -> str:
        """Build prompt for analyzing a file and extracting QA test scenarios."""
        path_lower = path.lower()
        relevant_sections_hint = ""

        if '.fx.yaml' in path_lower:
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
- `### 3.2 Power Fx Formula Validation` — create test cases for each formula:
  * Happy path: normal expected inputs
  * Empty/null: what happens with blank fields or empty collections?
  * Boundary values: max length strings, zero values, negative numbers
  * Delegation: will this query work with >500/2000 records?
  * Error conditions: what if Patch fails? What if LookUp returns blank?
- `### 3.1 Screen Navigation Tests` — test navigation between screens
- `### 3.3 Data Operations (CRUD)` — test Create/Read/Update/Delete operations
- `### 3.4 UI Control Behavior` — test visibility, enable/disable, conditional formatting
"""
        elif 'canvasmanifest' in path_lower:
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
- `## Test Plan Information` — extract solution name, version
- `### 1.1 Prerequisites` — extract required connections, licenses
- `### 3.1 Screen Navigation Tests` — extract screen list for navigation tests
"""
        elif 'workflows' in path_lower and path_lower.endswith('.json'):
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
This is a **Power Automate flow definition** in JSON format.
- `### 4.1 Flow Trigger Tests` — test trigger conditions (when does/doesn't it fire?)
- `### 4.2 Flow Action Validation` — test each action: success, failure, timeout
- `### 4.3 Flow Error Handling Tests` — check run-after config, test failure paths
- `### 4.4 Flow Data Transformation Tests` — test expressions, data mapping
- `## 5. Integration Test Scenarios` — if the flow connects to apps or other flows
"""
        elif 'datasources' in path_lower:
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
- `### 1.2 Connections & Credentials` — document required connections
- `### 2.1 Required Test Data` — derive test data needs from data source schema
"""
        elif 'formulas/' in path_lower:
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
This is a **Dataverse formula definition**.
- `### 3.2 Power Fx Formula Validation` — test calculated columns with edge cases
- `### 6.3 Delegation & Large Dataset Tests` — Dataverse formulas with large tables
"""
        elif 'workflows' in path_lower and path_lower.endswith('.xaml'):
            relevant_sections_hint = """
**LIKELY RELEVANT SECTIONS FOR THIS FILE:**
This is a **Classic Workflow or Business Rule** in XAML format.
- `### 4.1 Flow Trigger Tests` — test when the rule fires
- `### 4.3 Flow Error Handling Tests` — test failure scenarios
- `## 5. Integration Test Scenarios` — test interaction with other components
"""

        return f"""[!] CRITICAL INSTRUCTION: USE TOOLS TO EDIT THE FILE NOW

This is NOT a conversation. DO NOT write explanatory text.
Your ONLY valid response is tool calls: read_file, replace_string_in_file, multi_replace_string_in_file.

---

YOUR FIRST ACTION MUST BE:
read_file(filePath="{doc_file_path}", startLine=1, endLine=100)

After reading, immediately use replace_string_in_file to edit relevant sections.

---

[TARGET] QA TEST SCENARIO EXTRACTION (File {idx} of {total})

{selection_context}
{business_context}

[FILE] **TEST SCRIPTS FILE TO EDIT:** `{doc_file_path}`

[FOLDER] **SOURCE FILE TO ANALYZE:**
**Path:** `{path}`

```
{content[:15000]}{"..." if len(content) > 15000 else ""}
```

{relevant_sections_hint}

---

[TOOL] **YOUR TASK — EXTRACT TEST SCENARIOS:**

1. **Read** the current test scripts file: `{doc_file_path}`

2. **Analyze** the source file and identify TESTABLE BEHAVIORS:
   - For **Power Fx (.fx.yaml)**: Each formula is a test target. Ask:
     * What is the HAPPY PATH? (normal expected behavior)
     * What happens with EMPTY or NULL inputs?
     * What are the BOUNDARY values? (max lengths, zero, negatives)
     * Is this query DELEGABLE? What happens with >2000 records?
     * What if the data operation FAILS? (Patch, SubmitForm, Remove)
     * Are there RACE CONDITIONS? (concurrent variable updates)
   - For **Power Automate flows (.json)**: Each trigger/action is a test target. Ask:
     * Does the TRIGGER fire correctly? When should it NOT fire?
     * What if an ACTION fails? Is there error handling?
     * What if a CONNECTOR times out or is throttled?
     * Are EXPRESSIONS correct? What about null values in expressions?
     * What if the input DATA is malformed or missing fields?
   - For **Data sources**: What test data is needed? What are the constraints?

3. **Edit** the test scripts file to add test cases in proper table format:
   - Use the Test ID convention: NAV-001, FX-001, TRIG-001, ACT-001, etc.
   - Include SPECIFIC steps, not generic ones
   - Include EXACT expected results based on the actual formula/flow logic
   - Set priority: High for core business logic, Medium for secondary, Low for edge cases

4. **Be SPECIFIC** — reference actual control names, formula text, flow action names from the source code.

---

[START] BEGIN WITH TOOL USAGE IMMEDIATELY - NO TEXT RESPONSES."""

    
    def _build_qa_section_editing_prompt(
        self,
        section_id: str,
        section_name: str,
        doc_file_path: str,
        selection_context: str,
        business_section: str,
        files_analyzed: int,
        critical_files: List[tuple],
        non_critical_files: List[tuple],
        working_directory: Path,
    ) -> str:
        """Build a focused prompt for editing one specific QA test scripts section."""
        files_inventory = ""
        if section_id in ("canvas_tests", "flow_tests", "integration_tests", "test_environment"):
            files_inventory = self._build_files_inventory(
                critical_files, non_critical_files, working_directory
            )

        section_instructions = {
            "test_plan_info": f"""[TARGET] **SECTION: Test Plan Information**

Edit the top of `{doc_file_path}` to fill in:

1. **Solution Name** — extract from data already in the doc or metadata
2. **Version Under Test** — from manifest or "1.0.0"
3. **Date** — today's date
4. **Prepared By** — "Auto-generated QA Test Scripts"
5. **Test Environment** — "Sandbox" (default recommendation for testing)
6. **Test Scope** — synthesize from the components analyzed

Only edit the `## Test Plan Information` block.""",

            "test_environment": f"""[TARGET] **SECTIONS 1 & 2: Test Environment Setup & Test Data Requirements**

Edit `{doc_file_path}` to fill Sections 1 and 2:

1. **Section 1 — Test Environment Setup:**
   - **1.1 Prerequisites:** List required licenses, security roles, browsers
   - **1.2 Connections & Credentials:** List all data connections found in the analyzed files
     (DO NOT include actual credentials — only types and how to obtain them)
   - **1.3 Environment Configuration:** Any feature flags or settings needed

2. **Section 2 — Test Data Requirements:**
   - **2.1 Required Test Data:** Based on data sources and entity references found in the code,
     list what test data records are needed (entities, field values, record counts)
   - **2.2 Test Data Setup Steps:** How to prepare the test environment
   - **2.3 Data Cleanup Procedure:** How to reset after testing

{files_inventory}

Only edit Sections 1-2.""",

            "canvas_tests": f"""[TARGET] **SECTION 3: Canvas App Test Scenarios**

Edit `{doc_file_path}` to complete Section 3 with specific, actionable test cases:

1. **Read the doc** to see what test scenarios were extracted from file analysis passes
2. **Fill gaps and enhance** the subsections:
   - **3.1 Screen Navigation Tests:** Ensure all screens have navigation test cases
   - **3.2 Power Fx Formula Validation:** For EVERY significant formula:
     * Generate happy path test case
     * Generate empty/null input test case
     * Generate boundary value test case (if applicable)
     * Generate error condition test case (if the formula does data operations)
     * Generate delegation test case (if the formula uses Filter/Search/LookUp)
   - **3.3 Data Operations (CRUD):** Test every Patch, SubmitForm, Remove, Collect operation
   - **3.4 UI Control Behavior:** Test visibility conditions, enable/disable, conditional formatting
3. **De-duplicate** test cases and ensure proper Test ID numbering
4. **Assign priorities:** High = core business logic, Medium = secondary features, Low = cosmetic/edge cases

{files_inventory}

Only edit Section 3.""",

            "flow_tests": f"""[TARGET] **SECTION 4: Power Automate Flow Test Scenarios**

Edit `{doc_file_path}` to complete Section 4 with specific flow test cases:

1. **Read the doc** to see what test scenarios exist from file analysis passes
2. **Fill gaps and enhance:**
   - **4.1 Flow Trigger Tests:** For each flow:
     * Test that the trigger fires with valid conditions
     * Test that the trigger does NOT fire with invalid conditions
     * Test scheduled triggers with correct timing
   - **4.2 Flow Action Validation:** For each significant action:
     * Test successful execution with valid data
     * Test with invalid/missing input data
     * Test connector timeout scenarios
   - **4.3 Flow Error Handling Tests:** For each flow:
     * Does the flow have Scope-based try-catch? If not, note this as a gap
     * Test what happens when each connector fails
     * Verify run-after configurations work correctly
   - **4.4 Flow Data Transformation Tests:** Test expression logic and data mapping
3. **Be SPECIFIC** about which flow action to test and what data to use

Only edit Section 4.""",

            "integration_tests": f"""[TARGET] **SECTION 5: Integration Test Scenarios**

Edit `{doc_file_path}` to fill Section 5 — Integration Tests:

1. **Read the doc** to understand what Canvas Apps and flows exist
2. **Identify cross-component interactions:**
   - Canvas App triggering a Power Automate flow (via PowerAutomate.Run or button)
   - Flow writing data that the Canvas App reads
   - Multiple flows triggered in sequence
   - Shared data sources across components
3. **Write end-to-end test scenarios** that test the full chain:
   - User action in Canvas App → triggers flow → flow completes → data visible in app
   - Include EXACT steps for each integration test
   - Include expected intermediate states, not just final result
4. If no integration points are found, note that and suggest manual verification

Only edit Section 5.""",

            "edge_boundary": f"""[TARGET] **SECTION 6: Edge Case & Boundary Tests**

Edit `{doc_file_path}` to fill Section 6:

1. **Read the doc** to see what components/formulas/flows exist
2. **Fill subsections:**
   - **6.1 Input Boundary Tests:** For every user input field found:
     * Empty/null input
     * Maximum length (if text)
     * Special characters (quotes, HTML, unicode)
     * Zero/negative (if numeric)
     * Future/past dates (if date picker)
   - **6.2 State & Timing Edge Cases:**
     * App opened on mobile vs desktop
     * Network disconnection during data operation
     * Session timeout during long workflow
     * Browser back button behavior
     * Concurrent users editing same record
   - **6.3 Delegation & Large Dataset Tests:**
     * Identify ALL non-delegable queries from the formula analysis
     * For each: what happens with 500+ records? 2000+ records?
     * Document the delegation limit and expected behavior

Only edit Section 6.""",

            "perf_security_a11y": f"""[TARGET] **SECTIONS 7, 8, 9: Performance, Security & Accessibility**

Edit `{doc_file_path}` to fill Sections 7-9:

1. **Section 7 — Performance Tests:**
   - App load time (target <5s)
   - Gallery/list rendering with large datasets
   - Flow execution time for each flow
   - Concurrent user scenarios

2. **Section 8 — Security & Access Tests:**
   - Test with correct security role → full access
   - Test without required role → access denied
   - Test data visibility across different roles
   - Test direct URL/deep link access
   - Note if role-based testing isn't applicable, explain why

3. **Section 9 — Accessibility Tests:**
   - Standard WCAG 2.1 test scenarios
   - Keyboard-only navigation
   - Screen reader compatibility
   - Color contrast
   - Error identification

Replace placeholder text with specific or standardized test cases.

Only edit Sections 7-9.""",

            "regression_checklist": f"""[TARGET] **SECTION 10 + Appendix: Regression Checklist & Final Cleanup**

Edit `{doc_file_path}` to complete Section 10, Appendix, and Table of Contents:

**Part A — Section 10 Regression Test Checklist:**
1. Review the entire document and identify the TOP 10-15 most critical test scenarios
2. Add them to the regression table with their Test ID reference
3. These should cover: core navigation, main CRUD operations, key flow triggers, critical formulas

**Part B — Appendix Test Execution Log:**
- Leave as a blank template for testers to fill in during execution

**Part C — Table of Contents:**
Read the full document and generate a proper Table of Contents with markdown links.

**Part D — Final cleanup:**
- Replace any remaining template placeholders with actual content or "N/A"
- Ensure all Test IDs are properly numbered (no gaps, no duplicates)
- Ensure consistent table formatting
- Remove any raw template instructions (lines starting with `>`)

Edit Section 10, Appendix, Table of Contents, and do final cleanup.""",
        }

        instruction = section_instructions.get(section_id, f"Complete the {section_name} section.")

        return f"""[!] CRITICAL: SECTION EDITING TASK — USE TOOLS ONLY

DO NOT write text. USE read_file and replace_string_in_file to edit `{doc_file_path}`.

---

{selection_context}

**TEST SCRIPTS FILE:** `{doc_file_path}`
**You have analyzed {files_analyzed} files in previous passes.**

---

{instruction}

---

[EDIT] **GUIDELINES:**

[OK] **DO:**
- Read the file first with read_file to see current state
- Use replace_string_in_file for precise edits
- Include 3-5 lines of context in oldString for accurate matching
- Generate SPECIFIC test cases with actual component/formula names from the analysis
- Preserve content from other sections

[STOP] **DON'T:**
- Don't write conversational text — only use tools
- Don't edit sections outside your assigned scope
- Don't remove content added by earlier passes
- Don't use generic placeholder test cases — be specific to the actual solution

[START] **BEGIN IMMEDIATELY WITH TOOL CALLS.**"""

    

# Global singleton instance
_doc_generator: Optional[DocumentationGenerator] = None


async def get_doc_generator() -> DocumentationGenerator:
    """Get or create the global documentation generator instance"""
    global _doc_generator
    
    if _doc_generator is None:
        _doc_generator = DocumentationGenerator()
        await _doc_generator.initialize()
    
    return _doc_generator
