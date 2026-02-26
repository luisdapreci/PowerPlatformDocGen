# PDF Generation Feature

## Overview

The documentation generator now supports downloading generated documentation as professionally-formatted PDF files with advanced features including table of contents, syntax highlighting, and custom styling.

## 🎨 Key Features

- **Automatic Table of Contents**: Generates clickable TOC from document headings
- **Syntax Highlighting**: Full code syntax highlighting with Pygments
- **Enhanced Markdown Support**: 
  - Tables with custom styling
  - Admonition boxes (Note, Warning, Tip, etc.)
  - Footnotes
  - Definition lists
  - Attributes on elements
- **Branded PDF Output**: Custom colors, company branding, and professional styling
- **On-Demand Generation**: PDFs are created when requested to save resources
- **Image Support**: Automatically processes and embeds images from markdown
- **Custom CSS**: Inject your own styles to customize appearance
- **Professional Formatting**: Headers, footers, page numbers, styled tables, code blocks
- **Pure Python**: Uses xhtml2pdf - works out of the box
- **Input Validation**: Robust error handling and config validation

## Installation Requirements

**All Platforms**: PDF generation works out of the box with xhtml2pdf (pure Python).

Just install the dependencies from [requirements.txt](../requirements.txt):

```bash
pip install -r requirements.txt
```

The PDF renderer uses:
- **markdown**: Convert markdown to HTML
- **xhtml2pdf**: Generate PDFs (pure Python, no external dependencies)
- **Pygments**: Syntax highlighting for code blocks

## Configuration

Edit [src/config.py](../src/config.py) to customize PDF branding and features:

```python
PDF_CONFIG = {
    # Brand Colors (hex format)
    'primary_color': '#4f6d8f',      # Main brand color
    'secondary_color': '#3f6d78',    # Secondary color
    'accent_color': '#5d9cac',       # Accent for highlights
    
    # Company Information
    'company_name': 'Your Company',  # Company name for header/cover
    'footer_text': 'Confidential',   # Footer text
    
    # Logo Settings
    'logo_path': 'assets/logo.png',  # Path to logo (None to disable)
    
    # Page Setup
    'page_size': 'A4',               # A4, Letter, or Legal
    
    # Feature Toggles
    'enable_toc': True,              # Generate table of contents
    'enable_page_numbers': True,     # Show page numbers in footer
    
    # Page Numbering
    'page_number_format': 'Page {page} of {total}',  # Page number format
    'page_number_position': 'bottom-center',          # Position in footer
    
    # Custom CSS (optional)
    'custom_css': '''
        /* Add your custom styles here */
        h1 { text-transform: uppercase; }
    ''',
}
```

### Configuration Options

#### Colors
- **primary_color**: Main brand color used for headings and headers
- **secondary_color**: Secondary color for subheadings
- **accent_color**: Accent color for borders, highlights, and links
- All colors must be in hex format (e.g., `#3498db`)

#### Company Information
- **company_name**: Displayed on cover page and in headers (max 100 chars)
- **footer_text**: Displayed in document footer (max 100 chars)

#### Logo
- **logo_path**: Path to logo image (relative to project root or absolute)
- Supported formats: PNG, JPG, JPEG, GIF, SVG
- Max file size: 5MB
- Logo is displayed on the cover page
- Set to `None` to disable logo

#### Page Setup
- **page_size**: Paper size for PDF
  - `'A4'`: Standard A4 (210 × 297 mm)
  - `'Letter'`: US Letter (8.5 × 11 inches)
  - `'Legal'`: US Legal (8.5 × 14 inches)

#### Features
- **enable_toc**: Generate automatic table of contents from headings
  - Creates a clickable TOC on a separate page
  - Automatically extracts all H1-H6 headings
  - Includes proper indentation and styling
  
- **enable_page_numbers**: Show page numbers in the footer
  - Set to `True` to display page numbers
  - Set to `False` to hide page numbers
  - Combines with footer text automatically

#### Page Numbering

- **page_number_format**: Format string for page numbers
  - Use `{page}` placeholder for current page number
  - Use `{total}` placeholder for total page count
  - Examples:
    - `'Page {page} of {total}'` → "Page 3 of 10"
    - `'{page} / {total}'` → "3 / 10"
    - `'{page}'` → "3"
  
- **page_number_position**: Position of page numbers in footer
  - `'bottom-center'`: Center of footer (default)
  - `'bottom-right'`: Right side of footer
  - `'bottom-left'`: Left side of footer

**Example configurations:**

```python
# Default: centered with full format
PDF_CONFIG = {
    'enable_page_numbers': True,
    'page_number_format': 'Page {page} of {total}',
    'page_number_position': 'bottom-center',
}

# Minimal: simple page count on right
PDF_CONFIG = {
    'enable_page_numbers': True,
    'page_number_format': '{page}',
    'page_number_position': 'bottom-right',
}

# No page numbers
PDF_CONFIG = {
    'enable_page_numbers': False,
}
```

- **custom_css**: Inject custom CSS styles
  - Override default styles
  - Extend functionality
  - Automatically sanitized for security


## Enhanced Markdown Features

The PDF renderer supports extended markdown syntax for richer documentation:

### Admonition Boxes

Create styled note, warning, and tip boxes:

```markdown
!!! note "Note Title"
    This is a note box with important information.
    It will be rendered with a blue theme.

!!! warning "Warning"
    This is a warning box.
    Rendered in yellow/orange theme.

!!! danger "Danger"
    Critical information.
    Rendered in red theme.

!!! tip "Pro Tip"
    Helpful tips and hints.
    Rendered in green theme.
```

### Code Blocks with Syntax Highlighting

Specify language for proper syntax highlighting:

````markdown
```python
def hello_world():
    """Example Python function."""
    print("Hello, World!")
    return True
```

```javascript
const greet = (name) => {
    console.log(`Hello, ${name}!`);
    return true;
};
```
````

**Supported languages**: Python, JavaScript, TypeScript, C#, Java, SQL, PowerShell, Bash, JSON, YAML, XML, HTML, CSS, Markdown, and more.

### Tables

Create professional tables:

```markdown
| Feature | Status | Priority |
|---------|--------|----------|
| PDF Export | ✅ Complete | High |
| TOC Generation | ✅ Complete | High |
| Syntax Highlighting | ✅ Complete | Medium |
```

### Definition Lists

```markdown
Term 1
:   Definition of term 1

Term 2
:   Definition of term 2
    with multiple paragraphs
```

### Footnotes

```markdown
This is a statement[^1] that needs a citation.

[^1]: This is the footnote text that will appear at the bottom.
```

### Images

Embed images in your documentation:

```markdown
![Alt text](path/to/image.png)
![Company Logo](assets/logo.png)
```

Images are automatically:
- Processed and validated
- Converted to appropriate format
- Sized to fit within page margins
- Centered and styled

## Usage

### From the Web Interface

1. Generate documentation as usual
2. On the completion screen, you'll see two download buttons:
   - **Download Markdown** - Original .md format
   - **Download PDF** - Rendered PDF with all enhancements

### From the API

**Download Markdown:**
```
GET /download/{session_id}/{filename}
```

**Download PDF:**
```
GET /download-pdf/{session_id}/{filename}
```

The PDF endpoint will:
1. Read the markdown file
2. Validate configuration and inputs
3. Convert to HTML with enhanced markdown extensions
4. Generate table of contents from headings
5. Apply syntax highlighting to code blocks
6. Inject branded styling and custom CSS
7. Render to high-quality PDF
8. Return the PDF file for download

### Programmatic Usage

```python
from src.utils.pdf_renderer import render_markdown_to_pdf
from src import config

# Basic usage
result = render_markdown_to_pdf(
    markdown_content="# My Documentation\n\nContent here...",
    output_path="output/document.pdf",
    config=config.PDF_CONFIG
)

if result['status'] == 'success':
    print(f"PDF created: {result['file_path']}")
    print(f"Size: {result['size_bytes']} bytes")
    print(f"Renderer: {result['renderer']}")
else:
    print(f"Error: {result['error']}")

# Custom configuration
custom_config = {
    'primary_color': '#2c3e50',
    'company_name': 'My Company',
    'enable_toc': True,
    'enable_line_numbers': True,
    'custom_css': 'h1 { color: red; }'
}

result = render_markdown_to_pdf(
    markdown_content=markdown_text,
    output_path="custom_document.pdf",
    config=custom_config
)
```

## File Structure

```
src/
  utils/
    pdf_renderer.py         # Enhanced PDF conversion with validation
                           # - render_markdown_to_pdf()
                           # - validate_pdf_config()
                           # - _process_images_in_markdown()
                           # - _generate_toc_from_html()
  config.py                # PDF_CONFIG with all options
  main.py                  # API endpoints for downloads
templates/
  pdf_template.html        # Professional HTML/CSS template
                           # - Syntax highlighting styles
                           # - TOC styles
                           # - Admonition box styles
                           # - Enhanced typography
static/
  index.html              # UI with download buttons
assets/
  company_logo.png        # Your company logo (optional)
```

## Customization

### Custom Styling

**Option 1: Via Configuration (Recommended)**

Add custom CSS through the configuration:

```python
PDF_CONFIG = {
    # ...other settings...
    'custom_css': '''
        /* Custom heading styles */
        h1 {
            text-transform: uppercase;
            letter-spacing: 2pt;
        }
        
        /* Custom table styling */
        table {
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        /* Custom code block styling */
        .codehilite {
            border-left: 6px solid #2c3e50;
        }
        
        /* Add your own classes */
        .highlight {
            background-color: yellow;
            padding: 2pt 6pt;
        }
    '''
}
```

**Option 2: Edit Template (Advanced)**

Modify [templates/pdf_template.html](../templates/pdf_template.html) to change:
- Page layout and margins
- Typography and fonts (using `@font-face`)
- Colors and branding elements
- Header/footer content and positioning
- Code syntax highlighting themes
- Table and image styles
- Custom page break rules

### Custom Logo

1. Place your logo image (PNG, JPG, SVG) in the `assets` folder
2. Update `PDF_CONFIG['logo_path']` with a relative path from project root
3. Logo will automatically appear on the cover page

**Best practices:**
- Use PNG with transparent background
- Recommended size: 200-400 pixels wide
- Max file size: 5MB
- High resolution for print quality

Example:
```python
PDF_CONFIG = {
    'logo_path': 'assets/company_logo.png',  # Relative path (recommended)
    # ... other settings
}
```

## Troubleshooting

### "cannot load library 'gobject-2.0-0'" Warning on Windows

**This is normal and can be ignored!** The system automatically falls back to xhtml2pdf for PDF generation when WeasyPrint's GTK libraries aren't available. Your PDFs will still be generated successfully with good quality.

**To use WeasyPrint** (optional, for best quality):
Follow the "Optional: WeasyPrint Installation" section above.

### PDF Generation Fails

**Check these common issues:**

1. **Empty markdown content**: Ensure your markdown file has content
2. **Invalid colors**: Use hex format (#RRGGBB) for all colors
3. **Logo not found**: Check the logo path is correct and file exists
4. **Large logo file**: Logo must be under 5MB
5. **Output directory**: Ensure write permissions for output directory

**Enable debug logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### PDF Generation Timeout

For very large documents (100+ pages):

**Option 1: Use command line download**
```bash
curl -o documentation.pdf http://localhost:8000/download-pdf/{session_id}/{filename}
```

**Option 2: Increase timeout**
Modify the timeout in your HTTP client or browser.

### Poor Quality Images in PDF

**Best practices for images:**
- Use high-resolution images (300 DPI for print)
- Use absolute paths or properly embedded images
- Supported paths:
  - Local: `![Logo](assets/logo.png)`
  - Absolute: `![Logo](C:/path/to/image.png)`
  - URLs: `![Logo](https://example.com/image.png)`
- Supported formats: PNG, JPG, JPEG, GIF, SVG

### Table of Contents Not Showing

**Ensure:**
1. `enable_toc: True` in config
2. Your markdown has headings (# H1, ## H2, etc.)
3. Headings have text content (not empty)

### Line Numbers Not Showing

**Line numbers only work with WeasyPrint.**
- Check if WeasyPrint is installed correctly
- xhtml2pdf doesn't support line numbers (limitation)
- Set `enable_line_numbers: False` to suppress warnings

### Custom CSS Not Applied

**Check:**
1. CSS syntax is valid
2. No `<script>` tags (removed for security)
3. No `javascript:` URLs (sanitized)
4. CSS size limit is 5000 characters
5. Use proper CSS selectors

**Example valid custom CSS:**
```python
'custom_css': '''
    h1 { color: #ff0000; }
    .custom { background: #f0f0f0; }
'''
```

### Custom Fonts Not Loading

Add `@font-face` rules in custom CSS:

```python
'custom_css': '''
    @font-face {
        font-family: 'CustomFont';
        src: url('file:///C:/Windows/Fonts/CustomFont.ttf');
    }
    body {
        font-family: 'CustomFont', 'Segoe UI', sans-serif;
    }
'''
```

**Note:** Font files must be accessible to the PDF renderer.

## Performance Notes

- **On-Demand Generation**: PDFs created when requested (not pre-generated)
- **Generation Time**: 
  - Small docs (< 10 pages): 1-2 seconds
  - Medium docs (10-50 pages): 2-5 seconds
  - Large docs (50+ pages): 5-15 seconds
- **File Size**: PDFs typically 2-4x larger than markdown
- **Caching**: PDFs cached in the session output directory
- **Automatic Fallback**: WeasyPrint → xhtml2pdf → Error

## PDF Renderer Comparison

| Feature | WeasyPrint | xhtml2pdf |
|---------|------------|-----------|
| Installation | Requires GTK libraries | Pure Python ✓ |
| Quality | Excellent (best) ⭐ | Good |
| CSS Support | Full CSS3 | Limited CSS2 |
| Line Numbers | ✅ Yes | ❌ No |
| Syntax Highlighting | ✅ Full color | ⚠️ Basic |
| Page Headers/Footers | ✅ Advanced @page | ⚠️ Basic |
| Table Styling | ✅ Complete | ⚠️ Limited |
| Windows Compatibility | Requires setup | ✅ No setup needed |
| Linux/macOS | ✅ Usually pre-installed | ✅ Works OOTB |
| **Recommended For** | Best quality PDFs | Quick setup, Windows |

**Recommendation**: Use WeasyPrint for production PDFs, xhtml2pdf for development/testing.

## Security Considerations

- ✅ Input validation on all configuration options
- ✅ Logo file size limits (5MB max)
- ✅ Custom CSS sanitization (removes scripts)
- ✅ Path validation for images and logos
- ✅ Color format validation (hex only)
- ⚠️ Server-side PDF generation (consider rate limiting)
- ⚠️ PDFs contain metadata (company name, date)
- ⚠️ Ensure proper authentication for sensitive documents

**For production deployments:**
1. Enable rate limiting on PDF endpoints
2. Validate and sanitize all markdown input
3. Use authentication/authorization
4. Consider watermarks for confidential docs
5. Monitor server resources (PDF generation is CPU-intensive)

## What's New in This Version

### ✨ New Features
- ✅ **Automatic Table of Contents**: Generated from headings with proper indentation
- ✅ **Syntax Highlighting**: Full Pygments-based highlighting with 100+ languages
- ✅ **Line Numbers**: Optional line numbers in code blocks (WeasyPrint)
- ✅ **Admonition Boxes**: Styled note, warning, tip, danger boxes
- ✅ **Enhanced Tables**: Better styling with headers and alternating rows
- ✅ **Image Processing**: Automatic image handling and embedding
- ✅ **Custom CSS Support**: Inject your own styles
- ✅ **Input Validation**: Robust config and input validation
- ✅ **Better Error Handling**: Clear error messages and logging
- ✅ **Enhanced Markdown**: Footnotes, definition lists, attributes

### 🔧 Improvements
- Better Unicode support for special characters
- Improved font handling
- Enhanced code block styling
- Better page break handling
- Optimized file size
- Faster rendering
- More professional default styling

### 📚 Documentation
- Comprehensive feature documentation
- Usage examples for all markdown features
- Troubleshooting guide
- Configuration reference
- Security considerations

## Future Enhancements

Planned improvements for future versions:
- [ ] PDF bookmarks for navigation
- [ ] Batch PDF generation for multiple files
- [ ] PDF watermarks (draft/confidential)
- [ ] Export to other formats (DOCX, HTML, EPUB)
- [ ] Mermaid diagram rendering
- [ ] Custom cover page templates
- [ ] Multiple color themes/presets
- [ ] PDF compression options
- [ ] TOC customization (depth, style)
- [ ] Progress callback for large documents

## Support

If you encounter issues:
1. Check the Troubleshooting section above
2. Enable debug logging to see detailed errors
3. Verify your configuration with examples
4. Check that all dependencies are installed
5. Review the test files in `tests/` folder

**Test your PDF setup:**
```bash
cd tests
python test_pdf_with_logo.py
python test_ascii_pdf.py
```

