"""
Test script for incremental documentation generation approach
Tests that the AI actually edits the template file using tools, not just generates text
"""
import asyncio
import shutil
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from doc_generator import DocumentationGenerator
import config


async def test_incremental_generation():
    """Test the incremental documentation generation with a minimal Canvas App"""
    
    print("=" * 80)
    print("INCREMENTAL DOCUMENTATION GENERATION TEST")
    print("=" * 80)
    
    # Setup test directory
    test_dir = Path(__file__).parent.parent / "temp" / "test_incremental"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy template to test directory
    template_path = Path(__file__).parent.parent / "templates" / "DocumentationTemplate.md"
    template_content = template_path.read_text(encoding='utf-8')
    template_size = len(template_content)
    
    print(f"\n1. Setup:")
    print(f"   Test Directory: {test_dir}")
    print(f"   Template Size: {template_size} chars")
    
    # Create minimal test files
    critical_files = []
    
    # Test file 1: App.fx.yaml (App startup logic)
    app_fx = """App As appinfo:
    OnStart: |-
        =// Set global variables
        Set(gblAppName, "Test Calendar App");
        Set(gblCurrentUser, User().Email);
        
        // Initialize collections
        ClearCollect(
            colEvents,
            Filter(
                'Calendar Events',
                Status = "Active"
            )
        );
        
        // Navigate to home screen
        Navigate('Home Screen', ScreenTransition.Fade);
"""
    critical_files.append(("App.fx.yaml", app_fx))
    
    # Test file 2: Home Screen.fx.yaml
    home_screen_fx = """'Home Screen' As screen:
    Fill: =RGBA(245, 245, 245, 1)
    OnVisible: |-
        =// Refresh events on screen load
        Refresh('Calendar Events');
        UpdateContext({locScreenLoaded: true});
    
    Gallery1 As gallery:
        Items: |-
            =SortByColumns(
                Filter(
                    colEvents,
                    StartDate >= Today()
                ),
                "StartDate",
                Ascending
            )
        TemplateFill: =If(ThisItem.IsSelected, RGBA(0, 120, 212, 1), White)
        
    Button_NewEvent As button:
        Text: ="+ New Event"
        OnSelect: =Navigate('Event Details', ScreenTransition.Cover)
        Fill: =RGBA(0, 120, 212, 1)
"""
    critical_files.append(("Home Screen.fx.yaml", home_screen_fx))
    
    # Test file 3: Event Details.fx.yaml
    event_details_fx = """'Event Details' As screen:
    Fill: =White
    
    Form_Event As form:
        DataSource: ='Calendar Events'
        Item: =If(IsBlank(varSelectedEvent), Defaults('Calendar Events'), varSelectedEvent)
        
    Button_Save As button:
        Text: ="Save"
        OnSelect: |-
            =SubmitForm(Form_Event);
            If(
                Form_Event.Error = Blank(),
                Notify("Event saved successfully", NotificationType.Success);
                Navigate('Home Screen', ScreenTransition.UnCover),
                Notify("Error: " & Form_Event.Error, NotificationType.Error)
            );
        Fill: =RGBA(0, 120, 212, 1)
        
    Button_Cancel As button:
        Text: ="Cancel"
        OnSelect: =Navigate('Home Screen', ScreenTransition.UnCover)
"""
    critical_files.append(("Event Details.fx.yaml", event_details_fx))
    
    non_critical_files = []
    
    print(f"\n2. Test Files Created:")
    for path, content in critical_files:
        print(f"   ✓ {path} ({len(content)} chars)")
    
    # Initialize doc generator
    print(f"\n3. Initializing DocumentationGenerator...")
    doc_gen = DocumentationGenerator()
    await doc_gen.initialize()
    
    session_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print(f"   Session ID: {session_id}")
    print(f"   Model: {config.COPILOT_MODEL}")
    print(f"   Tools Enabled: {config.COPILOT_ALLOWED_BUILTIN_TOOLS}")
    
    # Run generation
    print(f"\n4. Running Incremental Generation...")
    print(f"   (This will take several minutes - watch for progress updates)")
    
    selection_context = """
ℹ️ TEST SCOPE: Minimal Canvas App
Testing incremental documentation with 3 screens and basic formulas.
"""
    
    business_context = """
This is a test calendar application for managing team events.
Users can view upcoming events and create new event entries.
The app integrates with SharePoint Calendar Events list.
"""
    
    start_time = datetime.now()
    
    try:
        result = await doc_gen.generate_documentation(
            session_id=session_id,
            working_directory=test_dir,
            critical_files=critical_files,
            non_critical_files=non_critical_files,
            template_path=template_path,
            selection_context=selection_context,
            business_context=business_context
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n5. Generation Complete!")
        print(f"   Duration: {duration:.1f} seconds")
        print(f"   Result Length: {len(result)} chars")
        
        # Check the actual file on disk
        doc_file = test_dir / f"{session_id}_Documentation.md"
        if doc_file.exists():
            actual_content = doc_file.read_text(encoding='utf-8')
            actual_size = len(actual_content)
            
            print(f"\n6. File Verification:")
            print(f"   File Path: {doc_file}")
            print(f"   File Size: {actual_size} chars")
            print(f"   Template Size: {template_size} chars")
            
            # Analyze the result
            print(f"\n7. Content Analysis:")
            
            # Check if file was actually edited
            if actual_size == template_size:
                print(f"   ❌ FAILURE: File size matches template (not edited!)")
                success = False
            elif actual_size < template_size:
                print(f"   ❌ FAILURE: File smaller than template ({actual_size} < {template_size})")
                success = False
            else:
                print(f"   ✅ SUCCESS: File edited ({actual_size} > {template_size})")
                success = True
            
            # Check for expected content
            checks = [
                ("App Name", "Test Calendar App" in actual_content or "gblAppName" in actual_content),
                ("Global Variables", "gblCurrentUser" in actual_content or "User().Email" in actual_content),
                ("Home Screen", "Home Screen" in actual_content),
                ("Gallery Formula", "SortByColumns" in actual_content or "colEvents" in actual_content),
                ("Event Details", "Event Details" in actual_content or "Form_Event" in actual_content),
                ("Business Context", "calendar" in actual_content.lower() or "events" in actual_content.lower()),
                ("Navigation", "Navigate" in actual_content),
                ("Data Source", "Calendar Events" in actual_content)
            ]
            
            print(f"\n   Content Checks:")
            passed = 0
            failed = 0
            for check_name, check_result in checks:
                status = "✅" if check_result else "❌"
                print(f"      {status} {check_name}")
                if check_result:
                    passed += 1
                else:
                    failed += 1
            
            # Check if still has placeholders that should have been filled
            placeholder_check = actual_content.count("[Placeholder]")
            print(f"\n   Remaining Placeholders: {placeholder_check}")
            
            # Overall result
            print(f"\n{'=' * 80}")
            print(f"TEST RESULT:")
            print(f"{'=' * 80}")
            
            if success and passed >= 5 and placeholder_check < 10:
                print(f"✅ TEST PASSED")
                print(f"   - File was edited ({actual_size} chars vs {template_size} template)")
                print(f"   - Content checks: {passed}/{len(checks)} passed")
                print(f"   - Placeholders filled: {placeholder_check} remaining")
                print(f"\n   The incremental approach is working correctly!")
                print(f"   AI is using file editing tools as expected.")
            else:
                print(f"❌ TEST FAILED")
                print(f"   - File edited: {success}")
                print(f"   - Content checks: {passed}/{len(checks)} passed, {failed} failed")
                print(f"   - Placeholders: {placeholder_check} remaining")
                print(f"\n   ISSUES DETECTED:")
                
                if not success:
                    print(f"   • AI did not edit the file - only generated text responses")
                    print(f"   • File size: {actual_size} (should be > {template_size})")
                
                if passed < 5:
                    print(f"   • Missing expected content from test files")
                    print(f"   • Only {passed}/{len(checks)} content checks passed")
                
                if placeholder_check > 15:
                    print(f"   • Too many unfilled placeholders ({placeholder_check})")
                    print(f"   • AI may not be filling all relevant sections")
            
            # Save a preview
            print(f"\n8. Documentation Preview (first 1000 chars):")
            print(f"-" * 80)
            print(actual_content[:1000])
            print(f"-" * 80)
            
            # Offer to view full file
            print(f"\n   Full documentation saved to:")
            print(f"   {doc_file}")
            
        else:
            print(f"\n   ❌ ERROR: Documentation file not found at {doc_file}")
    
    except Exception as e:
        print(f"\n❌ ERROR during generation:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{'=' * 80}")


if __name__ == "__main__":
    print("\nStarting Incremental Documentation Test...")
    print("This test will verify that the AI uses file editing tools correctly.\n")
    
    asyncio.run(test_incremental_generation())
    
    print("\nTest complete. Press Enter to exit...")
    input()
