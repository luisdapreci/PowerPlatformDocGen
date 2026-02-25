import sys
sys.path.insert(0, 'src')

from utils.pdf_renderer import render_markdown_to_pdf

test_markdown = """# Test ASCII Diagrams

## Power Automate Flow Example

```
┌─────────────────────────────────────────┐
│  Dataverse: cr6b0_calendar table        │
│  (New record created)                   │
└────────────────┬────────────────────────┘
                 │ Webhook Trigger
                 ▼
┌─────────────────────────────────────────┐
│  Trigger: When a row is added           │
│  - Entity: cr6b0_calendar               │
│  - Message: Create (1)                  │
│  - Scope: Organization (4)              │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  Action: Compose - Calendar ID          │
│  - Input: triggerOutputs()              │
│    ?['body/cr6b0_date']                 │
│  - Transform: replace('-', '')          │
│  - Output: "20240115"                   │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  Action: Update a row - Calendars       │
│  - Entity: cr6b0_calendars              │
│  - Record ID: from trigger              │
│  - Field: cr6b0_d_calendarkey           │
│  - Value: output from Compose           │
└─────────────────────────────────────────┘
```

## Code Example

```python
def hello_world():
    print("Hello, World!")
    for i in range(10):
        print(f"Number: {i}")
```

## Regular Text

This should render normally without any issues.
"""

result = render_markdown_to_pdf(test_markdown, 'test_ascii_diagram.pdf')
print(f"Status: {result['status']}")
if result['status'] == 'success':
    print(f"Renderer: {result.get('renderer', 'unknown')}")
    print(f"File: {result['file_path']}")
    print(f"Size: {result['size_bytes']} bytes")
    print("\n✓ PDF generated! Check test_ascii_diagram.pdf")
else:
    print(f"Error: {result.get('error', 'Unknown error')}")
