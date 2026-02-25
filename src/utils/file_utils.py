"""File handling utilities"""
import asyncio
import zipfile
import shutil
from pathlib import Path
from typing import List, Optional
import uuid
import config


def generate_session_id() -> str:
    """Generate a unique session ID"""
    return str(uuid.uuid4())


def get_session_dir(session_id: str) -> Path:
    """Get the working directory for a session"""
    return config.TEMP_DIR / session_id


def get_output_dir(session_id: str) -> Path:
    """Get the output directory for a session"""
    output_dir = config.OUTPUT_DIR / session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


async def extract_zip(zip_path: Path, extract_to: Path) -> None:
    """
    Extract a ZIP file asynchronously
    
    Args:
        zip_path: Path to the ZIP file
        extract_to: Directory to extract to
    
    Raises:
        zipfile.BadZipFile: If the file is not a valid ZIP
        ValueError: If extraction would exceed size limits
    """
    def _extract():
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Check total uncompressed size
            total_size = sum(info.file_size for info in zip_ref.infolist())
            if total_size > config.MAX_EXTRACTION_SIZE:
                raise ValueError(f"Extraction size {total_size} exceeds limit {config.MAX_EXTRACTION_SIZE}")
            
            zip_ref.extractall(extract_to)
    
    # Run extraction in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _extract)


def find_msapp_files(directory: Path) -> List[Path]:
    """
    Find all .msapp files in a directory tree
    
    Args:
        directory: Root directory to search
    
    Returns:
        List of paths to .msapp files
    """
    return list(directory.rglob("*.msapp"))


def find_flow_files(directory: Path) -> List[Path]:
    """
    Find all Power Automate flow definition files
    
    Args:
        directory: Root directory to search
    
    Returns:
        List of paths to flow JSON files
    """
    workflows_dir = directory / "Workflows"
    if workflows_dir.exists():
        return list(workflows_dir.rglob("*.json"))
    return []


def cleanup_session(session_id: str) -> None:
    """
    Clean up all files for a session
    
    Args:
        session_id: Session ID to clean up
    """
    session_dir = get_session_dir(session_id)
    output_dir = get_output_dir(session_id)
    
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)
    
    # Keep output directory for downloads but could optionally clean up after time


def get_file_size(path: Path) -> int:
    """Get file size in bytes"""
    return path.stat().st_size


def is_valid_solution_structure(directory: Path) -> bool:
    """
    Check if directory contains a valid Power Platform solution structure
    
    Args:
        directory: Directory to check
    
    Returns:
        True if valid solution structure is found
    """
    # Look for solution.xml or other solution indicator files
    solution_xml = directory / "solution.xml"
    other_folder = directory / "Other"
    
    return solution_xml.exists() or other_folder.exists()
