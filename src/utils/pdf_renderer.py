"""PDF rendering utility for converting markdown documentation to branded PDFs"""
import os
from pathlib import Path
from typing import Optional, Dict, Any


def render_markdown_to_pdf(
    markdown_content: str,
    output_path: str,
    config: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Convert markdown content to a branded PDF document.
    
    Uses WeasyPrint if available (requires GTK on Windows).
    Falls back to xhtml2pdf for Windows compatibility.
    
    Args:
        markdown_content: The markdown text to convert
        output_path: Path where the PDF should be saved
        config: Optional configuration dict with branding settings:
            - primary_color: Main brand color (hex)
            - secondary_color: Secondary brand color (hex)
            - accent_color: Accent color for highlights (hex)
            - company_name: Company name for footer
            - logo_path: Path to company logo image (optional)
            - footer_text: Custom footer text (optional)
            - page_size: Page size (default: "A4")
            
    Returns:
        Dict with status, file_path, and optional error message
    """
    # First try WeasyPrint (best quality), then fall back to xhtml2pdf (Windows compatible)
    try:
        return _render_with_weasyprint(markdown_content, output_path, config)
    except Exception as weasy_error:
        try:
            return _render_with_xhtml2pdf(markdown_content, output_path, config)
        except Exception as xhtml_error:
            return {
                'status': 'error',
                'error': f'PDF generation failed. WeasyPrint error: {str(weasy_error)}. xhtml2pdf error: {str(xhtml_error)}'
            }


def _render_with_weasyprint(
    markdown_content: str,
    output_path: str,
    config: Optional[Dict] = None
) -> Dict[str, Any]:
    """Render PDF using WeasyPrint (requires GTK libraries)"""
    try:
        import markdown
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration
        
        # Use default config if none provided
        if config is None:
            config = {}
        
        # Get configuration values with defaults
        primary_color = config.get('primary_color', '#2c3e50')
        secondary_color = config.get('secondary_color', '#34495e')
        accent_color = config.get('accent_color', '#3498db')
        company_name = config.get('company_name', 'Power Platform Documentation')
        footer_text = config.get('footer_text', 'Generated Documentation')
        logo_path = config.get('logo_path', None)
        page_size = config.get('page_size', 'A4')
        
        # Convert markdown to HTML with extensions
        md = markdown.Markdown(extensions=[
            'extra',  # Includes tables, fenced_code, etc.
            'codehilite',  # Syntax highlighting
            'toc',  # Table of contents
            'nl2br',  # Newline to break
            'sane_lists'  # Better list handling
        ])
        html_content = md.convert(markdown_content)
        
        # Load HTML template
        template_path = Path(__file__).parent.parent.parent / "templates" / "pdf_template.html"
        
        if not template_path.exists():
            return {
                'status': 'error',
                'error': f'PDF template not found at {template_path}'
            }
        
        with open(template_path, 'r', encoding='utf-8') as f:
            html_template = f.read()
        
        # Prepare logo HTML if logo path provided
        logo_html = ''
        if logo_path:
            # Resolve relative paths from project root
            if not os.path.isabs(logo_path):
                from pathlib import Path
                project_root = Path(__file__).parent.parent.parent
                logo_path = str(project_root / logo_path)
            
            if os.path.exists(logo_path):
                # Convert image to base64 data URI for better compatibility
                import base64
                try:
                    with open(logo_path, 'rb') as img_file:
                        img_data = base64.b64encode(img_file.read()).decode('utf-8')
                        # Detect image type from extension
                        ext = os.path.splitext(logo_path)[1].lower()
                        mime_type = {
                            '.png': 'image/png',
                            '.jpg': 'image/jpeg',
                            '.jpeg': 'image/jpeg',
                            '.gif': 'image/gif',
                            '.svg': 'image/svg+xml'
                        }.get(ext, 'image/png')
                        
                        logo_html = f'<img src="data:{mime_type};base64,{img_data}" alt="Logo" class="logo">'
                except Exception:
                    # If image loading fails, just skip the logo
                    pass
        
        # Replace placeholders in template
        html_document = html_template.replace('{markdown_content}', html_content)
        html_document = html_document.replace('{primary_color}', primary_color)
        html_document = html_document.replace('{secondary_color}', secondary_color)
        html_document = html_document.replace('{accent_color}', accent_color)
        html_document = html_document.replace('{company_name}', company_name)
        html_document = html_document.replace('{footer_text}', footer_text)
        html_document = html_document.replace('{logo_html}', logo_html)
        html_document = html_document.replace('{page_size}', page_size.upper())
        
        # Generate timestamp
        from datetime import datetime
        generation_date = datetime.now().strftime('%B %d, %Y')
        html_document = html_document.replace('{generation_date}', generation_date)
        
        # Configure fonts for WeasyPrint
        font_config = FontConfiguration()
        
        # Create PDF from HTML
        html_obj = HTML(string=html_document, base_url=str(template_path.parent))
        html_obj.write_pdf(
            output_path,
            font_config=font_config
        )
        
        return {
            'status': 'success',
            'file_path': output_path,
            'size_bytes': os.path.getsize(output_path) if os.path.exists(output_path) else 0,
            'renderer': 'weasyprint'
        }
        
    except Exception as e:
        raise Exception(f'WeasyPrint rendering failed: {str(e)}')


def _render_with_xhtml2pdf(
    markdown_content: str,
    output_path: str,
    config: Optional[Dict] = None
) -> Dict[str, Any]:
    """Render PDF using xhtml2pdf (pure Python, Windows compatible)"""
    try:
        import markdown
        from xhtml2pdf import pisa
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        
        # Register DejaVu Sans Mono font for better Unicode support
        try:
            # Try to use system fonts that support box-drawing characters
            import os
            # Common font locations on Windows
            font_paths = [
                r'C:\Windows\Fonts\DejaVuSansMono.ttf',
                r'C:\Windows\Fonts\consola.ttf',  # Consolas
                r'C:\Windows\Fonts\cour.ttf',      # Courier New
            ]
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont('CustomMono', font_path))
                        break
                    except:
                        continue
        except Exception as e:
            # If font registration fails, continue with default fonts
            pass
        
        # Use default config if none provided
        if config is None:
            config = {}
        
        # Get configuration values with defaults
        primary_color = config.get('primary_color', '#2c3e50')
        secondary_color = config.get('secondary_color', '#34495e')
        accent_color = config.get('accent_color', '#3498db')
        company_name = config.get('company_name', 'Power Platform Documentation')
        footer_text = config.get('footer_text', 'Generated Documentation')
        logo_path = config.get('logo_path', None)
        
        # Prepare logo HTML if logo path provided
        logo_html = ''
        if logo_path:
            # Resolve relative paths from project root
            if not os.path.isabs(logo_path):
                project_root = Path(__file__).parent.parent.parent
                logo_path = str(project_root / logo_path)
            
            if os.path.exists(logo_path):
                # Convert image to base64 data URI for xhtml2pdf compatibility
                import base64
                try:
                    with open(logo_path, 'rb') as img_file:
                        img_data = base64.b64encode(img_file.read()).decode('utf-8')
                        # Detect image type from extension
                        ext = os.path.splitext(logo_path)[1].lower()
                        mime_type = {
                            '.png': 'image/png',
                            '.jpg': 'image/jpeg',
                            '.jpeg': 'image/jpeg',
                            '.gif': 'image/gif',
                            '.svg': 'image/svg+xml'
                        }.get(ext, 'image/png')
                        
                        logo_html = f'<img src="data:{mime_type};base64,{img_data}" alt="Logo" width="100" style="height: auto; margin-bottom: 20px; display: block;" />'
                except Exception as e:
                    # If image loading fails, just skip the logo
                    pass
        
        # Preprocess markdown to fix box-drawing characters for better PDF rendering
        # Replace Unicode box-drawing characters with simple ASCII that renders reliably
        markdown_content = markdown_content.replace('─', '-')  # Box drawing horizontal
        markdown_content = markdown_content.replace('│', '|')  # Box drawing vertical
        markdown_content = markdown_content.replace('┌', '+')  # Box drawing top-left
        markdown_content = markdown_content.replace('┐', '+')  # Box drawing top-right
        markdown_content = markdown_content.replace('└', '+')  # Box drawing bottom-left
        markdown_content = markdown_content.replace('┘', '+')  # Box drawing bottom-right
        markdown_content = markdown_content.replace('├', '+')  # Box drawing left T
        markdown_content = markdown_content.replace('┤', '+')  # Box drawing right T
        markdown_content = markdown_content.replace('┬', '+')  # Box drawing top T
        markdown_content = markdown_content.replace('┴', '+')  # Box drawing bottom T
        markdown_content = markdown_content.replace('┼', '+')  # Box drawing cross
        
        # Convert markdown to HTML with extensions
        md = markdown.Markdown(extensions=[
            'extra',
            'codehilite',
            'toc',
            'nl2br',
            'sane_lists'
        ])
        html_content = md.convert(markdown_content)
        
        # Generate timestamp
        from datetime import datetime
        generation_date = datetime.now().strftime('%B %d, %Y')
        
        # Create simplified HTML for xhtml2pdf (doesn't support all CSS)
        html_document = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{company_name}</title>
    <style>
        @page {{
            size: a4;
            margin: 2cm;
            @frame footer {{
                -pdf-frame-content: footerContent;
                bottom: 1cm;
                margin-left: 2cm;
                margin-right: 2cm;
                height: 1cm;
            }}
        }}
        
        body {{
            font-family: Arial, Helvetica, sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #333;
        }}
        
        h1 {{
            font-size: 24pt;
            color: {primary_color};
            margin-top: 20pt;
            margin-bottom: 12pt;
            padding-bottom: 6pt;
            border-bottom: 3px solid {accent_color};
            page-break-after: avoid;
        }}
        
        h2 {{
            font-size: 18pt;
            color: {primary_color};
            margin-top: 18pt;
            margin-bottom: 10pt;
            padding-left: 8pt;
            border-left: 4px solid {accent_color};
            page-break-after: avoid;
        }}
        
        h3 {{
            font-size: 14pt;
            color: {secondary_color};
            margin-top: 14pt;
            margin-bottom: 8pt;
            page-break-after: avoid;
        }}
        
        h4, h5, h6 {{
            font-size: 12pt;
            color: {secondary_color};
            margin-top: 12pt;
            margin-bottom: 6pt;
            page-break-after: avoid;
        }}
        
        p {{
            margin-bottom: 8pt;
        }}
        
        ul, ol {{
            margin-bottom: 10pt;
            margin-left: 15pt;
        }}
        
        li {{
            margin-bottom: 4pt;
        }}
        
        code {{
            font-family: 'Courier New', Courier, monospace;
            font-size: 9pt;
            background-color: #f4f4f4;
            padding: 2pt 4pt;
            color: #c7254e;
        }}
        
        pre {{
            background-color: #f8f8f8;
            border: 1px solid #ddd;
            border-left: 4px solid {accent_color};
            padding: 10pt;
            margin-bottom: 12pt;
            page-break-inside: avoid;
            font-family: 'Courier', monospace;
            font-size: 8pt;
            line-height: 1.1;
            white-space: pre;
            overflow-x: visible;
            letter-spacing: 0;
            word-spacing: 0;
        }}
        
        pre code {{
            background-color: transparent;
            padding: 0;
            color: #333;
            font-family: 'Courier', monospace;
            font-size: 8pt;
            line-height: 1.1;
            letter-spacing: 0;
            word-spacing: 0;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 12pt;
            page-break-inside: avoid;
            font-size: 10pt;
        }}
        
        th {{
            background-color: {primary_color};
            color: white;
            padding: 8pt;
            text-align: left;
            border: 1px solid #ddd;
        }}
        
        td {{
            padding: 6pt 8pt;
            border: 1px solid #ddd;
        }}
        
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        blockquote {{
            margin: 12pt 0;
            padding: 8pt 12pt;
            background-color: #f9f9f9;
            border-left: 5px solid {accent_color};
            font-style: italic;
            color: #555;
        }}
        
        hr {{
            border: none;
            border-top: 2px solid {accent_color};
            margin: 15pt 0;
            opacity: 0.5;
        }}
        
        a {{
            color: {accent_color};
            text-decoration: none;
        }}
        
        .cover-page {{
            text-align: center;
            padding-top: 100pt;
            page-break-after: always;
        }}
        
        .cover-title {{
            font-size: 32pt;
            font-weight: bold;
            color: {primary_color};
            margin-bottom: 20pt;
        }}
        
        .cover-subtitle {{
            font-size: 18pt;
            color: {secondary_color};
            margin-bottom: 40pt;
        }}
        
        .cover-info {{
            font-size: 12pt;
            color: #666;
            margin-top: 60pt;
        }}
        
        #footerContent {{
            font-size: 9pt;
            color: #666;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="cover-page">
        {logo_html}
        <h1 class="cover-title">{company_name}</h1>
        <p class="cover-subtitle">Technical Documentation</p>
        <div class="cover-info">
            <p>Generated: {generation_date}</p>
        </div>
    </div>
    
    <div class="content">
        {html_content}
    </div>
    
    <div id="footerContent">
        {footer_text}
    </div>
</body>
</html>'''
        
        # Generate PDF with better Unicode support
        from io import BytesIO
        
        with open(output_path, 'wb') as pdf_file:
            pisa_status = pisa.CreatePDF(
                html_document,
                dest=pdf_file,
                encoding='utf-8',
                default_css=None
            )
        
        if pisa_status.err:  # type: ignore
            raise Exception(f'xhtml2pdf rendering had errors')
        
        return {
            'status': 'success',
            'file_path': output_path,
            'size_bytes': os.path.getsize(output_path) if os.path.exists(output_path) else 0,
            'renderer': 'xhtml2pdf'
        }
        
    except Exception as e:
        raise Exception(f'xhtml2pdf rendering failed: {str(e)}')
