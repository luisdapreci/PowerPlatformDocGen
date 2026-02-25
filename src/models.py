"""Data models for the application"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    EXTRACTED = "extracted"
    UNPACKING = "unpacking"
    ANALYZING = "analyzing"
    GENERATING_DOCS = "generating_docs"
    COMPLETED = "completed"
    FAILED = "failed"


class ComponentType(str, Enum):
    CANVAS_APP = "canvas_app"
    POWER_AUTOMATE = "power_automate"


class SolutionComponent(BaseModel):
    """Represents a component in the solution"""
    name: str
    path: str
    type: ComponentType
    display_name: str


class SolutionInfo(BaseModel):
    """Information about a Power Platform solution"""
    name: str
    version: str
    publisher: str
    description: Optional[str] = None
    canvas_apps: List[str] = []
    flows: List[str] = []
    tables: List[str] = []


class UploadResponse(BaseModel):
    """Response after file upload"""
    session_id: str
    filename: str
    status: AnalysisStatus
    message: str


class ComponentsListResponse(BaseModel):
    """Response with list of available components"""
    session_id: str
    components: List[SolutionComponent]
    message: str


class ComponentSelectionRequest(BaseModel):
    """Request to select components for analysis"""
    session_id: str
    selected_components: List[str] = Field(description="List of component paths")


class ComponentSelectionResponse(BaseModel):
    """Response after component selection"""
    session_id: str
    status: AnalysisStatus
    message: str
    selected_count: int


class AnalysisProgress(BaseModel):
    """Progress update during analysis"""
    session_id: str
    status: AnalysisStatus
    progress_percent: int
    current_step: str
    message: Optional[str] = None


class ChatMessage(BaseModel):
    """Chat message for interactive queries"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ChatRequest(BaseModel):
    """Request for chat query"""
    session_id: str
    message: str


class ChatResponse(BaseModel):
    """Response to chat query"""
    session_id: str
    message: str
    tool_calls: Optional[List[str]] = None


class DocumentationFiles(BaseModel):
    """Generated documentation files"""
    markdown_files: List[str]
    pdf_file: Optional[str] = None
    session_id: str


class GenerateDocsRequest(BaseModel):
    """Request to generate documentation"""
    session_id: str
    solution_name: Optional[str] = None
    project_description: Optional[str] = None
    business_context: Optional[str] = Field(None, description="Optional business context to guide documentation generation")
