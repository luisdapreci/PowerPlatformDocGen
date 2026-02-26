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

# Session settings
SESSION_TIMEOUT = 30 * 60  # 30 minutes in seconds
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
COPILOT_MODEL = "claude-sonnet-4.5"
COPILOT_STREAMING = True

# Documentation generation timeouts (in seconds)
DOC_GEN_FILE_TIMEOUT = 180  # 3 minutes per critical file
DOC_GEN_SECTION_TIMEOUT = 240  # 4 minutes per documentation section (section-by-section generation)
DOC_GEN_CONSOLIDATION_TIMEOUT = 600  # 10 minutes for final consolidation (deprecated - now using section-by-section)

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

# PDF Generation Configuration
PDF_CONFIG = {
    # Brand Colors (hex format)
    'primary_color': '#4f6d8f',  # Microsoft Blue
    'secondary_color': '#3f6d78',  # Darker Blue
    'accent_color': '#5d9cac',  # Light Blue
    
    # Company Information
    'company_name': 'Nextant Power Platform Documentation',
    'footer_text': 'Confidential - Internal Use Only',
    
    # Logo Settings
    'logo_path': 'assets/company_logo.png',  # Relative path from project root (or None to disable)
    
    # Page Setup
    'page_size': 'A4',  # Options: A4, Letter, Legal
    
    # Feature Toggles
    'enable_toc': False,  # Generate table of contents
    'enable_page_numbers': True,  # Show page numbers in footer
    
    # Page Numbering
    'page_number_format': 'Page {page} of {total}',  # Options: 'Page {page} of {total}', '{page} / {total}', '{page}', etc.
    'page_number_position': 'bottom-center',  # Options: bottom-center, bottom-right, bottom-left
    
    # Custom CSS (optional)
    # Add custom CSS to override or extend default styles
    'custom_css': '''
        /* You can add custom CSS here */
        /* Example: 
        h1 { text-transform: uppercase; }
        .custom-class { color: red; }
        */
    ''',
    
    # Advanced Options
    'theme': 'default',  # Future use: support for different color themes
}

# Ensure directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
