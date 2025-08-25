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
    # Get changed files from environment
    changed_files = os.environ.get('CHANGED_FILES', '').split('\n')
    changed_files = [f.strip() for f in changed_files if f.strip()]

    if not changed_files:
        print("No files to validate")
        return 0

    print(f"Validating {len(changed_files)} changed data points...")

    results = []
    for file_path in changed_files:
        if not Path(file_path).exists():
            print(f"Warning: File {file_path} not found, skipping")
            continue
            
        print(f"Validating {file_path}...")
        try:
            # Run validation for single instance
            instance_id = Path(file_path).stem
            result = subprocess.run([
                'python', '-m', 'swe_bench_validator',
                '--instance', instance_id,
                '--verbose',
            ], capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0:
                print(f"✅ {instance_id}: PASSED")
                results.append({'file': file_path, 'status': 'PASSED', 'error': None})
            else:
                print(f"❌ {instance_id}: FAILED")
                print(f"Error output: {result.stderr}")
                results.append({'file': file_path, 'status': 'FAILED', 'error': result.stderr})
                
        except subprocess.TimeoutExpired:
            print(f"⏰ {instance_id}: TIMEOUT")
            results.append({'file': file_path, 'status': 'TIMEOUT', 'error': 'Validation timed out'})
        except Exception as e:
            print(f"💥 {instance_id}: ERROR - {str(e)}")
            results.append({'file': file_path, 'status': 'ERROR', 'error': str(e)})

    # Generate summary
    passed = sum(1 for r in results if r['status'] == 'PASSED')
    failed = len(results) - passed

    print(f"\nValidation Summary:")
    print(f"  • Total: {len(results)}")
    print(f"  • Passed: {passed}")
    print(f"  • Failed: {failed}")

    # Set output for GitHub Actions
    if 'GITHUB_OUTPUT' in os.environ:
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f"passed={passed}\n")
            f.write(f"failed={failed}\n")
            f.write(f"total={len(results)}\n")

    if failed > 0:
        print("❌ Some validations failed!")
        return 1
    else:
        print("✅ All validations passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())

