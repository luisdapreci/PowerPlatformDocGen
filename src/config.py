"""Configuration settings for Power Platform Documentation Generator"""
import os
import sys
import shutil
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent.parent  # Project root (one level up from src)
UPLOAD_DIR = BASE_DIR / "uploads"
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# File size limits
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_EXTRACTION_SIZE = 500 * 1024 * 1024  # 500 MB

# Screenshot/image settings
MAX_SCREENSHOT_SIZE = 10 * 1024 * 1024  # 10 MB per image
MAX_SCREENSHOTS_PER_SESSION = 20
ALLOWED_IMAGE_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}
ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

# Image optimization for faster AI vision analysis
# Images are resized on upload to reduce file size and speed up processing
IMAGE_MAX_DIMENSION = 1920  # Max width or height in pixels (maintains aspect ratio)
IMAGE_JPEG_QUALITY = 80     # JPEG compression quality (1-100)
IMAGE_WEBP_QUALITY = 80     # WebP compression quality (1-100)
IMAGE_PNG_OPTIMIZE = True   # Enable PNG optimization

# Session settings
SESSION_TIMEOUT = 60 * 60  # 60 minutes in seconds
MAX_CONCURRENT_SESSIONS = 10

# Power Platform CLI
# Support both traditional pac command and dnx approach (no installation required)
_pac_command = "pac.exe" if sys.platform == "win32" else "pac"
PAC_CLI_COMMAND = shutil.which(_pac_command) or _pac_command

# DNX approach (requires .NET 10+, no pac installation needed)
# On Windows, dnx is a .cmd file that needs to be invoked through cmd.exe
_dnx_path = shutil.which("dnx")
if _dnx_path and sys.platform == "win32":
    # On Windows, invoke .cmd files through cmd.exe for subprocess compatibility
    DNX_COMMAND = ["cmd", "/c", "dnx", "Microsoft.PowerApps.CLI.Tool", "--yes"]
else:
    DNX_COMMAND = ["dnx", "Microsoft.PowerApps.CLI.Tool", "--yes"]

USE_DNX = shutil.which(_pac_command) is None  # Use dnx if pac not installed

PAC_UNPACK_TIMEOUT = 300  # 5 minutes

# Copilot SDK settings
COPILOT_MODEL = "claude-sonnet-4.6"
COPILOT_STREAMING = True

# Documentation generation timeouts (in seconds)
DOC_GEN_FILE_TIMEOUT = 360  # 6 minutes per critical file
DOC_GEN_SCREENSHOT_TIMEOUT = 360  # 6 minutes per screenshot (vision analysis + write + embed)
DOC_GEN_SECTION_TIMEOUT = 360  # 6 minutes per documentation section (section-by-section generation)
DOC_GEN_FINAL_PASS_TIMEOUT = 480  # 8 minutes for the final formatting/gap-filling pass (explores files, fills many sections)
DOC_GEN_CONSOLIDATION_TIMEOUT = 600  # 10 minutes for final consolidation (deprecated - now using section-by-section)

# Quick mode timeouts (shorter for faster generation)
DOC_GEN_QUICK_FILE_TIMEOUT = 240      # 4 minutes per file batch (quick mode)
DOC_GEN_QUICK_SCREENSHOT_TIMEOUT = 180 # 3 minutes per screenshot (quick mode)
DOC_GEN_QUICK_SECTION_TIMEOUT = 240    # 4 minutes per merged section (quick mode)

# Quick mode file batching
QUICK_MODE_BATCH_MAX_CHARS = 12000  # Max combined content length for a file batch
QUICK_MODE_BATCH_MAX_FILES = 3      # Max files per batch
QUICK_MODE_SINGLE_FILE_THRESHOLD = 8000  # Files larger than this are not batched

# Custom tools configuration
COPILOT_ENABLE_CUSTOM_TOOLS = True

# Built-in tool security (whitelist approach)
# Set to None to allow all tools, or provide a list to restrict
COPILOT_ALLOWED_BUILTIN_TOOLS = [
    "read_file",
    "list_dir",
    "grep_search",
    "view",
    "replace_string_in_file",  # For incremental doc generation
    "multi_replace_string_in_file",  # For batch edits
    # Exclude "bash" for security in production
    # Exclude "web_request" if not needed
]

# Infinite sessions configuration
COPILOT_ENABLE_INFINITE_SESSIONS = True
COPILOT_COMPACTION_THRESHOLD = 0.75  # Start compacting at 75% context usage
COPILOT_BUFFER_THRESHOLD = 0.90  # Block at 90% until compaction completes

# Hooks configuration
COPILOT_ENABLE_HOOKS = False  # Enable in Phase 3

# Word Document Generation Configuration
DOCX_CONFIG = {
    # Company Information
    'company_name': 'Nextant Power Platform Documentation',
    'author': 'Nextant',

    # Company logo embedded in the markdown/docx (relative to project root, or None to skip)
    'logo_path': 'assets/company_logo.png',
    'logo_width_inches': 1.5,

    # Feature Toggles
    'enable_toc': False,  # Generate table of contents
    
    # Reference .docx for custom branding/styles (optional)
    # Create a styled .docx with custom fonts/colours, point to it here.
    # Relative path from project root, or None to use Pandoc default.
    'reference_doc': None,  # e.g. 'assets/reference.docx'
    
    # Highlight style for code blocks
    # Options: pygments, kate, monochrome, breezeDark, espresso, zenburn, haddock, tango
    'highlight_style': 'tango',
}

# Ensure directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
