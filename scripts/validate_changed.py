#!/usr/bin/env python3
"""
Script for validating changed SWE-bench data points.
Used by GitHub Actions workflow.
"""

import json
import subprocess
import sys
import os
from pathlib import Path


def main():
    print("🔍 Starting SWE-bench data point validation...")
    print("=" * 50)
    
    # Debug environment
    print("Environment debug:")
    print(f"  - Current directory: {os.getcwd()}")
    print(f"  - Python version: {sys.version}")
    print(f"  - PATH: {os.environ.get('PATH', 'not set')}")
    
    # Get changed files from environment
    changed_files_json = os.environ.get('CHANGED_FILES_JSON', '')
    changed_files_raw = os.environ.get('CHANGED_FILES', '')
    if changed_files_json:
        print(f"  - CHANGED_FILES_JSON length: {len(changed_files_json)}")
    print(f"  - CHANGED_FILES env var: '{changed_files_raw}'")
    
    if not changed_files_json and not changed_files_raw:
        print("❌ No CHANGED_FILES environment variable found")
        print("Available environment variables:")
        for key in sorted(os.environ.keys()):
            if 'CHANGED' in key or 'GITHUB' in key:
                print(f"  - {key}: {os.environ[key]}")
        return 1
    
    changed_files = []
    # Prefer JSON when available to safely handle spaces
    if changed_files_json:
        try:
            parsed = json.loads(changed_files_json)
            if isinstance(parsed, list):
                changed_files = [str(p).strip() for p in parsed if str(p).strip()]
            else:
                print("⚠️ CHANGED_FILES_JSON is not a list; falling back to CHANGED_FILES")
        except Exception as e:
            print(f"⚠️ Failed to parse CHANGED_FILES_JSON: {e}; falling back to CHANGED_FILES")
    if not changed_files and changed_files_raw:
        changed_files = [f.strip() for f in changed_files_raw.split('\n') if f.strip()]

    if not changed_files:
        print("📭 No files to validate (empty list)")
        return 0

    print(f"📄 Validating {len(changed_files)} changed data points:")
    for i, file_path in enumerate(changed_files, 1):
        print(f"  {i}. {file_path}")
    print("=" * 50)

    results = []
    for i, file_path in enumerate(changed_files, 1):
        print(f"\n🔄 [{i}/{len(changed_files)}] Processing {file_path}...")
        
        # Check if file exists
        if not Path(file_path).exists():
            print(f"❌ File {file_path} not found!")
            print(f"Current directory: {os.getcwd()}")
            print(f"Available files in data_points/:")
            data_points_dir = Path("data_points")
            if data_points_dir.exists():
                for f in data_points_dir.glob("*.json"):
                    print(f"  - {f}")
            else:
                print("  data_points/ directory not found")
            results.append({'file': file_path, 'status': 'FILE_NOT_FOUND', 'error': f'File {file_path} does not exist'})
            continue
        
        # Validate JSON structure
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            print(f"✅ JSON structure is valid")
            print(f"  - Instance ID: {data.get('instance_id', 'MISSING')}")
            print(f"  - Repository: {data.get('repo', 'MISSING')}")
            print(f"  - Has patch: {'✅' if data.get('patch') else '❌'}")
            print(f"  - Has test_patch: {'✅' if data.get('test_patch') else '❌'}")
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in {file_path}: {e}")
            results.append({'file': file_path, 'status': 'INVALID_JSON', 'error': f'JSON decode error: {e}'})
            continue
        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")
            results.append({'file': file_path, 'status': 'READ_ERROR', 'error': f'Read error: {e}'})
            continue
            
        print(f"🚀 Running SWE-bench validation...")
        try:
            # Run validation for single instance
            instance_id = Path(file_path).stem
            print(f"  Instance ID: {instance_id}")
            
            cmd = ['python', '-m', 'swe_bench_validator', '--instance', instance_id]
            print(f"  Command: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            print(f"  Return code: {result.returncode}")
            if result.stdout:
                print(f"  Stdout: {result.stdout[:500]}...")
            if result.stderr:
                print(f"  Stderr: {result.stderr[:500]}...")
            
            if result.returncode == 0:
                print(f"✅ {instance_id}: PASSED")
                results.append({'file': file_path, 'status': 'PASSED', 'error': None})
            else:
                print(f"❌ {instance_id}: FAILED")
                print(f"Full error output:")
                print(result.stderr)
                if result.stdout:
                    print(f"Standard output:")
                    print(result.stdout)
                results.append({'file': file_path, 'status': 'FAILED', 'error': result.stderr})
                
        except subprocess.TimeoutExpired:
            print(f"⏰ {instance_id}: TIMEOUT (>600s)")
            results.append({'file': file_path, 'status': 'TIMEOUT', 'error': 'Validation timed out after 600 seconds'})
        except Exception as e:
            print(f"💥 {instance_id}: UNEXPECTED ERROR")
            print(f"Exception: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append({'file': file_path, 'status': 'ERROR', 'error': f'{type(e).__name__}: {str(e)}'})

    # Generate detailed summary
    print("\n" + "=" * 50)
    print("📊 VALIDATION SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for r in results if r['status'] == 'PASSED')
    failed = len(results) - passed
    
    # Categorize failures
    status_counts = {}
    for result in results:
        status = result['status']
        status_counts[status] = status_counts.get(status, 0) + 1

    print(f"📈 Overall Results:")
    print(f"  • Total files processed: {len(results)}")
    print(f"  • ✅ Passed: {passed}")
    print(f"  • ❌ Failed: {failed}")
    print(f"  • Success rate: {(passed/len(results)*100):.1f}%" if results else "0%")
    
    print(f"\n📋 Breakdown by status:")
    for status, count in status_counts.items():
        emoji = "✅" if status == "PASSED" else "❌"
        print(f"  • {emoji} {status}: {count}")
    
    # Show failed files with details
    failed_results = [r for r in results if r['status'] != 'PASSED']
    if failed_results:
        print(f"\n🔍 FAILED VALIDATIONS DETAILS:")
        print("-" * 30)
        for result in failed_results:
            print(f"❌ {result['file']}")
            print(f"   Status: {result['status']}")
            if result['error']:
                # Show first few lines of error
                error_lines = result['error'].split('\n')[:3]
                for line in error_lines:
                    if line.strip():
                        print(f"   Error: {line.strip()}")
                if len(result['error'].split('\n')) > 3:
                    print(f"   ... (truncated)")
            print()

    # Set output for GitHub Actions
    if 'GITHUB_OUTPUT' in os.environ:
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f"passed={passed}\n")
            f.write(f"failed={failed}\n")
            f.write(f"total={len(results)}\n")
        print(f"📤 GitHub Actions outputs set: passed={passed}, failed={failed}, total={len(results)}")

    print("=" * 50)
    if failed > 0:
        print("❌ VALIDATION FAILED!")
        print("💡 Check the detailed error messages above and fix the issues.")
        return 1
    else:
        print("✅ ALL VALIDATIONS PASSED!")
        return 0


if __name__ == "__main__":
    sys.exit(main())

