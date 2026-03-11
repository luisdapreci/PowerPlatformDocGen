"""Word document rendering utility for converting markdown documentation to branded .docx files via Pandoc"""
import os
import base64
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


def prepend_logo_to_markdown(content: str, logo_path: str, width_inches: float = 1.5) -> str:
    """
    Prepend a base64-encoded logo image to markdown content so the file is
    self-contained and the logo is rendered in both .md viewers and .docx exports.

    Args:
        content: Existing markdown text
        logo_path: Absolute (or project-relative) path to the logo image
        width_inches: Rendered width in the final document (Pandoc attribute)

    Returns:
        Markdown string with the logo prepended, or the original content if the
        logo file cannot be found/read.
    """
    if not logo_path:
        return content

    # Resolve relative paths from project root
    resolved = Path(logo_path) if os.path.isabs(logo_path) else Path(__file__).parent.parent.parent / logo_path
    if not resolved.exists():
        logger.warning(f"Logo not found at {resolved}, skipping logo injection")
        return content

    try:
        raw = resolved.read_bytes()
        b64 = base64.b64encode(raw).decode('ascii')
        # Infer MIME type from extension
        ext = resolved.suffix.lower().lstrip('.')
        mime = 'image/png' if ext == 'png' else f'image/{ext}'
        data_uri = f'data:{mime};base64,{b64}'
        # Wrap in a Pandoc fenced div mapped to Word's "Figure" style (centered by default)
        logo_tag = (
            f'::: {{custom-style="Figure"}}\n'
            f'![]({data_uri}){{width={width_inches}in}}\n'
            f':::'
        )
        return logo_tag + '\n\n' + content
    except Exception as e:
        logger.warning(f"Failed to embed logo: {e}")
        return content


def validate_docx_config(config: Optional[Dict]) -> Dict[str, Any]:
    """Validate and sanitize Word document configuration."""
    if config is None:
        config = {}

    validated: Dict[str, Any] = {}

    validated['company_name'] = str(config.get('company_name', 'Power Platform Documentation'))[:100]
    validated['author'] = str(config.get('author', ''))[:100]
    validated['enable_toc'] = bool(config.get('enable_toc', True))

    # Optional reference .docx for custom styles/branding
    reference_doc = config.get('reference_doc', None)
    if reference_doc:
        if not os.path.isabs(reference_doc):
            project_root = Path(__file__).parent.parent.parent
            reference_doc = str(project_root / reference_doc)
        if os.path.exists(reference_doc):
            validated['reference_doc'] = reference_doc
        else:
            logger.warning(f"Reference doc not found: {reference_doc}, using Pandoc default")
            validated['reference_doc'] = None
    else:
        validated['reference_doc'] = None

    # Code block highlight style
    valid_styles = {'pygments', 'kate', 'monochrome', 'breezeDark', 'espresso', 'zenburn', 'haddock', 'tango'}
    style = config.get('highlight_style', 'tango')
    validated['highlight_style'] = style if style in valid_styles else 'tango'

    return validated


def render_markdown_to_docx(
    markdown_content: str,
    output_path: str,
    config: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Convert markdown content to a Word document (.docx) using Pandoc.

    Args:
        markdown_content: The markdown text to convert
        output_path: Path where the .docx should be saved (must end in .docx)
        config: Optional configuration dict:
            - company_name: Used as the document title metadata
            - author: Author metadata
            - enable_toc: Include a table of contents (default: False)
            - reference_doc: Path to a branded reference .docx for styles
            - highlight_style: Code highlight theme (default: tango)

    Returns:
        Dict with 'status', 'file_path', and optional 'error' key
    """
    if not markdown_content or not markdown_content.strip():
        return {'status': 'error', 'error': 'Markdown content is empty or invalid'}

    if not output_path:
        return {'status': 'error', 'error': 'Output path is required'}

    output_dir = Path(output_path).parent
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {'status': 'error', 'error': f'Failed to create output directory: {str(e)}'}

    try:
        config = validate_docx_config(config)
    except Exception as e:
        logger.error(f"Config validation error: {str(e)}")
        return {'status': 'error', 'error': f'Invalid configuration: {str(e)}'}

    try:
        import pypandoc

        extra_args = [
            '--standalone',
            f'--syntax-highlighting={config["highlight_style"]}',
            f'--metadata=title:{config["company_name"]}',
        ]

        if config['author']:
            extra_args.append(f'--metadata=author:{config["author"]}')

        if config['enable_toc']:
            extra_args.append('--toc')

        if config['reference_doc']:
            extra_args.append(f'--reference-doc={config["reference_doc"]}')

        pypandoc.convert_text(
            markdown_content,
            'docx',
            format='markdown',
            outputfile=output_path,
            extra_args=extra_args,
        )

        return {
            'status': 'success',
            'file_path': output_path,
            'size_bytes': os.path.getsize(output_path) if os.path.exists(output_path) else 0,
            'renderer': 'pandoc',
        }

    except Exception as e:
        logger.error(f"Word document generation failed: {str(e)}")
        return {'status': 'error', 'error': f'Word document generation failed: {str(e)}'}
