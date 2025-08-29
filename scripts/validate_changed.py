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

    def sanitize_path(p: str) -> str:
        # Trim whitespace and carriage returns
        cleaned = p.strip().rstrip('\r')
        # Strip surrounding quotes
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
            cleaned = cleaned[1:-1]
        # Remove any trailing backslashes introduced by shell wrapping
        while cleaned.endswith('\\'):
            cleaned = cleaned[:-1]
        # Normalize path separators
        return os.path.normpath(cleaned)
    # Prefer JSON when available to safely handle spaces
    if changed_files_json:
        try:
            parsed = json.loads(changed_files_json)
            if isinstance(parsed, list):
                changed_files = [sanitize_path(str(p)) for p in parsed if str(p).strip()]
            else:
                print("⚠️ CHANGED_FILES_JSON is not a list; falling back to CHANGED_FILES")
        except Exception as e:
            print(f"⚠️ Failed to parse CHANGED_FILES_JSON: {e}; falling back to CHANGED_FILES")
    if not changed_files and changed_files_raw:
        changed_files = [sanitize_path(f) for f in changed_files_raw.split('\n') if f.strip()]

    # Remove duplicates while preserving order
    seen = set()
    deduped = []
    for f in changed_files:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    changed_files = deduped

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
            
        print(f"🚀 Building and running inside SWE-bench container...")
        try:
            # Prepare harness components
            from swebench.harness.test_spec.test_spec import make_test_spec
            from swebench.harness.run_evaluation import run_instance
            import swebench.harness.docker_build as db  # type: ignore
            import docker  # type: ignore
            import inspect
            from datetime import datetime

            # Create TestSpec from local datapoint (no dataset dependency)
            with open(file_path, 'r', encoding='utf-8') as f:
                dp = json.load(f)
            test_spec = make_test_spec(dp)

            # Ensure base/env images
            client = docker.from_env()

            def call_helper(func, force=False):
                try:
                    sig = inspect.signature(func)
                    params = sig.parameters
                except Exception:
                    params = {}
                kwargs = {}
                if 'test_spec' in params:
                    kwargs['test_spec'] = test_spec
                if 'client' in params:
                    kwargs['client'] = client
                if 'docker_client' in params:
                    kwargs['docker_client'] = client
                for k in ('nocache','no_cache','force_rebuild','rebuild','ensure'):
                    if k in params:
                        kwargs[k] = True if force else False
                try:
                    func(**kwargs)
                    return True
                except TypeError:
                    args = []
                    if 'test_spec' in params: args.append(test_spec)
                    if 'client' in params: args.append(client)
                    if 'nocache' in params: args.append(bool(force))
                    func(*args)
                    return True
                except Exception as e:
                    print(f"  Helper {getattr(func,'__name__','<func>')} failed: {e}")
                    return False

            # Base image
            for name in ('ensure_base_image','build_base_image','build_base'):
                if hasattr(db, name):
                    print(f"  Calling {name}()")
                    call_helper(getattr(db, name), force=True)
                    break

            # Env image
            env_ok = False
            for name in ('ensure_env_image','build_env_image','build_environment_image','build_env'):
                if hasattr(db, name):
                    print(f"  Calling {name}()")
                    if call_helper(getattr(db, name), force=True):
                        env_ok = True
                        break
            if not env_ok:
                print("  ⚠️ No environment build helper found; proceeding to run_instance")

            # Run evaluation for this TestSpec using run_instance with defensive signature
            import os as _os
            _os.environ['SWE_BENCH_CACHE_LEVEL'] = _os.environ.get('SWE_BENCH_CACHE_LEVEL','base')

            try:
                sig = inspect.signature(run_instance)
                params = sig.parameters
            except Exception:
                params = {}

            pred = { 'instance_id': dp.get('instance_id','local'), 'model_name_or_path': 'gold', 'model_patch': dp.get('patch','') }
            call_kwargs = {}
            if 'test_spec' in params: call_kwargs['test_spec'] = test_spec
            if 'pred' in params: call_kwargs['pred'] = pred
            elif 'prediction' in params: call_kwargs['prediction'] = pred
            if 'client' in params: call_kwargs['client'] = client
            if 'docker_client' in params: call_kwargs['docker_client'] = client
            # Provide a stable run_id
            run_id = f"validation-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
            if 'run_id' in params: call_kwargs['run_id'] = run_id
            if 'cache_level' in params: call_kwargs['cache_level'] = _os.environ['SWE_BENCH_CACHE_LEVEL']
            if 'timeout' in params: call_kwargs['timeout'] = 600
            if 'force_rebuild' in params: call_kwargs['force_rebuild'] = True
            if 'num_workers' in params: call_kwargs['num_workers'] = 1
            if 'max_workers' in params: call_kwargs['max_workers'] = 1
            if 'rm_image' in params: call_kwargs['rm_image'] = False
            if 'remove_image' in params: call_kwargs['remove_image'] = False

            call_args = []
            if not call_kwargs:
                call_args = [test_spec, pred]

            instance_id = Path(file_path).stem
            print(f"  Instance ID: {instance_id}")
            result = None
            try:
                result = run_instance(*call_args, **call_kwargs)
            except Exception as e:
                print(f"  run_instance error: {e}")
                results.append({'file': file_path, 'status': 'FAILED', 'error': str(e)})
                continue

            # Interpret result
            success = False
            if isinstance(result, dict):
                status = str(result.get('status') or result.get('eval_status') or '').upper()
                success = bool(result.get('success')) or status == 'PASSED'
            elif isinstance(result, bool):
                success = result

            if success:
                print(f"✅ {instance_id}: PASSED")
                results.append({'file': file_path, 'status': 'PASSED', 'error': None})
            else:
                print(f"❌ {instance_id}: FAILED")
                results.append({'file': file_path, 'status': 'FAILED', 'error': str(result)})

        except Exception as e:
            instance_id = Path(file_path).stem
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

