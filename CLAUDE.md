# Power Platform Documentation Generator - Claude Guide

## Project Overview

AI-powered documentation generator for Microsoft Power Platform solutions. Uses GitHub Copilot SDK (Claude Sonnet 4.5) to analyze and document Canvas Apps, Power Automate flows, Model-driven Apps, and Dataverse customizations via a FastAPI web application.

## Development Commands

### Install Dependencies
```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio  # for running tests
```

### Run the Application
```bash
python3 src/main.py
# App available at: http://localhost:8000/static/index.html
```

### Run Tests
```bash
# Run a single test file (most tests require asyncio mode)
python3 -m pytest tests/test_phase1.py -q --asyncio-mode=auto

# Run all tests
python3 -m pytest tests/ -q --asyncio-mode=auto

# Note: Tests that connect to Copilot SDK or a running server need GitHub Copilot CLI authenticated
```

## Project Structure

```
PowerPlatformDocGen/
├── src/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # App configuration (models, timeouts, PDF settings)
│   ├── models.py            # Pydantic models
│   ├── doc_generator.py     # Documentation generation logic
│   ├── session_manager.py   # Session lifecycle management
│   ├── analyze_solution_detailed.py  # Power Platform solution analyzer
│   └── utils/
│       ├── file_utils.py    # File helpers (zip, msapp, session dirs)
│       ├── pac_cli.py       # Power Platform CLI wrapper
│       └── pdf_renderer.py  # Markdown → PDF conversion
├── tests/                   # Test suite (pytest + asyncio)
├── static/                  # Frontend HTML/CSS/JS
├── templates/               # Documentation templates
├── assets/                  # Static assets (logos, etc.)
├── requirements.txt         # Python dependencies
├── start.sh                 # Unix quickstart script
└── start.bat                # Windows quickstart script
```

## Key Configuration (`src/config.py`)

- `COPILOT_MODEL`: AI model used (`claude-sonnet-4.5`)
- `MAX_UPLOAD_SIZE`: 100 MB max solution zip upload
- `SESSION_TIMEOUT`: 30 minutes per session
- `PAC_CLI_COMMAND`: Auto-detects `pac` or `dnx` CLI
- `PDF_CONFIG`: PDF styling (company name, colors, logo path)
- `COPILOT_ALLOWED_BUILTIN_TOOLS`: Whitelisted Copilot tools for security

## API Endpoints (FastAPI)

- `POST /upload` — Upload a Power Platform solution zip
- `GET /components/{session_id}` — List solution components
- `POST /generate` — Generate documentation for selected components
- `POST /chat` — Chat with the AI about the solution
- `WS /ws/{session_id}` — WebSocket for real-time progress
- `GET /download/{session_id}/{format}` — Download docs (markdown/pdf)
- `POST /convert-to-pdf` — Convert any markdown file to PDF

## External Dependencies

- **GitHub Copilot CLI**: Required for AI features. Install from [GitHub Copilot CLI docs](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli) and authenticate with `gh auth login`.
- **Power Platform CLI** (`pac` or `dnx`): Required for `.msapp` unpacking. Install via `dotnet tool install --global Microsoft.PowerApps.CLI.Tool` or use `dnx` (requires .NET 10+).

## Environment Variables

Copy `.env.example` to `.env` to customize:
- `LOG_LEVEL` (default: INFO)
- `COPILOT_MODEL` (default: claude-sonnet-4.5)
- `HOST` / `PORT` (default: 0.0.0.0:8000)

## Notes

- Sessions auto-expire after 30 minutes; uploaded files are cleaned up on session delete or page unload
- The app supports concurrent sessions (max 10 by default)
- PDF generation uses `xhtml2pdf` with `svglib` — if installing fails, run `pip install --upgrade pip setuptools --ignore-installed` first
