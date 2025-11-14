#!/usr/bin/env python3
"""Validate Mattermost integration structure and imports."""

import os
import sys
import json
import importlib.util
import ast

def validate_integration():
    """Validate the integration structure."""
    print("Mattermost Integration Validation")
    print("=" * 40)
    
    base_path = "custom_components/mattermost"
    
    # Check required files
    required_files = [
        "__init__.py",
        "config_flow.py", 
        "notify.py",
        "const.py",
        "manifest.json",
        "strings.json"
    ]
    
    missing_files = []
    for file in required_files:
        file_path = os.path.join(base_path, file)
        if os.path.exists(file_path):
            print(f"✓ {file}")
        else:
            print(f"✗ {file} - MISSING")
            missing_files.append(file)
    
    if missing_files:
        print(f"\nMissing files: {missing_files}")
        return False
    
    print("\n" + "=" * 40)
    
    # Validate manifest.json
    try:
        with open(os.path.join(base_path, "manifest.json"), "r") as f:
            manifest = json.load(f)
        
        print("Manifest validation:")
        print(f"  Domain: {manifest.get('domain', 'MISSING')}")
        print(f"  Name: {manifest.get('name', 'MISSING')}")
        print(f"  Config Flow: {manifest.get('config_flow', 'MISSING')}")
        print(f"  Requirements: {manifest.get('requirements', [])}")
        
        if manifest.get('domain') != 'mattermost':
            print("✗ Domain should be 'mattermost'")
            return False
        if not manifest.get('config_flow'):
            print("✗ Config flow should be enabled")
            return False
            
        print("✓ Manifest valid")
    except Exception as e:
        print(f"✗ Manifest error: {e}")
        return False
    
    print("\n" + "=" * 40)
    
    # Check Python syntax
    for py_file in ["__init__.py", "config_flow.py", "notify.py", "const.py"]:
        file_path = os.path.join(base_path, py_file)
        try:
            with open(file_path, "r") as f:
                source = f.read()
            
            # Parse the AST to check syntax
            ast.parse(source)
            print(f"✓ {py_file} syntax valid")
            
            # Check for old imports
            if py_file != "const.py":
                if "mattermostdriver" in source:
                    print(f"⚠ {py_file} still contains mattermostdriver imports")
                else:
                    print(f"✓ {py_file} no legacy imports")
            
        except SyntaxError as e:
            print(f"✗ {py_file} syntax error: {e}")
            return False
        except Exception as e:
            print(f"✗ {py_file} error: {e}")
            return False
    
    print("\n" + "=" * 40)
    print("✓ Integration structure validation complete!")
    return True

if __name__ == "__main__":
    success = validate_integration()
    sys.exit(0 if success else 1)