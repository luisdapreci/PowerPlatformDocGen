# Copilot SDK Enhancement Implementation Guide

## Overview

This guide provides step-by-step instructions for implementing native Copilot SDK features to maximize the value of your Power Platform documentation generator.

---

## Phase 1: Foundation (START HERE) ⭐⭐⭐

### Task 1.1: Convert Custom Tools to Native SDK Format

**Time Estimate:** 1-2 hours  
**Files Modified:** `src/copilot_tools.py`

#### Step 1: Add Required Imports

At the top of `src/copilot_tools.py`, add:

```python
"""Custom Copilot SDK tools for Power Platform analysis"""
import json
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
from pydantic import BaseModel, Field
from copilot import define_tool

logger = logging.getLogger(__name__)
```

#### Step 2: Define Pydantic Parameter Models

Add these model classes after the imports:

```python
# ==================== PARAMETER MODELS ====================

class AnalyzeCanvasAppParams(BaseModel):
    app_src_dir: str = Field(
        description="Absolute path to the unpacked canvas app _src directory"
    )

class ListDataSourcesParams(BaseModel):
    app_src_dir: str = Field(
        description="Absolute path to the unpacked canvas app _src directory"
    )

class ExtractAppMetadataParams(BaseModel):
    app_src_dir: str = Field(
        description="Absolute path to the unpacked canvas app _src directory"
    )

class AnalyzeFlowParams(BaseModel):
    flow_file_path: str = Field(
        description="Absolute path to the Power Automate flow JSON file"
    )

class FindConnectionsParams(BaseModel):
    solution_dir: str = Field(
        description="Absolute path to the extracted solution root directory"
    )

class ParseSolutionXmlParams(BaseModel):
    solution_xml_path: str = Field(
        description="Absolute path to the solution.xml file"
    )
```

#### Step 3: Convert Functions to SDK Tools

Replace each existing function with the decorated async version. Here's the template for ALL tools:

```python
# ==================== TOOL DEFINITIONS ====================

@define_tool(description="Analyze Power Fx formulas in a Canvas App by reading .fx.yaml files")
async def analyze_canvas_app_formulas(params: AnalyzeCanvasAppParams) -> str:
    """
    Reads Power Fx formula files from a Canvas App source directory.
    Returns JSON string with formula definitions organized by control/screen.
    """
    try:
        src_path = Path(params.app_src_dir) / "src"
        if not src_path.exists():
            return json.dumps({
                "error": f"Source directory not found: {src_path}",
                "success": False
            })
        
        formulas = {}
        fx_files = list(src_path.rglob("*.fx.yaml"))
        
        for fx_file in fx_files:
            control_name = fx_file.stem
            try:
                with open(fx_file, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load(f)
                    if content:
                        formulas[control_name] = content
            except Exception as e:
                logger.warning(f"Could not parse {fx_file}: {e}")
        
        return json.dumps({
            "success": True,
            "app_directory": params.app_src_dir,
            "formula_files_found": len(fx_files),
            "formulas": formulas
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "success": False
        })


@define_tool(description="List all data sources used by a Canvas App")
async def list_data_sources(params: ListDataSourcesParams) -> str:
    """
    Reads DataSources/*.json files from a Canvas App.
    Returns JSON string with data source definitions.
    """
    try:
        datasources_path = Path(params.app_src_dir) / "DataSources"
        if not datasources_path.exists():
            return json.dumps({
                "success": True,
                "data_sources": [],
                "message": "No DataSources directory found"
            })
        
        data_sources = []
        for ds_file in datasources_path.glob("*.json"):
            try:
                with open(ds_file, 'r', encoding='utf-8') as f:
                    ds_data = json.load(f)
                    data_sources.append({
                        "name": ds_file.stem,
                        "definition": ds_data
                    })
            except Exception as e:
                logger.warning(f"Could not parse {ds_file}: {e}")
        
        return json.dumps({
            "success": True,
            "app_directory": params.app_src_dir,
            "data_sources_count": len(data_sources),
            "data_sources": data_sources
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "success": False
        })


@define_tool(description="Extract metadata from a Canvas App's CanvasManifest.json")
async def extract_app_metadata(params: ExtractAppMetadataParams) -> str:
    """
    Reads CanvasManifest.json from a Canvas App.
    Returns JSON string with app metadata (name, author, screens, etc).
    """
    try:
        manifest_path = Path(params.app_src_dir) / "src" / "CanvasManifest.json"
        if not manifest_path.exists():
            return json.dumps({
                "error": f"CanvasManifest.json not found at {manifest_path}",
                "success": False
            })
        
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        return json.dumps({
            "success": True,
            "app_directory": params.app_src_dir,
            "metadata": {
                "name": manifest.get("Properties", {}).get("Name", "Unknown"),
                "author": manifest.get("Properties", {}).get("Author", "Unknown"),
                "description": manifest.get("Properties", {}).get("Description", ""),
                "document_type": manifest.get("Properties", {}).get("DocumentType", ""),
                "app_version": manifest.get("Properties", {}).get("AppVersion", ""),
                "screens": manifest.get("Screens", []),
                "components": manifest.get("Components", [])
            }
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "success": False
        })


@define_tool(description="Analyze a Power Automate flow definition file")
async def analyze_flow_definition(params: AnalyzeFlowParams) -> str:
    """
    Parses a Power Automate flow JSON file.
    Returns JSON string with flow trigger, actions, and connection references.
    """
    try:
        flow_path = Path(params.flow_file_path)
        if not flow_path.exists():
            return json.dumps({
                "error": f"Flow file not found: {params.flow_file_path}",
                "success": False
            })
        
        with open(flow_path, 'r', encoding='utf-8') as f:
            flow_data = json.load(f)
        
        properties = flow_data.get("properties", {})
        definition = properties.get("definition", {})
        
        return json.dumps({
            "success": True,
            "flow_name": flow_path.stem,
            "display_name": properties.get("displayName", "Unknown"),
            "state": properties.get("state", "Unknown"),
            "trigger": {
                "type": list(definition.get("triggers", {}).keys())[0] if definition.get("triggers") else "Unknown",
                "details": list(definition.get("triggers", {}).values())[0] if definition.get("triggers") else {}
            },
            "actions_count": len(definition.get("actions", {})),
            "actions": list(definition.get("actions", {}).keys()),
            "connection_references": properties.get("connectionReferences", {})
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "success": False
        })


@define_tool(description="Find all connection references in a Power Platform solution")
async def find_connections(params: FindConnectionsParams) -> str:
    """
    Searches for connection files in a solution directory.
    Returns JSON string with all found connections.
    """
    try:
        solution_path = Path(params.solution_dir)
        connections = []
        
        # Look for connection files in various locations
        connection_dirs = [
            solution_path / "Connections",
            solution_path / "ConnectionReferences"
        ]
        
        for conn_dir in connection_dirs:
            if conn_dir.exists():
                for conn_file in conn_dir.rglob("*.json"):
                    try:
                        with open(conn_file, 'r', encoding='utf-8') as f:
                            conn_data = json.load(f)
                            connections.append({
                                "file": conn_file.name,
                                "data": conn_data
                            })
                    except Exception as e:
                        logger.warning(f"Could not parse {conn_file}: {e}")
        
        # Also check canvas apps for embedded connections
        for app_dir in solution_path.rglob("*_src"):
            conn_path = app_dir / "Connections"
            if conn_path.exists():
                for conn_file in conn_path.glob("*.json"):
                    try:
                        with open(conn_file, 'r', encoding='utf-8') as f:
                            conn_data = json.load(f)
                            connections.append({
                                "file": f"{app_dir.name}/{conn_file.name}",
                                "data": conn_data
                            })
                    except Exception as e:
                        logger.warning(f"Could not parse {conn_file}: {e}")
        
        return json.dumps({
            "success": True,
            "solution_directory": params.solution_dir,
            "connections_found": len(connections),
            "connections": connections
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "success": False
        })


@define_tool(description="Parse solution.xml to extract solution metadata")
async def parse_solution_xml(params: ParseSolutionXmlParams) -> str:
    """
    Parses a Power Platform solution.xml file.
    Returns JSON string with solution name, version, publisher info.
    """
    try:
        from lxml import etree
        
        xml_path = Path(params.solution_xml_path)
        if not xml_path.exists():
            return json.dumps({
                "error": f"solution.xml not found at {params.solution_xml_path}",
                "success": False
            })
        
        tree = etree.parse(str(xml_path))
        root = tree.getroot()
        
        # Extract key information
        solution_manifest = root.find(".//SolutionManifest")
        if solution_manifest is not None:
            unique_name = solution_manifest.findtext("UniqueName", "Unknown")
            version = solution_manifest.findtext("Version", "Unknown")
            
            publisher = solution_manifest.find("Publisher")
            publisher_name = publisher.findtext("UniqueName", "Unknown") if publisher is not None else "Unknown"
            
            localized_names = {}
            if solution_manifest.find(".//LocalizedName") is not None:
                localized_names = {
                    elem.get("languagecode"): elem.get("description")
                    for elem in solution_manifest.findall(".//LocalizedName")
                }
            
            return json.dumps({
                "success": True,
                "solution_name": unique_name,
                "version": version,
                "publisher": publisher_name,
                "localized_names": localized_names
            }, indent=2)
        
        return json.dumps({
            "error": "Could not parse solution manifest",
            "success": False
        })
        
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "success": False
        })
```

#### Step 4: Verify Changes

Run this test:

```python
# Test file: test_copilot_tools.py
import asyncio
from copilot_tools import analyze_canvas_app_formulas, AnalyzeCanvasAppParams

async def test():
    result = await analyze_canvas_app_formulas(
        AnalyzeCanvasAppParams(app_src_dir="/path/to/app_src")
    )
    print(result)

asyncio.run(test())
```

---

### Task 1.2: Wire Tools into Session Manager

**Time Estimate:** 15-30 minutes  
**Files Modified:** `src/session_manager.py`

#### Step 1: Add Import Statement

At the top of `src/session_manager.py`, add:

```python
"""Session management for Copilot SDK"""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, List
from copilot import CopilotClient, CopilotSession
import logging
import config

# Import custom tools
from copilot_tools import (
    analyze_canvas_app_formulas,
    list_data_sources,
    extract_app_metadata,
    analyze_flow_definition,
    find_connections,
    parse_solution_xml
)

logger = logging.getLogger(__name__)
```

#### Step 2: Modify create_session Method

Find the `create_session` method (around line 40) and update the session configuration:

```python
async def create_session(
    self,
    session_id: str,
    working_directory: Path,
    tools: Optional[List] = None,
    available_tools: Optional[List[str]] = None
) -> CopilotSession:
    """
    Create a new Copilot session for solution analysis
    """
    if not self.client:
        raise RuntimeError("SessionManager not initialized")
    
    # System prompt for Power Platform analysis
    system_prompt = """You are a Power Platform solution analyst expert..."""  # Keep existing
    
    # Prepare custom tools list
    custom_tools = [
        analyze_canvas_app_formulas,
        list_data_sources,
        extract_app_metadata,
        analyze_flow_definition,
        find_connections,
        parse_solution_xml
    ]
    
    # Override with provided tools if specified
    if tools is not None:
        custom_tools = tools
    
    # Create session configuration
    session_config = {
        "model": config.COPILOT_MODEL,
        "working_directory": str(working_directory),
        "streaming": config.COPILOT_STREAMING,
        "tools": custom_tools,  # ADD THIS LINE
        "system_message": {
            "mode": "append",
            "content": system_prompt
        }
    }
    
    # Add available_tools if specified
    if available_tools:
        session_config["available_tools"] = available_tools
    
    try:
        copilot_session = await self.client.create_session(session_config)
        
        # Store managed session
        managed_session = ManagedSession(
            session_id=session_id,
            copilot_session=copilot_session,
            working_directory=working_directory
        )
        self.sessions[session_id] = managed_session
        
        logger.info(f"Created Copilot session for {session_id} with {len(custom_tools)} custom tools")
        return copilot_session
        
    except Exception as e:
        logger.error(f"Failed to create session for {session_id}: {e}")
        raise
```

#### Step 3: Test Integration

Start your server and upload a solution:

```powershell
python src/main.py
```

In the chat, try:
```
What Power Fx formulas are in this solution?
```

You should see the agent using your custom tools!

---

### Task 1.3: Add Configuration Options

**Time Estimate:** 15 minutes  
**Files Modified:** `src/config.py`

#### Add New Configuration Settings

At the end of `src/config.py`, add:

```python
# Copilot SDK settings
COPILOT_MODEL = "claude-sonnet-4.5"
COPILOT_STREAMING = True

# Custom tools configuration
COPILOT_ENABLE_CUSTOM_TOOLS = True

# Built-in tool security (whitelist approach)
# Set to None to allow all tools, or provide a list to restrict
COPILOT_ALLOWED_BUILTIN_TOOLS = [
    "read_file",
    "list_dir",
    "grep_search",
    "view",
    # Exclude "bash" for security in production
    # Exclude "web_request" if not needed
]

# Infinite sessions configuration
COPILOT_ENABLE_INFINITE_SESSIONS = True
COPILOT_COMPACTION_THRESHOLD = 0.75  # Start compacting at 75% context usage
COPILOT_BUFFER_THRESHOLD = 0.90  # Block at 90% until compaction completes

# Hooks configuration
COPILOT_ENABLE_HOOKS = True
```

#### Update session_manager.py to Use Config

Modify the session configuration to use these settings:

```python
# In create_session method
session_config = {
    "model": config.COPILOT_MODEL,
    "working_directory": str(working_directory),
    "streaming": config.COPILOT_STREAMING,
    "tools": custom_tools if config.COPILOT_ENABLE_CUSTOM_TOOLS else [],
    "system_message": {
        "mode": "append",
        "content": system_prompt
    }
}

# Add infinite sessions config
if config.COPILOT_ENABLE_INFINITE_SESSIONS:
    session_config["infinite_sessions"] = {
        "enabled": True,
        "background_compaction_threshold": config.COPILOT_COMPACTION_THRESHOLD,
        "buffer_exhaustion_threshold": config.COPILOT_BUFFER_THRESHOLD
    }

# Add available_tools restriction
if config.COPILOT_ALLOWED_BUILTIN_TOOLS:
    session_config["available_tools"] = config.COPILOT_ALLOWED_BUILTIN_TOOLS
```

---

## Phase 2: Real-time Streaming ⭐⭐⭐

### Task 2.1: Implement Event-Driven WebSocket

**Time Estimate:** 2-3 hours  
**Files Modified:** `src/main.py`

#### Step 1: Create Event Handler

Replace the existing `chat_websocket` function (around line 407):

```python
@app.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for interactive chat with the Copilot agent.
    Supports real-time streaming with delta events.
    """
    await websocket.accept()
    
    try:
        copilot_session = session_manager.get_session(session_id)
        if not copilot_session:
            await websocket.send_json({
                "error": "Session not found. Please upload a solution to start."
            })
            await websocket.close()
            return
        
        # Track current processing state
        processing_done = asyncio.Event()
        
        # Event handler for all Copilot events
        def on_event(event):
            event_type = event.type.value
            
            try:
                if event_type == "assistant.message_delta":
                    # Streaming text chunks
                    asyncio.create_task(websocket.send_json({
                        "type": "delta",
                        "content": event.data.delta_content or ""
                    }))
                
                elif event_type == "assistant.message":
                    # Complete message
                    asyncio.create_task(websocket.send_json({
                        "type": "message",
                        "content": event.data.content
                    }))
                
                elif event_type == "tool.call":
                    # Tool execution started
                    asyncio.create_task(websocket.send_json({
                        "type": "tool_call",
                        "tool": event.data.name,
                        "args": event.data.arguments if hasattr(event.data, 'arguments') else {}
                    }))
                
                elif event_type == "tool.result":
                    # Tool execution completed
                    result_preview = str(event.data.result)[:200] if hasattr(event.data, 'result') else ""
                    asyncio.create_task(websocket.send_json({
                        "type": "tool_result",
                        "tool": event.data.name if hasattr(event.data, 'name') else "unknown",
                        "preview": result_preview
                    }))
                
                elif event_type == "session.idle":
                    # Processing complete
                    asyncio.create_task(websocket.send_json({
                        "type": "idle"
                    }))
                    processing_done.set()
                
                elif event_type == "session.compaction_start":
                    asyncio.create_task(websocket.send_json({
                        "type": "system",
                        "message": "🔄 Compacting context (large conversation)..."
                    }))
                
                elif event_type == "session.compaction_complete":
                    asyncio.create_task(websocket.send_json({
                        "type": "system",
                        "message": "✅ Context compacted successfully"
                    }))
                
            except Exception as e:
                logger.error(f"Error handling event {event_type}: {e}")
        
        # Register event handler
        copilot_session.on(on_event)
        
        # Main message loop
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message = data.get("message", "")
            
            if not message:
                continue
            
            # Reset processing state
            processing_done.clear()
            
            # Send message to Copilot (non-blocking)
            try:
                await copilot_session.send({"prompt": message})
                
                # Wait for processing to complete
                await processing_done.wait()
                
            except Exception as e:
                logger.error(f"Error processing chat message: {e}")
                logger.exception("Full error details:")
                await websocket.send_json({
                    "type": "error",
                    "error": str(e)
                })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.exception(f"WebSocket error for session {session_id}")
        try:
            await websocket.close()
        except:
            pass
```

---

### Task 2.2: Update Frontend for Streaming

**Time Estimate:** 1-2 hours  
**Files Modified:** `static/index.html`

#### Step 1: Update WebSocket Message Handling

Find the WebSocket `onmessage` handler in `static/index.html` and replace it:

```javascript
// Enhanced WebSocket message handler
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    if (data.error) {
        addMessage('error', `Error: ${data.error}`);
        return;
    }
    
    switch(data.type) {
        case 'delta':
            // Streaming chunk - append to current message
            if (!currentStreamingMessage) {
                currentStreamingMessage = addMessage('assistant', '');
            }
            currentStreamingMessage.textContent += data.content;
            chatMessages.scrollTop = chatMessages.scrollHeight;
            break;
        
        case 'message':
            // Complete message
            if (currentStreamingMessage) {
                currentStreamingMessage = null;
            } else {
                addMessage('assistant', data.content);
            }
            break;
        
        case 'tool_call':
            // Tool execution indicator
            addToolIndicator('call', data.tool, data.args);
            break;
        
        case 'tool_result':
            // Tool completion indicator
            addToolIndicator('result', data.tool, data.preview);
            break;
        
        case 'idle':
            // Reset streaming state
            currentStreamingMessage = null;
            hideTypingIndicator();
            break;
        
        case 'system':
            // System message
            addMessage('system', data.message);
            break;
        
        case 'error':
            addMessage('error', data.error);
            break;
        
        default:
            console.log('Unknown message type:', data.type);
    }
};

// Helper function to show tool execution
function addToolIndicator(type, toolName, details) {
    const indicator = document.createElement('div');
    indicator.className = `tool-indicator tool-${type}`;
    
    if (type === 'call') {
        indicator.innerHTML = `🔧 <strong>${toolName}</strong>`;
    } else {
        indicator.innerHTML = `✅ <strong>${toolName}</strong> completed`;
    }
    
    chatMessages.appendChild(indicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Track current streaming message
let currentStreamingMessage = null;
```

#### Step 2: Add CSS Styles for Tool Indicators

Add to the `<style>` section:

```css
.tool-indicator {
    padding: 8px 12px;
    margin: 8px 0;
    border-radius: 4px;
    font-size: 0.9em;
    font-family: 'Courier New', monospace;
}

.tool-call {
    background-color: #e3f2fd;
    border-left: 4px solid #2196F3;
    color: #1565c0;
}

.tool-result {
    background-color: #e8f5e9;
    border-left: 4px solid #4caf50;
    color: #2e7d32;
}

.message.system {
    background-color: #fff3e0;
    border-left: 4px solid #ff9800;
    color: #e65100;
    font-style: italic;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

.streaming {
    animation: pulse 1.5s ease-in-out infinite;
}
```

---

## Phase 3: Monitoring & Control ⭐⭐

### Task 3.1: Implement Session Hooks

**Time Estimate:** 1-2 hours  
**Files Created:** `src/copilot_hooks.py`

#### Step 1: Create Hooks Module

Create a new file `src/copilot_hooks.py`:

```python
"""
Session hooks for monitoring and controlling Copilot SDK behavior
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Track tool usage statistics
tool_usage_stats = {}


async def on_pre_tool_use(input_data: Dict[str, Any], invocation) -> Dict[str, Any]:
    """
    Hook called before tool execution.
    Can allow/deny or modify tool arguments.
    """
    tool_name = input_data.get('toolName', 'unknown')
    tool_args = input_data.get('toolArgs', {})
    
    logger.info(f"🔧 Pre-tool: {tool_name}")
    logger.debug(f"   Args: {tool_args}")
    
    # Track usage
    tool_usage_stats[tool_name] = tool_usage_stats.get(tool_name, 0) + 1
    
    # Security checks
    if tool_name == "bash":
        command = str(tool_args.get('command', ''))
        dangerous_patterns = ['rm -rf', 'del /f', 'format', '> /dev/null']
        
        if any(pattern in command.lower() for pattern in dangerous_patterns):
            logger.warning(f"⚠️  Blocked dangerous command: {command}")
            return {
                "permissionDecision": "deny",
                "additionalContext": "Dangerous command blocked for security"
            }
    
    # Allow by default
    return {
        "permissionDecision": "allow",
        "additionalContext": f"Tool {tool_name} execution authorized"
    }


async def on_post_tool_use(input_data: Dict[str, Any], invocation) -> Dict[str, Any]:
    """
    Hook called after tool execution.
    Can log results or add context.
    """
    tool_name = input_data.get('toolName', 'unknown')
    result = input_data.get('result', {})
    
    # Log successful execution
    logger.info(f"✅ Post-tool: {tool_name}")
    
    # Add helpful context based on tool
    additional_context = ""
    
    if tool_name == "analyze_canvas_app_formulas":
        if isinstance(result, dict) and result.get('success'):
            formula_count = result.get('formula_files_found', 0)
            additional_context = f"Found {formula_count} Power Fx formula files"
    
    elif tool_name == "list_data_sources":
        if isinstance(result, dict) and result.get('success'):
            ds_count = result.get('data_sources_count', 0)
            additional_context = f"Identified {ds_count} data sources"
    
    return {
        "additionalContext": additional_context
    }


async def on_user_prompt_submitted(input_data: Dict[str, Any], invocation) -> Dict[str, Any]:
    """
    Hook called when user submits a prompt.
    Can modify or log the prompt.
    """
    prompt = input_data.get('prompt', '')
    
    logger.info(f"💬 User prompt: {prompt[:100]}...")
    
    # Could add automatic context here
    # For example, remind the agent about available tools for specific queries
    modified_prompt = prompt
    
    if "formula" in prompt.lower() and "power fx" not in prompt.lower():
        modified_prompt = f"{prompt}\n\nNote: Use analyze_canvas_app_formulas tool to examine Power Fx code."
    
    return {
        "modifiedPrompt": modified_prompt
    }


async def on_session_start(input_data: Dict[str, Any], invocation) -> Dict[str, Any]:
    """
    Hook called when session starts.
    """
    source = input_data.get('source', 'unknown')
    
    logger.info(f"🚀 Session started from: {source}")
    
    return {
        "additionalContext": "Power Platform solution analysis session initialized"
    }


async def on_session_end(input_data: Dict[str, Any], invocation) -> Dict[str, Any]:
    """
    Hook called when session ends.
    """
    reason = input_data.get('reason', 'unknown')
    
    logger.info(f"🛑 Session ended: {reason}")
    logger.info(f"📊 Tool usage stats: {tool_usage_stats}")
    
    return {}


async def on_error_occurred(input_data: Dict[str, Any], invocation) -> Dict[str, Any]:
    """
    Hook called when an error occurs.
    Can retry, skip, or abort.
    """
    error = input_data.get('error', 'Unknown error')
    context = input_data.get('errorContext', 'unknown')
    
    logger.error(f"❌ Error in {context}: {error}")
    
    # Retry on transient errors
    if "timeout" in error.lower() or "connection" in error.lower():
        logger.info("🔄 Retrying due to transient error...")
        return {"errorHandling": "retry"}
    
    # Skip on file not found
    if "not found" in error.lower():
        logger.info("⏭️  Skipping due to missing file...")
        return {"errorHandling": "skip"}
    
    # Abort on critical errors
    return {"errorHandling": "abort"}


def get_all_hooks():
    """
    Returns dictionary of all hooks for session configuration.
    """
    return {
        "on_pre_tool_use": on_pre_tool_use,
        "on_post_tool_use": on_post_tool_use,
        "on_user_prompt_submitted": on_user_prompt_submitted,
        "on_session_start": on_session_start,
        "on_session_end": on_session_end,
        "on_error_occurred": on_error_occurred
    }


def get_tool_usage_stats():
    """
    Returns current tool usage statistics.
    """
    return tool_usage_stats.copy()
```

#### Step 2: Integrate Hooks into Session Manager

In `src/session_manager.py`, add import and update session config:

```python
import copilot_hooks

# In create_session method, add hooks if enabled:
if config.COPILOT_ENABLE_HOOKS:
    session_config["hooks"] = copilot_hooks.get_all_hooks()
```

#### Step 3: Add Telemetry Endpoint

In `src/main.py`, add:

```python
from copilot_hooks import get_tool_usage_stats

@app.get("/telemetry/tool-usage")
async def get_tool_telemetry():
    """Get tool usage statistics"""
    return {
        "tool_usage": get_tool_usage_stats()
    }
```

---

## Testing Your Implementation

### Test Phase 1: Custom Tools

```python
# Test script: test_phase1.py
import asyncio
from copilot import CopilotClient

async def test_custom_tools():
    client = CopilotClient()
    await client.start()
    
    session = await client.create_session({
        "model": "gpt-4o",
        "working_directory": "/path/to/extracted/solution",
        "tools": [
            # Import your tools here
        ]
    })
    
    # Test prompt
    result = await session.send_and_wait({
        "prompt": "What Power Fx formulas are in this solution?"
    })
    
    print(result.data.content)
    
    await session.destroy()
    await client.stop()

asyncio.run(test_custom_tools())
```

### Test Phase 2: Streaming

Open your browser console and watch for:
- `delta` messages appearing incrementally
- `tool_call` events showing tool execution
- `tool_result` events with previews

### Test Phase 3: Hooks

Check your logs for:
```
INFO: 🔧 Pre-tool: analyze_canvas_app_formulas
INFO: ✅ Post-tool: analyze_canvas_app_formulas
INFO: 📊 Tool usage stats: {'analyze_canvas_app_formulas': 3, ...}
```

---

## Troubleshooting

### Issue: Tools not found by agent

**Solution:** Ensure you're importing and passing tools correctly:
```python
from copilot_tools import analyze_canvas_app_formulas
# Pass in session config
"tools": [analyze_canvas_app_formulas]  # Not as string!
```

### Issue: WebSocket not streaming

**Solution:** Verify `streaming: True` in config and event handler is registered:
```python
copilot_session.on(on_event)  # Must call this!
```

### Issue: Hooks not firing

**Solution:** Check config:
```python
COPILOT_ENABLE_HOOKS = True  # In config.py
```

---

## Next Steps

After completing Phase 1-3:

1. ✅ **Monitor logs** - Watch tool usage and agent behavior
2. ✅ **Test edge cases** - Upload complex solutions
3. ✅ **Gather metrics** - Track which tools are most useful
4. ✅ **Optimize prompts** - Adjust system message based on tool usage
5. ✅ **Move to Phase 4** - Implement advanced features

---

## Support & Resources

- **Copilot SDK Docs:** https://github.com/github/copilot-sdk
- **Python SDK README:** https://github.com/github/copilot-sdk/tree/main/python
- **Example Projects:** https://github.com/github/awesome-copilot

---

**Last Updated:** February 11, 2026  
**Version:** 1.0
