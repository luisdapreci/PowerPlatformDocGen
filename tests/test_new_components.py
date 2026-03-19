#!/usr/bin/env python3
"""Quick test for desktop flow and copilot agent detection."""
import sys
sys.path.insert(0, "src")

from pathlib import Path
from main import (
    _parse_customizations_workflow_map,
    _get_copilot_agent_display_name,
    _collect_copilot_agent_files,
    _extract_desktop_flow_definition,
    _extract_desktop_flow_metadata,
)

SOL_DIR = Path(r"C:\PowerPlatformDocGen\tests\data\COPILOT AGENT + DESKTOP\ARRAutomationSolutionV2_1_0_0_1")

print("=== WORKFLOW MAP ===")
wf_map = _parse_customizations_workflow_map(SOL_DIR)
desktop_count = 0
cloud_count = 0
for fname, meta in wf_map.items():
    cat_label = "DESKTOP" if meta["category"] == 6 else "CLOUD"
    if meta["category"] == 6:
        desktop_count += 1
    else:
        cloud_count += 1
    name = meta["name"]
    ui_type = meta["ui_flow_type"]
    print(f"  [{cat_label}] {name}  (file={fname}, ui_flow_type={ui_type})")

print(f"\nTotal: {len(wf_map)} workflows ({desktop_count} desktop, {cloud_count} cloud)")

print("\n=== COPILOT AGENTS ===")
bots_dir = SOL_DIR / "bots"
if bots_dir.exists():
    for bot_dir in bots_dir.iterdir():
        if bot_dir.is_dir():
            display_name = _get_copilot_agent_display_name(bot_dir)
            print(f"  Agent: {display_name} (folder: {bot_dir.name})")

            rel_path = str(bot_dir.relative_to(SOL_DIR))
            agent_files = _collect_copilot_agent_files(SOL_DIR, rel_path)
            print(f"  Collected {len(agent_files)} files:")
            for path in sorted(agent_files.keys())[:10]:
                size = len(agent_files[path])
                print(f"    {path} ({size} chars)")
            if len(agent_files) > 10:
                print(f"    ... and {len(agent_files) - 10} more")

print("\n=== DESKTOP FLOW PAD SCRIPT EXTRACTION ===")
for fname, meta in wf_map.items():
    if meta["category"] == 6:
        wf_id = meta["workflow_id"]
        name = meta["name"]
        pad_script = _extract_desktop_flow_definition(SOL_DIR, wf_id)
        extra = _extract_desktop_flow_metadata(SOL_DIR, wf_id)
        script_len = len(pad_script) if pad_script else 0
        extra_keys = list(extra.keys())
        print(f"  {name}: PAD script={script_len} chars, metadata keys={extra_keys}")
        if pad_script:
            # Show first 200 chars of script
            preview = pad_script[:200].replace("\n", "\\n")
            print(f"    Preview: {preview}...")

print("\nAll tests passed!")
