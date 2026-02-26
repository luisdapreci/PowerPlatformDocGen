"""PDF rendering utility for converting markdown documentation to branded PDFs"""
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any
import logging

# Configure logging
logger = logging.getLogger(__name__)


def validate_pdf_config(config: Optional[Dict]) -> Dict[str, Any]:
    """
    Validate and sanitize PDF configuration.
    Returns a validated config dict with defaults filled in.
    """
    if config is None:
        config = {}
    
    validated = {}
    
    # Color validation (hex format)
    def validate_color(color: str, default: str) -> str:
        if not color:
            return default
        # Check if it's a valid hex color
        if re.match(r'^#[0-9A-Fa-f]{6}$', color):
            return color
        logger.warning(f"Invalid color format: {color}, using default: {default}")
        return default
    
    validated['primary_color'] = validate_color(config.get('primary_color', '#2c3e50'), '#2c3e50')
    validated['secondary_color'] = validate_color(config.get('secondary_color', '#34495e'), '#34495e')
    validated['accent_color'] = validate_color(config.get('accent_color', '#3498db'), '#3498db')
    
    # Text fields
    validated['company_name'] = config.get('company_name', 'Power Platform Documentation')[-100:]  # Limit length
    validated['footer_text'] = config.get('footer_text', 'Generated Documentation')[-100:]
    
    # Page size validation
    valid_page_sizes = ['A4', 'LETTER', 'LEGAL']
    page_size = config.get('page_size', 'A4').upper()
    validated['page_size'] = page_size if page_size in valid_page_sizes else 'A4'
    
    # Logo path validation
    logo_path = config.get('logo_path', None)
    if logo_path:
        if not os.path.isabs(logo_path):
            # Make relative to project root
            project_root = Path(__file__).parent.parent.parent
            logo_path = str(project_root / logo_path)
        
        if os.path.exists(logo_path):
            # Check file size (max 5MB)
            file_size = os.path.getsize(logo_path)
            if file_size > 5 * 1024 * 1024:
                logger.warning(f"Logo file too large ({file_size} bytes), skipping")
                validated['logo_path'] = None
            else:
                validated['logo_path'] = logo_path
        else:
            logger.warning(f"Logo file not found: {logo_path}")
            validated['logo_path'] = None
    else:
        validated['logo_path'] = None
    
    # Boolean flags
    validated['enable_toc'] = bool(config.get('enable_toc', True))
    validated['enable_page_numbers'] = bool(config.get('enable_page_numbers', True))
    
    # Page numbering format
    page_number_format = config.get('page_number_format', 'Page {page} of {total}')
    validated['page_number_format'] = str(page_number_format)[:50]  # Limit length
    
    # Page number position
    valid_positions = ['bottom-center', 'bottom-right', 'bottom-left']
    position = config.get('page_number_position', 'bottom-center')
    validated['page_number_position'] = position if position in valid_positions else 'bottom-center'
    
    # Custom CSS (sanitize potential security issues)
    custom_css = config.get('custom_css', '')
    if custom_css:
        # Basic sanitization - remove script tags and javascript
        custom_css = re.sub(r'<script[^>]*>.*?</script>', '', custom_css, flags=re.DOTALL | re.IGNORECASE)
        custom_css = re.sub(r'javascript:', '', custom_css, flags=re.IGNORECASE)
        validated['custom_css'] = custom_css[:5000]  # Limit size
    else:
        validated['custom_css'] = ''
    
    return validated


def render_markdown_to_pdf(
    markdown_content: str,
    output_path: str,
    config: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Convert markdown content to a branded PDF document using xhtml2pdf.
    
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
            - custom_css: Additional CSS styles to inject
            - enable_toc: Generate table of contents (default: True)
            - theme: Color theme preset (default: "default")
            
    Returns:
        Dict with status, file_path, and optional error message
    """
    # Validate inputs
    if not markdown_content or not markdown_content.strip():
        return {
            'status': 'error',
            'error': 'Markdown content is empty or invalid'
        }
    
    if not output_path:
        return {
            'status': 'error',
            'error': 'Output path is required'
        }
    
    # Ensure output directory exists
    output_dir = Path(output_path).parent
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {
            'status': 'error',
            'error': f'Failed to create output directory: {str(e)}'
        }
    
    # Validate and sanitize configuration
    try:
        config = validate_pdf_config(config)
    except Exception as e:
        logger.error(f"Config validation error: {str(e)}")
        return {
            'status': 'error',
            'error': f'Invalid configuration: {str(e)}'
        }
    
    # Render PDF using xhtml2pdf
    try:
        return _render_with_xhtml2pdf(markdown_content, output_path, config)
    except Exception as e:
        logger.error(f"PDF generation failed: {str(e)}")
        return {
            'status': 'error',
            'error': f'PDF generation failed: {str(e)}'
        }


def _process_images_in_markdown(markdown_content: str, base_path: Optional[Path] = None) -> str:
    """
    Process images in markdown to optimize for PDF rendering.
    Converts relative paths to absolute and handles image sizing.
    """
    if base_path is None:
        base_path = Path.cwd()
    
    # Pattern to match markdown images: ![alt](path)
    img_pattern = r'!\[([^\]]*)\]\(([^\)]+)\)'
    
    def replace_image(match):
        alt_text = match.group(1)
        img_path = match.group(2)
        
        # Skip if it's already a URL
        if img_path.startswith(('http://', 'https://', 'data:')):
            return match.group(0)
        
        # Convert relative path to absolute
        abs_path = base_path / img_path
        if abs_path.exists():
            return f'![{alt_text}](file:///{abs_path.as_posix()})'
        
        return match.group(0)
    
    return re.sub(img_pattern, replace_image, markdown_content)


def _generate_toc_from_html(html_content: str) -> str:
    """
    Generate a table of contents from HTML headings.
    Returns HTML for the TOC.
    """
    # Parse headings from HTML
    heading_pattern = r'<h([1-6])[^>]*>(.*?)</h\1>'
    headings = re.findall(heading_pattern, html_content, re.IGNORECASE | re.DOTALL)
    
    if not headings:
        return ""
    
    toc_html = ['<div class="table-of-contents">', '<h2>Table of Contents</h2>', '<ul class="toc-list">']
    
    for level, title in headings:
        # Remove HTML tags from title
        clean_title = re.sub(r'<[^>]+>', '', title).strip()
        if not clean_title:
            continue
        
        # Create a slug for the heading
        slug = re.sub(r'[^\w\s-]', '', clean_title.lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        
        indent_class = f'toc-level-{level}'
        toc_html.append(f'  <li class="{indent_class}"><a href="#{slug}">{clean_title}</a></li>')
    
    toc_html.append('</ul>')
    toc_html.append('</div>')
    toc_html.append('<div class="page-break"></div>')
    
    return '\n'.join(toc_html)


def _add_heading_ids(html_content: str) -> str:
    """
    Add ID attributes to headings for TOC linking.
    """
    def add_id(match):
        level = match.group(1)
        attrs = match.group(2) or ''
        title = match.group(3)
        
        # Skip if already has an ID
        if 'id=' in attrs:
            return match.group(0)
        
        # Generate ID from title
        clean_title = re.sub(r'<[^>]+>', '', title).strip()
        slug = re.sub(r'[^\w\s-]', '', clean_title.lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        
        return f'<h{level} id="{slug}"{attrs}>{title}</h{level}>'
    
    pattern = r'<h([1-6])([^>]*)>(.*?)</h\1>'
    return re.sub(pattern, add_id, html_content, flags=re.IGNORECASE | re.DOTALL)


def _get_syntax_highlighting_css() -> str:
    """
    Get CSS for syntax highlighting using Pygments.
    """
    try:
        from pygments.formatters import HtmlFormatter
        formatter = HtmlFormatter(style='friendly')
        return formatter.get_style_defs('.codehilite')
    except ImportError:
        # Fallback if pygments not available
        return ""


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
        custom_css = config.get('custom_css', '')
        enable_toc = config.get('enable_toc', True)
        enable_page_numbers = config.get('enable_page_numbers', True)
        page_number_format = config.get('page_number_format', 'Page {page} of {total}')
        page_number_position = config.get('page_number_position', 'bottom-center')
        
        # Process images in markdown
        base_path = Path(output_path).parent
        markdown_content = _process_images_in_markdown(markdown_content, base_path)
        
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
            'sane_lists',
            'admonition',
            'attr_list',
            'def_list',
            'footnotes',
            'md_in_html',
            'tables',
        ], extension_configs={
            'codehilite': {
                'css_class': 'codehilite',
            }
        })
        html_content = md.convert(markdown_content)
        
        # Add IDs to headings
        html_content = _add_heading_ids(html_content)
        
        # Generate table of contents if enabled
        toc_html = ''
        if enable_toc:
            toc_html = _generate_toc_from_html(html_content)
        
        # Inject TOC before main content
        content_with_toc = f'{toc_html}\n{html_content}'
        
        # Generate timestamp
        from datetime import datetime
        generation_date = datetime.now().strftime('%B %d, %Y')
        
        # Create simplified HTML for xhtml2pdf (doesn't support all CSS)
        # Add TOC styles
        toc_styles = '''
        .table-of-contents {
            page-break-after: always;
            margin-bottom: 20pt;
            padding: 15pt;
            border: 1px solid #ddd;
            background-color: #f9f9f9;
        }
        
        .table-of-contents h2 {
            color: ''' + primary_color + ''';
            margin-top: 0;
            margin-bottom: 15pt;
            border-left: none;
            padding-left: 0;
        }
        
        .toc-list {
            list-style: none;
            padding-left: 0;
        }
        
        .toc-list li {
            margin-bottom: 6pt;
        }
        
        .toc-list a {
            text-decoration: none;
            color: #333;
        }
        
        .toc-level-1 {
            font-weight: bold;
            font-size: 11pt;
            margin-top: 8pt;
        }
        
        .toc-level-2 {
            padding-left: 15pt;
            font-size: 10pt;
        }
        
        .toc-level-3 {
            padding-left: 30pt;
            font-size: 9pt;
        }
        
        .toc-level-4,
        .toc-level-5,
        .toc-level-6 {
            padding-left: 45pt;
            font-size: 9pt;
            color: #666;
        }
        
        /* Admonition styles */
        .admonition {
            padding: 10pt;
            margin: 12pt 0;
            border-left: 4px solid ''' + accent_color + ''';
            background-color: #f9f9f9;
            page-break-inside: avoid;
        }
        
        .admonition-title {
            font-weight: bold;
            margin-bottom: 6pt;
            color: ''' + primary_color + ''';
        }
        
        .admonition.note {
            border-left-color: #3498db;
            background-color: #e7f3ff;
        }
        
        .admonition.warning {
            border-left-color: #f39c12;
            background-color: #fff3cd;
        }
        
        .admonition.danger {
            border-left-color: #e74c3c;
            background-color: #ffe7e7;
        }
        
        .admonition.tip {
            border-left-color: #27ae60;
            background-color: #d4edda;
        }
        '''
        
        # Build footer content with page numbering
        footer_content_parts = []
        
        # Add footer text
        if footer_text:
            footer_content_parts.append(footer_text)
        
        # Add page numbers if enabled
        if enable_page_numbers:
            # Format page numbers using xhtml2pdf tags
            # Replace {page} with <pdf:pagenumber> and {total} with <pdf:pagecount>
            page_num_text = page_number_format.replace('{page}', '<pdf:pagenumber>').replace('{total}', '<pdf:pagecount>')
            footer_content_parts.append(page_num_text)
        
        # Join footer parts with separator
        footer_content = ' • '.join(footer_content_parts) if footer_content_parts else ''
        
        # Determine footer alignment based on position
        footer_align_map = {
            'bottom-left': 'left',
            'bottom-center': 'center',
            'bottom-right': 'right'
        }
        footer_align = footer_align_map.get(page_number_position, 'center')
        
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
            text-align: {footer_align};
        }}
        
        {toc_styles}
        {custom_css}
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
        {content_with_toc}
    </div>
    
    <div id="footerContent">
        {footer_content}
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
