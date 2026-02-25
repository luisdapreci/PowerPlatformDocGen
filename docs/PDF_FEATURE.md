# PDF Generation Feature

## Overview

The documentation generator now supports downloading generated documentation as professionally-formatted PDF files in addition to Markdown format.

## Features

- **Branded PDF Output**: Custom colors, company branding, and professional styling
- **On-Demand Generation**: PDFs are created when requested to save resources
- **Two Download Options**: Users can choose between Markdown (.md) or PDF (.pdf) formats
- **Professional Formatting**: Includes headers, footers, page numbers, styled tables, code blocks, and more
- **Automatic Fallback**: Uses WeasyPrint if available (best quality), automatically falls back to xhtml2pdf on Windows

## Installation Requirements

**Windows Users**: PDF generation works out of the box with xhtml2pdf (no additional installation required).

**Linux/macOS Users**: For better quality PDFs, optionally install GTK for WeasyPrint support.

### Optional: WeasyPrint Installation (Higher Quality PDFs)

WeasyPrint requires GTK libraries to be installed on Windows:

1. **Option 1: Using GTK Installer**
   - Download GTK3 runtime from: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
   - Run the installer and select all components
   - Add GTK bin directory to your system PATH (usually `C:\Program Files\GTK3-Runtime Win64\bin`)

2. **Option 2: Using MSYS2**
   ```powershell
   # Install MSYS2 from https://www.msys2.org/
   # Then in MSYS2 terminal:
   pacman -S mingw-w64-x86_64-gtk3 mingw-w64-x86_64-python-gobject
   ```

3. **Verify Installation**
   ```powershell
   python -c "from weasyprint import HTML; print('WeasyPrint OK')"
   ```

### Linux/macOS

WeasyPrint dependencies are usually available through package managers:

**Ubuntu/Debian:**
```bash
sudo apt-get install python3-cffi python3-brotli libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi-dev
```

**macOS:**
```bash
brew install python cairo pango gdk-pixbuf libffi
```

**Alpine Linux (Docker):**
```dockerfile
RUN apk add --no-cache \
    python3 \
    py3-pip \
    cairo \
    pango \
    gdk-pixbuf \
    libffi-dev \
    harfbuzz \
    ttf-freefont
```

## Configuration

Edit `src/config.py` to customize PDF branding:

```python
PDF_CONFIG = {
    'primary_color': '#0078D4',      # Main brand color
    'secondary_color': '#2B579A',    # Secondary color
    'accent_color': '#00BCF2',       # Accent for highlights
    'company_name': 'Your Company',   # Company name
    'footer_text': 'Confidential',   # Footer text
    'logo_path': '/path/to/logo.png', # Optional logo (None to disable)
    'page_size': 'A4',               # A4, Letter, or Legal
}
```

## Usage

### From the Web Interface

1. Generate documentation as usual
2. On the completion screen, you'll see two download buttons:
   - **Download Markdown** - Original .md format
   - **Download PDF** - Rendered PDF with branding

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
2. Convert to HTML with syntax highlighting
3. Apply branded styling
4. Render to PDF on-demand
5. Return the PDF file

## File Structure

```
src/
  utils/
    pdf_renderer.py         # PDF conversion logic
  config.py                 # PDF_CONFIG settings
  main.py                   # API endpoints
templates/
  pdf_template.html         # HTML/CSS template for PDFs
static/
  index.html               # Updated UI with two download buttons
```

## Customization

### Custom Styling

Edit `templates/pdf_template.html` to modify:
- Page layout and margins
- Typography and fonts
- Colors and branding elements
- Header/footer content
- Code syntax highlighting
- Table styles

### Custom Logo

1. Place your logo image (PNG, JPG, SVG) in the `assets` folder
2. Update `PDF_CONFIG['logo_path']` with a relative path from project root
3. Logo will appear on the cover page

Example:
```python
PDF_CONFIG = {
    'logo_path': 'assets/company_logo.png',  # Relative path (recommended)
    # ... other settings
}
```

## Troubleshooting

### "cannot load library 'gobject-2.0-0'" Warning on Windows

**This is normal and can be ignored!** The system automatically falls back to xhtml2pdf for PDF generation when WeasyPrint's GTK libraries aren't available. Your PDFs will still be generated successfully.

If you want to use WeasyPrint for higher quality PDFs (optional), follow the installation steps in the "Optional: WeasyPrint Installation" section above.

### PDF Generation Timeout

For very large documents, increase the timeout in your browser or use:
```bash
# Download via command line
curl -o documentation.pdf http://localhost:8000/download-pdf/{session_id}/{filename}
```

### Poor Quality Images in PDF

Ensure images referenced in markdown use absolute paths or are properly embedded. WeasyPrint supports:
- Local file paths: `file:///path/to/image.png`
- Web URLs: `https://example.com/image.png`
- Data URIs: `data:image/png;base64,...`

### Custom Fonts

To use custom fonts in PDFs, add `@font-face` rules in `templates/pdf_template.html`:

```html
<style>
@font-face {
    font-family: 'CustomFont';
    src: url('file:///path/to/font.ttf');
}
body {
    font-family: 'CustomFont', sans-serif;
}
</style>
```

## Performance Notes

- **On-Demand Generation**: PDFs are created when requested, not pre-generated
- **Generation Time**: Typically 2-5 seconds for standard documentation
- **File Size**: PDFs are usually 2-3x larger than markdown files
- **Caching**: PDFs are cached in the session output directory for repeat downloads
- **Automatic Fallback**: System tries WeasyPrint first (if available), then falls back to xhtml2pdf

## PDF Renderer Comparison

| Feature | WeasyPrint | xhtml2pdf |
|---------|------------|-----------|
| Installation | Requires GTK libraries | Pure Python (no dependencies) |
| Quality | Excellent (best) | Good |
| CSS Support | Full CSS3 | Limited CSS2 |
| Page Headers/Footers | Advanced (@page rules) | Basic |
| Windows Compatibility | Requires setup | Works out of the box ✓ |
| Linux/macOS | Usually pre-installed | Works out of the box ✓ |

## Security Considerations

- PDFs are generated server-side using user-provided markdown content
- Ensure proper input validation if exposing this endpoint publicly
- Consider rate limiting for PDF generation to prevent abuse
- PDFs may contain metadata (generation date, company name, etc.)

## Future Enhancements

Potential improvements for future versions:
- Pre-generated PDFs during doc generation (faster downloads)
- PDF watermarks for draft/confidential documents
- Interactive table of contents with clickable links
- Export to other formats (DOCX, HTML)
- Batch PDF generation for multiple components
