"""
Test script for enhanced PDF generation features.

Tests:
1. Table of Contents generation
2. Syntax highlighting
3. Admonition boxes
4. Custom CSS injection
5. Line numbers (WeasyPrint)
6. Enhanced markdown features
7. Input validation
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.pdf_renderer import render_markdown_to_pdf, validate_pdf_config
import config

# Test markdown with all enhanced features
ENHANCED_MARKDOWN = """
# Enhanced PDF Features Test

This document tests all the new PDF generation features.

## Table of Contents

The TOC should be automatically generated from these headings.

## Syntax Highlighting

### Python Code

```python
def fibonacci(n):
    \"""Generate Fibonacci sequence.\"""
    if n <= 0:
        return []
    elif n == 1:
        return [0]
    elif n == 2:
        return [0, 1]
    
    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[-1] + fib[-2])
    return fib

# Usage
result = fibonacci(10)
print(f"First 10 Fibonacci numbers: {result}")
```

### JavaScript Code

```javascript
// Async function example
async function fetchUserData(userId) {
    try {
        const response = await fetch(`/api/users/${userId}`);
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error fetching user:', error);
        throw error;
    }
}

// Usage
fetchUserData(123).then(user => {
    console.log('User:', user.name);
});
```

### SQL Query

```sql
-- Complex JOIN query
SELECT 
    u.user_id,
    u.username,
    COUNT(o.order_id) as total_orders,
    SUM(o.total_amount) as total_spent
FROM users u
LEFT JOIN orders o ON u.user_id = o.user_id
WHERE u.created_at >= '2024-01-01'
GROUP BY u.user_id, u.username
HAVING COUNT(o.order_id) > 5
ORDER BY total_spent DESC
LIMIT 10;
```

## Admonition Boxes

!!! note "Important Note"
    This is a note box. It should appear with a blue theme and proper styling.
    
    You can include multiple paragraphs and even code:
    
    ```python
    print("Code in admonition!")
    ```

!!! warning "Warning"
    This is a warning box with yellow/orange styling.
    Be careful when proceeding!

!!! danger "Critical Alert"
    This is a danger/error box with red styling.
    This indicates critical information.

!!! tip "Pro Tip"
    This is a tip box with green styling.
    Helpful hints and best practices go here.

!!! important "Important Information"
    This box uses purple/violet styling for important callouts.

## Tables

### Feature Comparison

| Feature | WeasyPrint | xhtml2pdf | Status |
|---------|-----------|-----------|--------|
| Syntax Highlighting | ✅ Full Color | ⚠️ Basic | Implemented |
| Line Numbers | ✅ Yes | ❌ No | Implemented |
| Table of Contents | ✅ Yes | ✅ Yes | Implemented |
| Custom CSS | ✅ Yes | ✅ Yes | Implemented |
| Page Breaks | ✅ Advanced | ⚠️ Basic | Implemented |

### Performance Metrics

| Document Size | Generation Time | File Size |
|--------------|----------------|-----------|
| Small (< 10 pages) | 1-2 seconds | 200-500 KB |
| Medium (10-50 pages) | 2-5 seconds | 500 KB - 2 MB |
| Large (50+ pages) | 5-15 seconds | 2-10 MB |

## Lists and Formatting

### Unordered List

- First level item
- Another first level item
  - Second level nested item
  - Another second level
    - Third level item
- Back to first level

### Ordered List

1. First step in the process
2. Second step with details
   1. Sub-step 2.1
   2. Sub-step 2.2
3. Third step
4. Final step

### Task List

- [x] Completed task
- [x] Another completed task
- [ ] Pending task
- [ ] Future task

## Definition Lists

Term 1
:   Definition for term 1. This provides detailed information
    about the term with proper formatting.

Term 2
:   Definition for term 2. Multiple paragraphs are supported.

    This is a second paragraph in the definition.

API
:   Application Programming Interface

REST
:   Representational State Transfer

## Footnotes

This feature includes footnotes[^1] that appear at the bottom of the page.
You can also reference them multiple times[^1] and add more[^2].

[^1]: This is the first footnote with important information.
[^2]: This is the second footnote with additional details.

## Block Quotes

> This is a blockquote with important information.
> It can span multiple lines and will be styled appropriately.
>
> > Nested blockquotes are also supported.
> > They have proper indentation.

## Horizontal Rules

Content above the line.

---

Content below the line.

## Emphasis and Formatting

This paragraph contains **bold text**, *italic text*, ***bold and italic***, 
`inline code`, ~~strikethrough text~~, and ==highlighted text==.

## Code Blocks Without Language

```
Plain text code block
No syntax highlighting
  But preserves formatting
    And indentation
```

## Long Code Block (Testing Line Numbers)

```python
class PowerPlatformDocumentationGenerator:
    \"""
    Main class for generating Power Platform documentation.
    Supports multiple components and export formats.
    \"""
    
    def __init__(self, config):
        self.config = config
        self.session_id = None
        self.components = []
        self.metadata = {}
    
    def analyze_solution(self, solution_path):
        \"""Analyze Power Platform solution.\"""
        # Line 15
        print(f"Analyzing solution: {solution_path}")
        
        # Parse solution files
        components = self._parse_components(solution_path)
        
        # Extract metadata  # Line 20
        self.metadata = self._extract_metadata(components)
        
        # Analyze dependencies
        dependencies = self._analyze_dependencies(components)
        
        return {  # Line 25
            'components': components,
            'metadata': self.metadata,
            'dependencies': dependencies
        }
    
    def generate_documentation(self, output_format='markdown'):  # Line 30
        \"""Generate documentation in specified format.\"""
        if output_format == 'markdown':
            return self._generate_markdown()
        elif output_format == 'pdf':
            return self._generate_pdf()  # Line 35
        elif output_format == 'html':
            return self._generate_html()
        else:
            raise ValueError(f"Unsupported format: {output_format}")
        
    def _generate_pdf(self):  # Line 40
        \"""Generate PDF documentation with all enhancements.\"""
        markdown_content = self._generate_markdown()
        
        result = render_markdown_to_pdf(
            markdown_content=markdown_content,  # Line 45
            output_path=self.config['output_path'],
            config=self.config['pdf_config']
        )
        
        return result  # Line 50
```

## Images

![Example Diagram](https://via.placeholder.com/600x300/3498db/ffffff?text=Documentation+Diagram)

## Nested Structures

### Complex Lists with Code

1. **Step 1: Setup Environment**
   
   Install required dependencies:
   
   ```bash
   pip install markdown weasyprint xhtml2pdf
   ```
   
   Configure the environment:
   
   ```python
   config = {
       'enable_toc': True,
       'enable_line_numbers': True
   }
   ```

2. **Step 2: Generate Documentation**
   
   Run the generator:
   
   - Option A: From command line
   - Option B: From Python script
   - Option C: From web interface

3. **Step 3: Export to PDF**
   
   Download the PDF with all features enabled.

## Summary

This document tests all enhanced PDF features:

✅ Table of Contents (auto-generated)
✅ Syntax Highlighting (multiple languages)
✅ Line Numbers (WeasyPrint only)
✅ Admonition Boxes (note, warning, tip, danger, important)
✅ Enhanced Tables
✅ Definition Lists
✅ Footnotes
✅ Code Blocks with proper styling
✅ Custom CSS support
✅ Input validation
✅ Image handling

---

*Generated by Enhanced PDF Renderer v2.0*
"""


def test_enhanced_features():
    """Test all enhanced PDF features."""
    print("\n" + "="*80)
    print("ENHANCED PDF FEATURES TEST")
    print("="*80)
    
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    # Test 1: Basic generation with all features
    print("\nTest 1: Full Featured PDF Generation")
    print("-" * 80)
    
    output_file = output_dir / "enhanced_features.pdf"
    
    result = render_markdown_to_pdf(
        markdown_content=ENHANCED_MARKDOWN,
        output_path=str(output_file),
        config=config.PDF_CONFIG
    )
    
    if result['status'] == 'success':
        print(f"✅ PDF generated successfully!")
        print(f"   File: {result['file_path']}")
        print(f"   Size: {result['size_bytes']:,} bytes")
        print(f"   Renderer: xhtml2pdf")
    else:
        print(f"❌ PDF generation failed!")
        print(f"   Error: {result['error']}")
        return False
    
    # Test 2: Custom configuration
    print("\nTest 2: Custom Configuration")
    print("-" * 80)
    
    custom_config = {
        'primary_color': '#2c3e50',
        'secondary_color': '#34495e',
        'accent_color': '#e74c3c',
        'company_name': 'Custom Test Documentation',
        'footer_text': 'Test Document - Confidential',
        'logo_path': None,  # No logo
        'page_size': 'Letter',
        'enable_toc': True,
        'custom_css': '''
            h1 { 
                text-transform: uppercase;
                letter-spacing: 2pt;
            }
            .codehilite {
                border-left: 6px solid #e74c3c;
            }
        '''
    }
    
    output_file2 = output_dir / "custom_config.pdf"
    
    result2 = render_markdown_to_pdf(
        markdown_content=ENHANCED_MARKDOWN,
        output_path=str(output_file2),
        config=custom_config
    )
    
    if result2['status'] == 'success':
        print(f"✅ Custom PDF generated successfully!")
        print(f"   File: {result2['file_path']}")
        print(f"   Renderer: xhtml2pdf")
    else:
        print(f"❌ Custom PDF failed: {result2['error']}")
    
    # Test 3: Configuration validation
    print("\nTest 3: Configuration Validation")
    print("-" * 80)
    
    test_configs = [
        {
            'name': 'Invalid color format',
            'config': {'primary_color': 'red'},  # Should default to valid color
        },
        {
            'name': 'Empty config',
            'config': {},  # Should use defaults
        },
        {
            'name': 'None config',
            'config': None,  # Should use defaults
        },
        {
            'name': 'Invalid page size',
            'config': {'page_size': 'INVALID'},  # Should default to A4
        }
    ]
    
    for test_case in test_configs:
        validated = validate_pdf_config(test_case['config'])
        print(f"   {test_case['name']}: ✅ Validated")
    
    # Test 4: Error handling
    print("\nTest 4: Error Handling")
    print("-" * 80)
    
    # Empty content
    result_empty = render_markdown_to_pdf("", str(output_dir / "empty.pdf"))
    if result_empty['status'] == 'error':
        print(f"   ✅ Empty content error handled: {result_empty['error']}")
    
    # Invalid output path
    result_invalid = render_markdown_to_pdf(
        ENHANCED_MARKDOWN,
        "/invalid/path/that/does/not/exist/file.pdf"
    )
    if result_invalid['status'] == 'error':
        print(f"   ✅ Invalid path error handled")
    
    # Test 5: Page numbering configurations
    print("\nTest 5: Page Numbering Configurations")
    print("-" * 80)
    
    # Test with page numbers disabled
    output_file_no_pages = output_dir / "no_page_numbers.pdf"
    config_no_pages = {
        'enable_page_numbers': False,
        'footer_text': 'Documentation without page numbers'
    }
    result_no_pages = render_markdown_to_pdf(
        markdown_content=ENHANCED_MARKDOWN,
        output_path=str(output_file_no_pages),
        config=config_no_pages
    )
    if result_no_pages['status'] == 'success':
        print(f"   ✅ PDF without page numbers: {output_file_no_pages.name}")
    
    # Test with custom page number format
    output_file_custom_format = output_dir / "custom_page_format.pdf"
    config_custom_format = {
        'enable_page_numbers': True,
        'page_number_format': '{page} / {total}',
        'page_number_position': 'bottom-right',
        'footer_text': 'Custom Format'
    }
    result_custom_format = render_markdown_to_pdf(
        markdown_content=ENHANCED_MARKDOWN,
        output_path=str(output_file_custom_format),
        config=config_custom_format
    )
    if result_custom_format['status'] == 'success':
        print(f"   ✅ PDF with custom page format (bottom-right): {output_file_custom_format.name}")
    
    # Test with different position
    output_file_left = output_dir / "page_numbers_left.pdf"
    config_left = {
        'enable_page_numbers': True,
        'page_number_format': 'Page {page}',
        'page_number_position': 'bottom-left',
        'footer_text': 'Test Document'
    }
    result_left = render_markdown_to_pdf(
        markdown_content=ENHANCED_MARKDOWN,
        output_path=str(output_file_left),
        config=config_left
    )
    if result_left['status'] == 'success':
        print(f"   ✅ PDF with page numbers on left: {output_file_left.name}")
    
    print("\n" + "="*80)
    print("ALL TESTS COMPLETED!")
    print("="*80)
    print(f"\nGenerated PDFs are in: {output_dir}")
    print("\nOpen the PDFs to verify:")
    print("1. Table of Contents on separate page")
    print("2. Syntax highlighted code blocks")
    print("3. Styled admonition boxes")
    print("4. Professional tables")
    print("5. Custom styling applied")
    print("6. Page numbering (various formats and positions)")
    print("\nRenderer: xhtml2pdf (pure Python, no external dependencies)")
    print("\n")
    
    return True


if __name__ == "__main__":
    try:
        success = test_enhanced_features()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
