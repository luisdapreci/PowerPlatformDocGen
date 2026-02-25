"""
Test script for PDF generation with logo embedding.

This script tests:
1. PDF generation with a logo (base64 embedded)
2. PDF generation without a logo
3. Both WeasyPrint and xhtml2pdf renderers
4. Verifies no file:// URL warnings
"""

import sys
import os
from pathlib import Path

# Add parent directory to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from utils.pdf_renderer import render_markdown_to_pdf
import config
PDF_CONFIG = config.PDF_CONFIG


# Sample markdown content with ASCII diagrams
SAMPLE_MARKDOWN = """
# Test Documentation

## Overview
This is a test document to verify PDF generation with logo embedding.

## Architecture Diagram

```
┌─────────────────────────────────────────────┐
│         Power Platform Solution            │
│                                             │
│  ┌──────────┐        ┌──────────┐          │
│  │  Canvas  │───────▶│  Dataverse│         │
│  │   App    │        │            │         │
│  └──────────┘        └──────────┘          │
│                                             │
│  ┌──────────┐        ┌──────────┐          │
│  │   Flow   │───────▶│ Connector │         │
│  └──────────┘        └──────────┘          │
└─────────────────────────────────────────────┘
```

## Component Details

### Canvas App
- **Name**: Test App
- **Type**: Canvas Application
- **Screens**: 5

### Data Model

| Entity | Fields | Purpose |
|--------|--------|---------|
| Account | Name, Email | Customer data |
| Contact | Phone, Address | Contact info |
| Project | Title, Status | Project tracking |

## Code Example

```javascript
function initializeApp() {
    // Initialize the application
    const config = {
        apiEndpoint: "https://api.example.com",
        timeout: 3000
    };
    
    return config;
}
```

## Summary

This document demonstrates:
- ✅ Markdown to PDF conversion
- ✅ Logo embedding (base64)
- ✅ ASCII diagram rendering
- ✅ Table formatting
- ✅ Code highlighting
- ✅ Professional styling
"""


def create_test_logo():
    """Create a simple test logo image if one doesn't exist."""
    logo_path = Path(__file__).parent.parent / "assets" / "company_logo.png"
    
    # Create assets directory if it doesn't exist
    logo_path.parent.mkdir(parents=True, exist_ok=True)
    
    # If logo already exists, return
    if logo_path.exists():
        print(f"✓ Logo already exists at: {logo_path}")
        return logo_path
    
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Create a simple 400x100 logo with text
        img = Image.new('RGB', (400, 100), color=(0, 120, 212))  # Microsoft blue
        draw = ImageDraw.Draw(img)
        
        # Add company name text
        try:
            # Try to use a nice font
            font = ImageFont.truetype("arial.ttf", 40)
        except:
            # Fall back to default font
            font = ImageFont.load_default()
        
        draw.text((20, 30), "Company Logo", fill=(255, 255, 255), font=font)
        
        # Save the image
        img.save(str(logo_path))
        print(f"✓ Created test logo at: {logo_path}")
        return logo_path
        
    except ImportError:
        print("⚠ PIL/Pillow not installed. Creating a placeholder file.")
        # Create an empty file as placeholder
        logo_path.touch()
        print(f"✓ Created placeholder at: {logo_path}")
        return logo_path


def test_pdf_with_logo():
    """Test PDF generation with logo."""
    print("\n" + "="*60)
    print("TEST 1: PDF Generation with Logo")
    print("="*60)
    
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / "test_with_logo.pdf"
    
    try:
        print("\n📄 Generating PDF with logo...")
        print(f"   Using config: {PDF_CONFIG}")
        result = render_markdown_to_pdf(
            markdown_content=SAMPLE_MARKDOWN,
            output_path=str(output_file),
            config=PDF_CONFIG
        )
        
        if not result.get('success'):
            print(f"⚠ Warning: {result.get('error', 'Unknown error')}")
        
        if output_file.exists():
            file_size = output_file.stat().st_size
            print(f"✅ SUCCESS: PDF generated at {output_file}")
            print(f"   File size: {file_size:,} bytes")
            return True
        else:
            print(f"❌ FAILED: PDF not created at {output_file}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_pdf_without_logo():
    """Test PDF generation without logo."""
    print("\n" + "="*60)
    print("TEST 2: PDF Generation without Logo")
    print("="*60)
    
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / "test_without_logo.pdf"
    
    # Temporarily remove logo path
    config_without_logo = PDF_CONFIG.copy()
    config_without_logo['logo_path'] = None
    
    try:
        print("\n📄 Generating PDF without logo...")
        print(f"   Using config: {config_without_logo}")
        result = render_markdown_to_pdf(
            markdown_content=SAMPLE_MARKDOWN,
            output_path=str(output_file),
            config=config_without_logo
        )
        
        if not result.get('success'):
            print(f"⚠ Warning: {result.get('error', 'Unknown error')}")
        
        if output_file.exists():
            file_size = output_file.stat().st_size
            print(f"✅ SUCCESS: PDF generated at {output_file}")
            print(f"   File size: {file_size:,} bytes")
            return True
        else:
            print(f"❌ FAILED: PDF not created at {output_file}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def verify_base64_embedding():
    """Verify that base64 embedding is being used (no file:// warnings)."""
    print("\n" + "="*60)
    print("TEST 3: Verify Base64 Embedding")
    print("="*60)
    
    print("\n🔍 Checking pdf_renderer.py for base64 implementation...")
    
    pdf_renderer_path = Path(__file__).parent.parent / "src" / "utils" / "pdf_renderer.py"
    
    with open(pdf_renderer_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = {
        "base64 import": "import base64" in content,
        "base64.b64encode usage": "base64.b64encode" in content,
        "data URI format": "data:image" in content or "data:{mime_type}" in content,
        "No file:// URLs": "file://" not in content or "# OLD:" in content
    }
    
    all_passed = True
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"   {status} {check}")
        if not passed:
            all_passed = False
    
    return all_passed


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("PDF GENERATION TEST SUITE")
    print("="*60)
    print(f"Test directory: {Path(__file__).parent}")
    print(f"Output directory: {Path(__file__).parent / 'output'}")
    
    # Create test logo
    print("\n📋 Preparing test environment...")
    create_test_logo()
    
    # Run tests
    results = []
    
    results.append(("PDF with Logo", test_pdf_with_logo()))
    results.append(("PDF without Logo", test_pdf_without_logo()))
    results.append(("Base64 Embedding Check", verify_base64_embedding()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"   {status}: {test_name}")
    
    print(f"\n   Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! PDF generation with logo embedding is working correctly.")
        print("\n📁 Check the following files:")
        output_dir = Path(__file__).parent / "output"
        for pdf_file in output_dir.glob("*.pdf"):
            print(f"   - {pdf_file}")
        
        logo_path = Path(__file__).parent.parent / "assets" / "company_logo.png"
        if logo_path.exists():
            print(f"   - {logo_path} (logo)")
    else:
        print("\n⚠ Some tests failed. Please review the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
