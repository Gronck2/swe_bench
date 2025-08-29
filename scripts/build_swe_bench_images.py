#!/usr/bin/env python3
"""
Script to build SWE-bench Docker environment images.
This is required before running validation with official harness.
"""

import docker
import json
import sys
from pathlib import Path
from swebench.harness.docker_build import build_env_images
from swebench.harness.test_spec.test_spec import make_test_spec

def main():
    print("🐋 Building SWE-bench Docker environment images...")
    
    # Initialize Docker client
    try:
        client = docker.from_env()
        print(f"✅ Docker client connected: {client.version()['Version']}")
    except Exception as e:
        print(f"❌ Failed to connect to Docker: {e}")
        return 1
    
    # Get data points directory
    data_points_dir = Path("data_points")
    if not data_points_dir.exists():
        print(f"❌ Data points directory not found: {data_points_dir}")
        return 1
    
    # Load all data points and create test specs
    test_specs = []
    data_point_files = list(data_points_dir.glob("*.json"))
    
    print(f"📄 Found {len(data_point_files)} data point files")
    
    for file_path in data_point_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data_point = json.load(f)
            
            # Create test spec for each data point
            test_spec = make_test_spec(data_point)
            test_specs.append(test_spec)
            print(f"  ✅ {file_path.name} -> {data_point.get('repo', 'unknown')}")
            
        except Exception as e:
            print(f"  ❌ Failed to load {file_path.name}: {e}")
            continue
    
    if not test_specs:
        print("❌ No valid test specs found")
        return 1
    
    print(f"\n🏗️ Building environment images for {len(test_specs)} data points...")
    print("This may take 10-30 minutes depending on repository complexity...")
    
    try:
        # Build environment images
        build_env_images(
            client=client,
            dataset=test_specs,
            force_rebuild=False,  # Only build if not exists
            max_workers=2  # Limit workers to avoid resource issues
        )
        print("✅ Environment images built successfully!")
        
        # List created images
        print("\n📋 SWE-bench Docker images:")
        images = client.images.list()
        swe_images = [img for img in images if any(tag.startswith('sweb.') for tag in img.tags)]
        
        if swe_images:
            for img in swe_images:
                for tag in img.tags:
                    if tag.startswith('sweb.'):
                        print(f"  🐋 {tag}")
        else:
            print("  ⚠️ No SWE-bench images found (may have been built with different tags)")
        
        return 0
        
    except Exception as e:
        print(f"❌ Failed to build environment images: {e}")
        print(f"Error type: {type(e).__name__}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
