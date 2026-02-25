#!/usr/bin/env python3
"""
Comprehensive Power Platform Solution Analyzer
Parses solution.xml, Canvas Apps, and Workflows for detailed analysis
"""

import xml.etree.ElementTree as ET
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

class SolutionAnalyzer:
    def __init__(self, solution_path: str):
        self.solution_path = Path(solution_path)
        self.report = {}
        
    def parse_solution_xml(self) -> Dict[str, Any]:
        """Extract solution metadata from solution.xml"""
        solution_file = self.solution_path / "solution.xml"
        if not solution_file.exists():
            return {}
        
        tree = ET.parse(solution_file)
        root = tree.getroot()
        
        # Define namespace
        ns = {'sol': 'http://schemas.microsoft.com/crm/2011/solutions'}
        
        solution_info = {}
        
        # Extract SolutionManifest info
        manifest = root.find('.//sol:SolutionManifest', ns)
        if manifest:
            unique_name = manifest.find('sol:UniqueName', ns)
            version = manifest.find('sol:Version', ns)
            publisher = manifest.find('.//sol:Publisher', ns)
            
            if unique_name is not None:
                solution_info['unique_name'] = unique_name.text
            if version is not None:
                solution_info['version'] = version.text
            if publisher is not None:
                pub_unique_name = publisher.find('sol:UniqueName', ns)
                if pub_unique_name is not None:
                    solution_info['publisher_unique_name'] = pub_unique_name.text
        
        return solution_info
    
    def find_canvas_apps(self) -> List[Dict[str, Any]]:
        """Find all canvas apps in the solution"""
        canvas_apps = []
        
        # Method 1: Check CanvasApps directory
        canvas_apps_dir = self.solution_path / "CanvasApps"
        if canvas_apps_dir.exists():
            for app_dir in canvas_apps_dir.iterdir():
                if app_dir.is_dir():
                    app_info = self._analyze_canvas_app(app_dir)
                    if app_info:
                        canvas_apps.append(app_info)
        
        # Method 2: Check for _src directories at root level
        for item in self.solution_path.iterdir():
            if item.is_dir() and item.name.endswith('_src'):
                app_info = self._analyze_canvas_app(item)
                if app_info:
                    # Check if not already added
                    if not any(app['id'] == app_info['id'] for app in canvas_apps):
                        canvas_apps.append(app_info)
        
        return canvas_apps
    
    def _analyze_canvas_app(self, app_dir: Path) -> Dict[str, Any]:
        """Analyze a single canvas app directory"""
        app_info = {
            'path': str(app_dir.relative_to(self.solution_path)),
            'id': app_dir.name,
            'name': app_dir.name,
            'screens': [],
            'formulas': [],
            'data_sources': [],
            'assets': [],
            'manifest': {}
        }
        
        # Check for CanvasManifest.json
        manifest_file = app_dir / "CanvasManifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                    app_info['manifest'] = manifest
                    if 'Name' in manifest:
                        app_info['name'] = manifest['Name']
            except Exception as e:
                app_info['manifest_error'] = str(e)
        
        # Find screens from ComponentReferences.json or direct screen files
        screens_dir = app_dir / "Screens"
        if screens_dir.exists():
            for screen_dir in screens_dir.iterdir():
                if screen_dir.is_dir():
                    screen_name = screen_dir.name
                    # Check for screen manifest
                    screen_manifest = screen_dir / "ComponentManifest.json"
                    if screen_manifest.exists():
                        try:
                            with open(screen_manifest, 'r', encoding='utf-8') as f:
                                screen_data = json.load(f)
                                screen_name = screen_data.get('DisplayName', screen_name)
                        except:
                            pass
                    app_info['screens'].append(screen_name)
        
        # Find .fx.yaml files (formulas)
        for root, dirs, files in os.walk(app_dir):
            for file in files:
                if file.endswith('.fx.yaml'):
                    rel_path = os.path.relpath(os.path.join(root, file), app_dir)
                    app_info['formulas'].append(rel_path)
        
        # Check DataSources folder
        datasources_dir = app_dir / "DataSources"
        if datasources_dir.exists():
            for source_file in datasources_dir.iterdir():
                if source_file.is_file() and source_file.suffix == '.json':
                    try:
                        with open(source_file, 'r', encoding='utf-8') as f:
                            source_data = json.load(f)
                            source_name = source_data.get('Name', source_file.stem)
                            app_info['data_sources'].append(source_name)
                    except:
                        app_info['data_sources'].append(source_file.name)
        
        # Check Assets folder
        assets_dir = app_dir / "Assets"
        if assets_dir.exists():
            for asset_file in assets_dir.iterdir():
                if asset_file.is_file():
                    app_info['assets'].append(asset_file.name)
        
        return app_info
    
    def analyze_workflows(self) -> Dict[str, Any]:
        """Analyze Power Automate Workflows"""
        workflows_dir = self.solution_path / "Workflows"
        workflows_info = {
            'total_count': 0,
            'flows': [],
            'connections': set()
        }
        
        if not workflows_dir.exists():
            return workflows_info
        
        flow_count = 0
        for flow_file in workflows_dir.glob('*.json'):
            if flow_count < 10:  # Get first 10 flows
                try:
                    with open(flow_file, 'r', encoding='utf-8') as f:
                        flow_data = json.load(f)
                        flow_info = {
                            'display_name': flow_data.get('properties', {}).get('displayName', flow_file.stem),
                            'trigger_type': flow_data.get('properties', {}).get('definition', {}).get('triggers', {}).get('trigger', {}).get('type', 'Unknown'),
                            'file': flow_file.name
                        }
                        workflows_info['flows'].append(flow_info)
                        
                        # Extract connection references
                        refs = flow_data.get('properties', {}).get('connectionReferences', {})
                        if isinstance(refs, dict):
                            workflows_info['connections'].update(refs.keys())
                except Exception as e:
                    workflows_info['flows'].append({
                        'display_name': flow_file.stem,
                        'trigger_type': 'Error parsing',
                        'file': flow_file.name,
                        'error': str(e)
                    })
            flow_count += 1
        
        workflows_info['total_count'] = flow_count
        workflows_info['connections'] = list(workflows_info['connections'])
        
        return workflows_info
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive analysis report"""
        print("Parsing solution metadata...")
        solution_info = self.parse_solution_xml()
        
        print("Analyzing canvas apps...")
        canvas_apps = self.find_canvas_apps()
        
        print("Analyzing workflows...")
        workflows = self.analyze_workflows()
        
        # Calculate component counts
        component_counts = {
            'total_canvas_apps': len(canvas_apps),
            'total_screens': sum(len(app['screens']) for app in canvas_apps),
            'total_formulas': sum(len(app['formulas']) for app in canvas_apps),
            'total_data_sources': sum(len(app['data_sources']) for app in canvas_apps),
            'total_assets': sum(len(app['assets']) for app in canvas_apps),
            'total_workflows': workflows['total_count']
        }
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'solution_info': solution_info,
            'component_counts': component_counts,
            'canvas_apps': canvas_apps,
            'workflows': {
                'total_count': workflows['total_count'],
                'first_10_flows': workflows['flows'],
                'connections': workflows['connections']
            }
        }
        
        return report

def main():
    """Main execution"""
    from pathlib import Path
    # Use relative path from project root
    base_dir = Path(__file__).parent.parent
    solution_path = base_dir / "temp" / "163eb050-10b6-4e26-878c-95135044ec0c" / "extracted"
    
    analyzer = SolutionAnalyzer(str(solution_path))
    report = analyzer.generate_report()
    
    # Output as formatted JSON
    print("\n" + "="*80)
    print("POWER PLATFORM SOLUTION ANALYSIS REPORT")
    print("="*80 + "\n")
    
    print(json.dumps(report, indent=2, default=str))
    
    # Save report to file
    output_file = Path(solution_path).parent / "solution_analysis_report.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n\nReport saved to: {output_file}")

if __name__ == "__main__":
    main()
