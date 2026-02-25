# Assets Folder

This folder contains static assets for PDF generation.

## Adding Your Company Logo

1. Place your company logo image in this folder
2. Name it `company_logo.png` (or update the filename in `src/config.py`)
3. Supported formats: PNG, JPG, SVG
4. Recommended size: 200px wide or less

The logo will automatically appear on the cover page of all generated PDFs.

## Current Configuration

The logo path is configured in `src/config.py`:
```python
'logo_path': 'assets/company_logo.png'
```

Set to `None` to disable the logo.
