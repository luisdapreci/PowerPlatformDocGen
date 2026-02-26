# Power Platform Documentation Generator

> **AI-powered documentation generator for Microsoft Power Platform solutions using GitHub Copilot SDK**

Automatically analyze and document Power Platform solutions including Canvas Apps, Power Automate flows, Model-driven Apps, and Dataverse customizations with the help of GitHub Copilot's AI capabilities.

## 🔑 Prerequisites at a Glance

Before you begin, ensure you have:

- ✅ **GitHub Copilot subscription** (or use BYOK with your own API keys)
- ✅ **GitHub CLI** installed and authenticated (`gh auth login`)
- ✅ **Python 3.10+** installed
- ✅ **Power Platform CLI** (pac or dnx)

See [Prerequisites](#prerequisites) for detailed installation instructions.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Development](#development)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## 🎯 Overview

The Power Platform Documentation Generator is a web-based application that leverages GitHub Copilot SDK to automatically analyze and document Microsoft Power Platform solutions. It extracts, parses, and documents complex Power Platform components with minimal manual effort.

**Key Capabilities:**
- Automated solution analysis and documentation generation
- Interactive chat interface for querying solution details
- Component-level selection for focused documentation
- Support for Canvas Apps with Power Fx formula extraction
- Power Automate flow analysis
- Real-time progress tracking via WebSocket
- PDF and Markdown output formats

---

## ✨ Features

### 🔍 Comprehensive Analysis
- **Canvas Apps**: Extract and document Power Fx formulas, data sources, screens, controls, and assets
- **Power Automate Flows**: Parse workflow JSON files to document triggers, actions, and logic
- **Solution Metadata**: Read solution.xml for versioning and publisher information
- **Data Connections**: Identify SharePoint, SQL, Dataverse, and custom connectors

### 🤖 AI-Powered Documentation
- **GitHub Copilot SDK Integration**: Leverages Claude Sonnet 4.5 model for intelligent analysis
  - Built on the official [GitHub Copilot SDK for Python](https://github.com/github/copilot-sdk/blob/main/python/README.md)
  - Authenticated via [GitHub CLI](https://cli.github.com/) or BYOK
  - Requires GitHub Copilot subscription (or BYOK with your own API keys)
- **Incremental Template Editing**: Generates documentation by progressively populating a template
- **Context-Aware**: Understands Power Platform architecture and best practices
- **Business Context**: Incorporates user-provided context for tailored documentation

### 🎨 User-Friendly Interface
- **Modern Web UI**: Clean, responsive interface built with HTML/CSS/JavaScript
- **Wizard Workflow**: Step-by-step process for uploading, selecting components, and generating docs
- **Real-Time Progress**: WebSocket-based live updates during analysis
- **Interactive Chat**: Ask questions about your solution components

### 🔧 Advanced Capabilities
- **Component Selection**: Choose specific apps or flows to document
- **Multiple Export Formats**: Download as Markdown or PDF
- **Session Management**: Maintain multiple concurrent analysis sessions
- **Auto Cleanup**: Automatic session expiration and temporary file cleanup

---

## 🏗️ Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                        Web Browser                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         index.html (Static Frontend)                  │   │
│  │  • Upload UI  • Component Selection  • Chat Interface │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                           ↕ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (main.py)               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Upload &   │  │  Component   │  │     Chat     │      │
│  │  Extraction  │  │  Selection   │  │   Handler    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                           ↕
┌─────────────────────────────────────────────────────────────┐
│              GitHub Copilot SDK (CopilotClient)             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  • Session Manager  • Documentation Generator        │   │
│  │  • Claude Sonnet 4.5  • Built-in File Tools          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                           ↕
┌─────────────────────────────────────────────────────────────┐
│                   Solution Analyzer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Canvas App  │  │   Flow       │  │  Solution    │      │
│  │   Parser     │  │  Parser      │  │  XML Reader  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                           ↕
┌─────────────────────────────────────────────────────────────┐
│           Power Platform CLI (pac.exe / dnx)                │
│              (Unpack .msapp Canvas Apps)                    │
└─────────────────────────────────────────────────────────────┘
```

### Key Modules

- **main.py**: FastAPI application with REST endpoints and WebSocket support
- **session_manager.py**: Manages Copilot SDK sessions with isolation and cleanup
- **doc_generator.py**: Dedicated documentation generation using incremental template editing
- **analyze_solution_detailed.py**: Parses Power Platform solution structures
- **models.py**: Pydantic data models for request/response validation
- **config.py**: Centralized configuration with environment-specific settings
- **utils/**: Helper modules for file operations and Power Platform CLI interaction

---

## 📦 Prerequisites

### Required Software

1. **Python 3.10+**
   - Download from [python.org](https://www.python.org/downloads/)
   - Ensure `python` is in your PATH
   - Verify installation: `python --version`

2. **GitHub Copilot Subscription**
   - A GitHub Copilot subscription is required (includes free tier with limited usage)
   - Alternatively, use BYOK (Bring Your Own Key) with your own API keys from OpenAI, Azure, or Anthropic
   - Sign up at [GitHub Copilot](https://github.com/features/copilot#pricing)

3. **GitHub CLI (gh)**
   - **Required**: For GitHub Copilot SDK authentication
   - Install from [cli.github.com](https://cli.github.com/)
   
   **Installation:**
   
   - **Windows**:
     ```bash
     winget install --id GitHub.cli
     # or
     choco install gh
     ```
   
   - **macOS**:
     ```bash
     brew install gh
     ```
   
   - **Linux**:
     ```bash
     # Debian/Ubuntu
     sudo apt install gh
     
     # Fedora/RHEL
     sudo dnf install gh
     ```
   
   **Authentication:**
   ```bash
   # Login to GitHub
   gh auth login
   
   # Verify authentication
   gh auth status
   ```

4. **GitHub Copilot SDK**
   - Installed automatically via `requirements.txt`
   - Requires authenticated GitHub CLI (see step 3)
   - Documentation: [GitHub Copilot Python SDK](https://github.com/github/copilot-sdk/blob/main/python/README.md)

5. **Power Platform CLI** (one of the following):
   - **Option A**: Traditional `pac` CLI
     ```bash
     dotnet tool install --global Microsoft.PowerApps.CLI.Tool
     ```
   - **Option B**: DNX (no installation, requires .NET 10+)
     ```bash
     dnx Microsoft.PowerApps.CLI.Tool --yes help
     ```
   - Download from: [https://aka.ms/PowerAppsCLI](https://aka.ms/PowerAppsCLI)

### System Requirements

- **OS**: Windows 10/11, macOS, or Linux
- **RAM**: 4 GB minimum, 8 GB recommended
- **Disk Space**: 500 MB for application + space for solution files
- **Network**: Internet connection for Copilot API calls

---

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/PowerPlatformDocGen.git
cd PowerPlatformDocGen
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

### 3. Activate Virtual Environment

**Windows:**
```bash
venv\Scripts\activate
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

### 4. Verify GitHub CLI Authentication

Before installing dependencies, ensure GitHub CLI is authenticated:

```bash
# Check authentication status
gh auth status

# If not authenticated, login
gh auth login

# Follow the prompts to authenticate via browser or token
```

**Important**: The GitHub Copilot SDK requires an authenticated GitHub CLI session to function.

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

### 6. Verify Installation

```bash
# Verify Copilot SDK installation
python -c "from copilot import CopilotClient; print('Copilot SDK installed successfully!')"

# Verify GitHub CLI authentication
gh auth status

# Verify Power Platform CLI (if installed)
pac help
# or
dnx Microsoft.PowerApps.CLI.Tool --yes help
```

---

## 🔐 GitHub Copilot SDK Setup

This application uses the official [GitHub Copilot SDK](https://github.com/github/copilot-sdk) which requires proper authentication.

### Requirements

1. **GitHub Copilot Subscription**
   - Any GitHub Copilot subscription (includes free tier with limited usage)
   - Or use BYOK (Bring Your Own Key) with OpenAI, Azure AI, or Anthropic API keys
   - See [GitHub Copilot pricing](https://github.com/features/copilot#pricing)

2. **GitHub CLI Authentication**
   ```bash
   # Install GitHub CLI (if not already installed)
   # Windows: winget install --id GitHub.cli
   # macOS:   brew install gh
   # Linux:   sudo apt install gh (or equivalent)
   
   # Authenticate with GitHub
   gh auth login
   
   # Verify authentication
   gh auth status
   ```

3. **Verify Setup**
   ```bash
   # Test Python SDK import
   python -c "from copilot import CopilotClient; print('✓ Copilot SDK ready')"
   ```

### How It Works

The GitHub Copilot SDK:
- Uses your authenticated GitHub CLI session (or BYOK)
- Makes API calls to GitHub Copilot services (or your configured provider)
- Leverages Claude Sonnet 4.5 model for AI analysis (default)
- Requires active internet connection
- Respects your organization's Copilot policies

### BYOK (Bring Your Own Key) - Alternative Option

You can use this application **without a GitHub Copilot subscription** by configuring your own API keys:

**Supported Providers:**
- OpenAI (GPT-4, etc.)
- Azure OpenAI
- Anthropic (Claude models)
- Local providers (Ollama, etc.)

**Setup:**
Modify `config.py` to add provider configuration:
```python
# Example BYOK configuration (add to config.py)
COPILOT_PROVIDER = {
    "type": "openai",
    "base_url": "https://api.openai.com/v1",
    "api_key": "your-api-key-here"
}
```

See [BYOK Documentation](https://github.com/github/copilot-sdk/blob/main/docs/auth/byok.md) for detailed setup instructions.

### SDK Documentation

For detailed SDK documentation, see:
- [Python SDK Documentation](https://github.com/github/copilot-sdk/blob/main/python/README.md)
- [Main SDK Documentation](https://github.com/github/copilot-sdk/blob/main/README.md)
- [Authentication Guide](https://github.com/github/copilot-sdk/blob/main/docs/auth/index.md)
- [BYOK Guide](https://github.com/github/copilot-sdk/blob/main/docs/auth/byok.md)

---

## ⚡ Quick Start

> **Important**: Before starting, ensure you have:
> - GitHub Copilot subscription (or BYOK with your own API keys)
> - GitHub CLI installed and authenticated (`gh auth login`) or BYOK configured
> - Power Platform CLI installed (or use dnx)

### Windows

1. **Authenticate with GitHub CLI:**
   ```bash
   gh auth login
   ```

2. **Run the startup script:**
   ```bash
   start.bat
   ```

3. **Open your browser:**
   Navigate to [http://localhost:8000](http://localhost:8000)

3. **Upload a solution:**
   - Export your Power Platform solution as an unmanaged solution (.zip)
   - Upload via the web interface
   - Select components to document
   - Add optional business context
   - Generate documentation

### macOS/Linux

1. **Authenticate with GitHub CLI:**
   ```bash
   gh auth login
   ```

2. **Make the script executable:**
   ```bash
   chmod +x start.sh
   ```

3. **Run the startup script:**
   ```bash
   ./start.sh
   ```

4. **Open your browser:**
   Navigate to [http://localhost:8000](http://localhost:8000)

### Manual Start

```bash
# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows

# Start the server
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📖 Usage

### Step-by-Step Workflow

#### 1. Export Power Platform Solution

In Power Platform:
- Go to **Solutions**
- Select your solution
- Click **Export**
- Choose **Unmanaged**
- Download the `.zip` file

#### 2. Upload Solution

- Open the web interface
- Click **Upload Solution**
- Select your exported `.zip` file
- Wait for extraction and unpacking

#### 3. Select Components

- Review the list of Canvas Apps and Power Automate flows
- Select components to document (or select all)
- Click **Next**

#### 4. Add Business Context (Optional)

- Provide project background, objectives, or specific documentation requirements
- This helps the AI generate more relevant documentation

#### 5. Generate Documentation

- Click **Generate Documentation**
- Monitor real-time progress
- Download the generated Markdown or PDF

#### 6. Interactive Chat (Optional)

- Ask questions about your solution
- Example queries:
  - "What data sources are used in the Sales App?"
  - "Explain the approval workflow logic"
  - "List all Power Fx formulas in the Inventory app"

### API Usage

You can also interact with the API directly:

```python
import requests

# Upload solution
with open('MySolution.zip', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/upload',
        files={'file': f}
    )
session_id = response.json()['session_id']

# Get components
response = requests.get(f'http://localhost:8000/components/{session_id}')
components = response.json()['components']

# Generate documentation
response = requests.post(
    f'http://localhost:8000/generate-docs',
    json={
        'session_id': session_id,
        'selected_components': [c['path'] for c in components],
        'business_context': 'This is a sales tracking application'
    }
)
```

---

## 📂 Project Structure

```
PowerPlatformDocGen/
├── src/                              # Source code
│   ├── __init__.py
│   ├── main.py                       # FastAPI application entry point
│   ├── config.py                     # Configuration settings
│   ├── models.py                     # Pydantic data models
│   ├── session_manager.py            # Copilot session management
│   ├── doc_generator.py              # Documentation generation logic
│   ├── analyze_solution_detailed.py  # Solution analysis and parsing
│   └── utils/                        # Utility modules
│       ├── __init__.py
│       ├── file_utils.py             # File operations
│       └── pac_cli.py                # Power Platform CLI wrapper
│
├── static/                           # Static web assets
│   └── index.html                    # Frontend UI
│
├── templates/                        # Documentation templates
│   └── DocumentationTemplate.md      # Markdown template
│
├── tests/                            # Test suite
│   ├── test_api_endpoints.py
│   ├── test_doc_generation_isolation.py
│   ├── test_integration_demo.py
│   └── ...
│
├── temp/                             # Temporary session files (auto-created)
├── uploads/                          # Uploaded solution files (auto-created)
├── output/                           # Generated documentation (auto-created)
│
├── requirements.txt                  # Python dependencies
├── start.bat                         # Windows startup script
├── start.sh                          # macOS/Linux startup script
├── IMPLEMENTATION_GUIDE.md           # SDK enhancement guide
├── workspace.code-workspace          # VS Code workspace
└── README.md                         # This file
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root (optional):

```env
# GitHub Copilot SDK Settings
COPILOT_MODEL=claude-sonnet-4.5
COPILOT_STREAMING=true

# GitHub CLI (automatically detected)
# Ensure 'gh auth login' is completed before starting

# Server Settings
HOST=0.0.0.0
PORT=8000

# File Size Limits
MAX_UPLOAD_SIZE=104857600  # 100 MB
MAX_EXTRACTION_SIZE=524288000  # 500 MB

# Session Management
SESSION_TIMEOUT=1800  # 30 minutes
MAX_CONCURRENT_SESSIONS=10

# Power Platform CLI
USE_DNX=false  # Set to true to use dnx instead of pac
```

> **Note**: GitHub authentication is handled through the GitHub CLI (`gh`). The application will use your authenticated GitHub session automatically.

### Configuration Options (config.py)

Key settings you can modify:

```python
# Timeouts
DOC_GEN_FILE_TIMEOUT = 180            # Per file analysis (seconds)
DOC_GEN_SECTION_TIMEOUT = 240         # Per documentation section (seconds)

# Copilot Settings
COPILOT_MODEL = "claude-sonnet-4.5"   # AI model to use
COPILOT_STREAMING = True               # Enable streaming responses
COPILOT_ENABLE_INFINITE_SESSIONS = True  # Context management

# Tool Access Control
COPILOT_ALLOWED_BUILTIN_TOOLS = [
    "read_file",
    "list_dir",
    "grep_search",
    "replace_string_in_file",
    "multi_replace_string_in_file"
]
```

---

## 🔌 API Endpoints

### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serve the web interface |
| `POST` | `/upload` | Upload a Power Platform solution ZIP |
| `GET` | `/components/{session_id}` | List available components in solution |
| `POST` | `/select-components` | Select components for documentation |
| `POST` | `/generate-docs` | Generate documentation for selected components |
| `GET` | `/download/{session_id}` | Download generated documentation |
| `POST` | `/chat` | Chat with AI about solution components |
| `DELETE` | `/session/{session_id}` | Clean up a session |

### WebSocket Endpoints

| Endpoint | Description |
|----------|-------------|
| `/ws/{session_id}` | Real-time progress updates during analysis |

### Example Request/Response

**Upload Solution:**
```json
POST /upload
Content-Type: multipart/form-data

Response:
{
  "session_id": "abc-123-def",
  "filename": "MySolution.zip",
  "status": "extracted",
  "message": "Solution extracted successfully"
}
```

**Generate Documentation:**
```json
POST /generate-docs
Content-Type: application/json

{
  "session_id": "abc-123-def",
  "selected_components": ["CanvasApps/SalesApp_src", "Workflows/ApprovalFlow.json"],
  "business_context": "Sales tracking and approval workflow",
  "include_formulas": true,
  "include_data_sources": true
}

Response:
{
  "session_id": "abc-123-def",
  "status": "completed",
  "documentation_path": "/download/abc-123-def",
  "message": "Documentation generated successfully"
}
```

---

## 🛠️ Development

### Setting Up Development Environment

1. **Install development dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-asyncio black flake8
   ```

2. **Enable hot reload:**
   ```bash
   uvicorn src.main:app --reload
   ```

3. **Run tests:**
   ```bash
   pytest tests/
   ```

### Code Style

- **Formatter**: Black
- **Linter**: Flake8
- **Type Hints**: Encouraged for all function signatures

```bash
# Format code
black src/

# Lint code
flake8 src/
```

### Adding New Features

1. **Custom Analysis Tools**: Extend `analyze_solution_detailed.py`
2. **New Endpoints**: Add routes in `main.py`
3. **Data Models**: Define in `models.py` using Pydantic
4. **Frontend Changes**: Modify `static/index.html`

### Debugging

Enable detailed logging:

```python
# In src/main.py or src/config.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## 🧪 Testing

### Test Suite

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_api_endpoints.py

# Run with coverage
pytest --cov=src tests/
```

### Available Tests

- `test_api_endpoints.py`: REST API functionality
- `test_doc_generation_isolation.py`: Documentation generation
- `test_integration_demo.py`: End-to-end workflow
- `test_custom_tools.py`: Copilot SDK tool integration
- `test_timeout_handling.py`: Timeout and error handling

### Manual Testing

Use the provided test scripts:

```bash
# Quick API test
python tests/quick_test.py

# Integration demo
python tests/test_integration_demo.py

# Setup verification
python tests/test_setup.py
```

---

## 🔧 Troubleshooting

### Common Issues

#### 1. GitHub Copilot Authentication Error

**Symptom**: "Authentication failed" or "Copilot client initialization failed"

**Solutions**:
- Verify GitHub Copilot subscription is active (or configure BYOK)
- Ensure GitHub CLI is installed: `gh --version`
- Authenticate with GitHub CLI: `gh auth login`
- Check authentication status: `gh auth status`
- Restart the application after authentication
- Alternatively, configure BYOK with your own API keys (no GitHub auth required)

**Note**: See the [Authentication Guide](https://github.com/github/copilot-sdk/blob/main/docs/auth/index.md) for all authentication options.

#### 2. Power Platform CLI Not Found

**Symptom**: "pac command not found" or unpacking fails

**Solutions**:
- Install pac CLI: `dotnet tool install --global Microsoft.PowerApps.CLI.Tool`
- Use dnx instead: Set `USE_DNX=true` in config
- Verify installation: `pac help` or `dnx Microsoft.PowerApps.CLI.Tool --yes help`

#### 3. Upload Fails with Large Files

**Symptom**: Upload timeout or memory error

**Solutions**:
- Increase `MAX_UPLOAD_SIZE` in `config.py`
- Use a smaller solution or remove unnecessary components
- Check available disk space in `temp/` directory

#### 4. Documentation Generation Timeout

**Symptom**: "Documentation generation timed out"

**Solutions**:
- Increase `DOC_GEN_SECTION_TIMEOUT` in `config.py`
- Select fewer components for documentation
- Check network connection (Copilot API calls)

#### 5. WebSocket Connection Fails

**Symptom**: No real-time progress updates

**Solutions**:
- Check browser console for errors
- Verify firewall settings allow WebSocket connections
- Try a different browser
- Disable browser extensions that might block WebSockets

#### 6. Copilot SDK Rate Limits

**Symptom**: "Rate limit exceeded" or slow responses

**Solutions**:
- GitHub Copilot has usage limits based on subscription tier
- Wait a few minutes before retrying
- Reduce the number of components being analyzed simultaneously
- Check your organization's Copilot usage dashboard

### Logging

Check detailed logs for troubleshooting:

```bash
# The application logs to console by default
# Look for ERROR or WARNING messages

# Example log output:
# 2026-02-20 10:30:45 - src.main - INFO - Starting Power Platform Documentation Generator
# 2026-02-20 10:30:46 - src.session_manager - INFO - Copilot client initialized
```

### Getting Help

- Check the [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) for advanced features
- Review test files in `tests/` for usage examples
- Check GitHub Issues for known problems
- Review Power Platform CLI documentation: [https://aka.ms/PowerAppsCLI](https://aka.ms/PowerAppsCLI)
- Review GitHub Copilot SDK documentation: [Python SDK](https://github.com/github/copilot-sdk/blob/main/python/README.md)

### Frequently Asked Questions

**Q: What GitHub Copilot subscription do I need?**  
A: Any GitHub Copilot subscription works, including the free tier (with limited usage). You can also use BYOK (Bring Your Own Key) with your own API keys from OpenAI, Azure, or Anthropic, which doesn't require a GitHub Copilot subscription.

**Q: Do I need to be online to use this tool?**  
A: Yes, the GitHub Copilot SDK makes API calls to GitHub's services, so an internet connection is required.

**Q: How do I know if my GitHub CLI is authenticated correctly?**  
A: Run `gh auth status` in your terminal. You should see "Logged in to github.com as [your-username]".

**Q: What if I don't have Power Platform CLI installed?**  
A: You can use the dnx approach (requires .NET 10+) which doesn't require installing pac globally, or you can analyze already-unpacked solutions.

**Q: Is my solution data sent to GitHub/Copilot?**  
A: Yes, when using GitHub authentication, code and content are sent to GitHub's Copilot service for analysis. With BYOK, data is sent to your configured provider (OpenAI, Azure, Anthropic). Ensure this complies with your organization's data policies.

---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

### Contribution Process

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes**
4. **Run tests**: `pytest tests/`
5. **Format code**: `black src/`
6. **Commit changes**: `git commit -m 'Add amazing feature'`
7. **Push to branch**: `git push origin feature/amazing-feature`
8. **Open a Pull Request**

### Code Standards

- Follow PEP 8 style guidelines
- Add type hints to function signatures
- Write docstrings for classes and functions
- Add tests for new features
- Update documentation as needed

### Areas for Contribution

- [ ] Support for Model-driven Apps analysis
- [ ] Additional PDF features (bookmarks, hyperlinks, custom headers)
- [ ] Multi-language documentation support
- [ ] Dataverse table relationship diagrams
- [ ] Custom connector documentation
- [ ] Plugin assembly analysis
- [ ] Business Process Flow documentation
- [ ] Improved error handling and validation
- [ ] Performance optimizations
- [ ] Docker containerization

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **GitHub Copilot SDK**: For enabling AI-powered analysis and documentation ([github.com/github/copilot-sdk](https://github.com/github/copilot-sdk))
- **GitHub CLI**: For seamless authentication and integration
- **Microsoft Power Platform**: For the low-code platform and CLI tools
- **FastAPI**: For the modern, fast web framework
- **xhtml2pdf**: For cross-platform PDF generation (pure Python)
- **Claude (Anthropic)**: For the Sonnet 4.5 model powering the analysis

---

## 📞 Support

- **Documentation**: See [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)
- **Issues**: [GitHub Issues](https://github.com/yourusername/PowerPlatformDocGen/issues)
- **GitHub Copilot SDK**: [Python SDK Docs](https://github.com/github/copilot-sdk/blob/main/python/README.md) | [Main SDK Docs](https://github.com/github/copilot-sdk/blob/main/README.md)
- **GitHub CLI**: [https://cli.github.com/](https://cli.github.com/)
- **Power Platform CLI**: [https://aka.ms/PowerAppsCLI](https://aka.ms/PowerAppsCLI)
- **GitHub Copilot**: [https://github.com/features/copilot](https://github.com/features/copilot)

---

## 🗺️ Roadmap

### Completed ✅
- Canvas App analysis and documentation
- Power Automate flow parsing
- Interactive chat interface
- Real-time progress tracking
- Component selection
- PDF and Markdown export
- Session management

### In Progress 🚧
- Performance optimization
- Enhanced error handling
- Improved UI/UX

### Planned 📅
- Model-driven App analysis
- Plugin assembly documentation
- Dataverse table documentation
- Power BI report integration
- Batch processing multiple solutions
- CI/CD integration
- Docker deployment
- Multi-user authentication

---

**Made with ❤️ and ☕ by the Power Platform Community**

*Last Updated: February 2026*
