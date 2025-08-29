"""
Core validator functionality for SWE-bench data points.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

# SWE-bench library imports
from swebench.harness.run_evaluation import run_instance
from swebench.harness.test_spec.test_spec import make_test_spec, TestSpec
from swebench.harness.constants import (
    KEY_INSTANCE_ID,
    KEY_MODEL,
    KEY_PREDICTION,
    FAIL_TO_PASS,
    PASS_TO_PASS,
)

console = Console()
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating a single data point."""
    instance_id: str
    success: bool
    patch_applied: bool
    tests_passed: bool
    error_message: Optional[str] = None
    execution_time: Optional[float] = None
    test_results: Optional[Dict[str, Any]] = None


class SWEBenchValidator:
    """
    Validates SWE-bench data points using the official evaluation harness.
    
    This validator:
    1. Loads data points from JSON files
    2. Converts them to SWE-bench prediction format
    3. Runs evaluation using the harness
    4. Validates test results
    """
    
    def __init__(
        self,
        data_points_dir: Path = Path("data_points"),
        timeout: int = 300,
        max_workers: int = 1,
        cache_level: str = "base",
        verbose: bool = False,
        force_rebuild: bool = False,
    ):
        """
        Initialize the SWE-bench validator.
        
        Args:
            data_points_dir: Directory containing JSON data point files
            timeout: Timeout for test execution in seconds
            max_workers: Maximum number of parallel workers
            cache_level: Docker cache level (none, base, env, instance)
            verbose: Enable verbose logging
            force_rebuild: Force rebuild of Docker images
        """
        self.data_points_dir = Path(data_points_dir)
        self.timeout = timeout
        self.max_workers = max_workers
        self.cache_level = cache_level
        self.verbose = verbose
        self.force_rebuild = force_rebuild
        
        # Setup logging
        if verbose:
            logging.basicConfig(level=logging.INFO)
        
        # Validate data points directory
        if not self.data_points_dir.exists():
            raise ValueError(f"Data points directory does not exist: {self.data_points_dir}")
        
        # Initialize Docker client
        try:
            import docker
            self.docker_client = docker.from_env()
        except ImportError:
            raise ImportError("Docker library not installed. Install with: pip install docker")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Docker client: {str(e)}")
    
    def _load_data_point(self, file_path: Path) -> Dict[str, Any]:
        """Load a single data point from JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate required fields
            required_fields = [
                'instance_id', 'repo', 'base_commit', 'patch',
                'FAIL_TO_PASS', 'PASS_TO_PASS'
            ]
            
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")
            
            return data
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {file_path}: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Failed to load {file_path}: {str(e)}")
    
    def _convert_to_prediction(self, data_point: Dict[str, Any]) -> Dict[str, str]:
        """Convert data point to SWE-bench prediction format."""
        return {
            KEY_INSTANCE_ID: data_point['instance_id'],
            KEY_MODEL: "gold",  # For validating golden patches
            KEY_PREDICTION: data_point['patch']
        }
    
    def _validate_test_results(self, test_output: str, data_point: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate test results against FAIL_TO_PASS and PASS_TO_PASS requirements.
        
        Returns:
            (tests_passed, test_results)
        """
        test_results = {
            'patch_applied': False,
            'fail_to_pass_passed': False,
            'pass_to_pass_passed': False,
            'test_output': test_output
        }
        
        # Check if patch was applied
        if ">>>>> Applied Patch" in test_output:
            test_results['patch_applied'] = True
        elif ">>>>> Patch Apply Failed" in test_output:
            return False, test_results
        
        # Check test execution results
        if ">>>>> All Tests Passed" in test_output:
            test_results['fail_to_pass_passed'] = True
            test_results['pass_to_pass_passed'] = True
            return True, test_results
        elif ">>>>> Some Tests Failed" in test_output:
            # Need to analyze which specific tests failed
            test_results['fail_to_pass_passed'] = False
            test_results['pass_to_pass_passed'] = False
            return False, test_results
        elif ">>>>> Tests Timed Out" in test_output:
            test_results['timeout'] = True
            return False, test_results
        elif ">>>>> Tests Errored" in test_output:
            test_results['error'] = True
            return False, test_results
        
        return False, test_results
    
    def validate_single_data_point(self, file_path: Path) -> ValidationResult:
        """
        Validate a single data point file.
        
        Args:
            file_path: Path to the JSON data point file
            
        Returns:
            ValidationResult with validation details
        """
        instance_id = file_path.stem
        start_time = time.time()
        
        try:
            # Load data point
            data_point = self._load_data_point(file_path)
            
            # Convert to prediction format
            prediction = self._convert_to_prediction(data_point)
            
            # Create test specification
            test_spec = make_test_spec(data_point)
            
            # Run evaluation (Docker harness)
            run_id = f"validation-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            if self.verbose:
                console.print(f"Running validation for {instance_id} using SWE-bench harness...")

            # Ensure required Docker images (base/env) exist or are built
            try:
                self._ensure_required_images(test_spec)
            except Exception as e:
                logger.warning(f"Failed to pre-build/ensure images: {e}")

            validation_success, test_results = self._run_with_harness(
                data_point=data_point,
                prediction=prediction,
                test_spec=test_spec,
                run_id=run_id,
            )
            
            execution_time = time.time() - start_time
            
            if validation_success:
                return ValidationResult(
                    instance_id=instance_id,
                    success=True,
                    patch_applied=bool(test_results.get('patch_applied', True)),
                    tests_passed=bool(test_results.get('tests_passed', True)),
                    execution_time=execution_time,
                    test_results=test_results or {'status': 'PASSED'}
                )
            else:
                return ValidationResult(
                    instance_id=instance_id,
                    success=False,
                    patch_applied=bool(test_results.get('patch_applied', False)),
                    tests_passed=bool(test_results.get('tests_passed', False)),
                    error_message=test_results.get('error') or "Validation failed",
                    execution_time=execution_time
                )
                
        except Exception as e:
            execution_time = time.time() - start_time
            return ValidationResult(
                instance_id=instance_id,
                success=False,
                patch_applied=False,
                tests_passed=False,
                error_message=str(e),
                execution_time=execution_time
            )
    
    def _run_with_harness(
        self,
        data_point: Dict[str, Any],
        prediction: Dict[str, str],
        test_spec: TestSpec,
        run_id: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Run SWE-bench harness for a single instance with defensive signature handling."""
        import os
        import inspect

        # Pass cache level via env for harness if supported
        if self.cache_level:
            os.environ['SWE_BENCH_CACHE_LEVEL'] = str(self.cache_level)

        # Compose kwargs based on available parameters in run_instance
        try:
            sig = inspect.signature(run_instance)
            params = sig.parameters
        except Exception:
            params = {}

        call_kwargs = {}
        # Commonly supported parameters across versions
        if 'test_spec' in params:
            call_kwargs['test_spec'] = test_spec
        if 'pred' in params:
            call_kwargs['pred'] = prediction
        elif 'prediction' in params:
            call_kwargs['prediction'] = prediction
        # Optional commonly required runtime args
        if 'run_id' in params and run_id:
            call_kwargs['run_id'] = run_id
        # Docker client param names vary
        if 'client' in params and hasattr(self, 'docker_client'):
            call_kwargs['client'] = self.docker_client
        if 'docker_client' in params and hasattr(self, 'docker_client'):
            call_kwargs['docker_client'] = self.docker_client
        # Image removal flags may vary
        if 'rm_image' in params:
            call_kwargs['rm_image'] = False
        if 'remove_image' in params:
            call_kwargs['remove_image'] = False
        # Build/ensure flags (help auto-build missing env/instance images)
        for key in (
            'build_env', 'build_images', 'build_missing', 'ensure_env',
            'ensure_images', 'rebuild_env', 'rebuild'
        ):
            if key in params:
                # Prefer force_rebuild to drive rebuild when requested
                call_kwargs[key] = bool(self.force_rebuild) or key in ('build_env', 'build_images', 'build_missing', 'ensure_env', 'ensure_images')

        if 'cache_level' in params and self.cache_level:
            call_kwargs['cache_level'] = self.cache_level
        if 'timeout' in params and self.timeout:
            call_kwargs['timeout'] = int(self.timeout)
        if 'force_rebuild' in params:
            call_kwargs['force_rebuild'] = bool(self.force_rebuild)
        if 'num_workers' in params and self.max_workers:
            call_kwargs['num_workers'] = int(self.max_workers)
        if 'max_workers' in params and self.max_workers:
            call_kwargs['max_workers'] = int(self.max_workers)
        if 'verbose' in params:
            call_kwargs['verbose'] = bool(self.verbose)

        # Fallback positional args if names not present
        call_args = []
        if not call_kwargs:
            call_args = [test_spec, prediction]

        try:
            result = run_instance(*call_args, **call_kwargs)
        except Exception as e:
            return False, {'error': f"Harness execution error: {type(e).__name__}: {e}", 'patch_applied': False, 'tests_passed': False}

        # Interpret result in a defensive way
        test_results: Dict[str, Any] = {}
        success = False

        try:
            if isinstance(result, dict):
                # Common keys
                status = str(result.get('status') or result.get('eval_status') or '').upper()
                success = bool(result.get('success')) or status == 'PASSED'
                # If harness provides more detailed results
                test_results.update(result)
            elif isinstance(result, (list, tuple)) and result:
                # Sometimes returns (success, details)
                if isinstance(result[0], bool):
                    success = result[0]
                # Try to capture text output
                if len(result) > 1 and isinstance(result[1], str):
                    test_results['test_output'] = result[1]
            elif isinstance(result, bool):
                success = result
            elif isinstance(result, str):
                # Parse sentinel markers from output
                output = result
                test_results['test_output'] = output
                if ">>>>> All Tests Passed" in output:
                    success = True
                elif ">>>>> Patch Apply Failed" in output:
                    success = False
            
            # Derive flags from output if available
            output_text = str(test_results.get('test_output') or '')
            if output_text:
                if ">>>>> Applied Patch" in output_text:
                    test_results['patch_applied'] = True
                if ">>>>> All Tests Passed" in output_text:
                    test_results['tests_passed'] = True

        except Exception:
            # If parsing fails, rely on truthiness of result
            success = bool(result)

        return success, test_results

    def _ensure_required_images(self, test_spec: TestSpec) -> None:
        """Try to ensure base/env images are present by invoking docker_build helpers if available."""
        try:
            import swebench.harness.docker_build as db
        except Exception as e:
            logger.info(f"docker_build module not available: {e}")
            return

        def _call_helper(func) -> None:
            import inspect
            try:
                sig = inspect.signature(func)
                params = sig.parameters
            except Exception:
                params = {}
            kwargs = {}
            if 'test_spec' in params:
                kwargs['test_spec'] = test_spec
            if 'client' in params and hasattr(self, 'docker_client'):
                kwargs['client'] = self.docker_client
            if 'docker_client' in params and hasattr(self, 'docker_client'):
                kwargs['docker_client'] = self.docker_client
            if 'logger' in params:
                kwargs['logger'] = logger
            # nocache flags to force rebuild when requested
            for k in ('nocache', 'no_cache', 'force_rebuild', 'rebuild'):
                if k in params:
                    kwargs[k] = bool(self.force_rebuild)
            try:
                func(**kwargs)
            except TypeError:
                # try positional fallback: (test_spec, client, logger, nocache)
                args = []
                if 'test_spec' in params:
                    args.append(test_spec)
                if 'client' in params and hasattr(self, 'docker_client'):
                    args.append(self.docker_client)
                if 'logger' in params:
                    args.append(logger)
                if 'nocache' in params:
                    args.append(bool(self.force_rebuild))
                func(*args)

        # Try base image helpers
        for name in (
            'ensure_base_image', 'build_base_image', 'build_base',
        ):
            if hasattr(db, name):
                _call_helper(getattr(db, name))
                break

        # Try environment image helpers
        for name in (
            'ensure_env_image', 'build_env_image', 'build_environment_image', 'build_env',
        ):
            if hasattr(db, name):
                _call_helper(getattr(db, name))
                break
    
    def validate_directory(self, progress_callback: Optional[callable] = None) -> List[ValidationResult]:
        """
        Validate all data points in the directory.
        
        Args:
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of ValidationResult objects
        """
        json_files = list(self.data_points_dir.glob("*.json"))
        
        if not json_files:
            console.print("[yellow]No JSON files found in data_points directory[/yellow]")
            return []
        
        if progress_callback:
            progress_callback(f"Found {len(json_files)} data points to validate")
        
        results = []
        
        for i, file_path in enumerate(json_files):
            if progress_callback:
                progress_callback(f"Validating {i+1}/{len(json_files)}: {file_path.name}")
            
            result = self.validate_single_data_point(file_path)
            results.append(result)
            
            if self.verbose:
                status = "✅" if result.success else "❌"
                console.print(f"{status} {file_path.name}: {result.success}")
        
        return results
    
    def generate_validation_report(self, results: List[ValidationResult]) -> str:
        """Generate a human-readable validation report."""
        if not results:
            return "No validation results to report."
        
        # Count results
        total = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total - successful
        
        # Create summary table
        table = Table(title="SWE-bench Data Point Validation Report")
        table.add_column("Instance ID", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Patch Applied", style="blue")
        table.add_column("Tests Passed", style="blue")
        table.add_column("Execution Time", style="yellow")
        table.add_column("Error", style="red")
        
        for result in results:
            status = "✅ PASS" if result.success else "❌ FAIL"
            patch_status = "✅" if result.patch_applied else "❌"
            tests_status = "✅" if result.tests_passed else "❌"
            time_str = f"{result.execution_time:.2f}s" if result.execution_time else "N/A"
            error_str = result.error_message or ""
            
            table.add_row(
                result.instance_id,
                status,
                patch_status,
                tests_status,
                time_str,
                error_str
            )
        
        # Generate report
        report = f"""
# SWE-bench Validation Report

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Total Data Points**: {total}
**Successful Validations**: {successful}
**Failed Validations**: {failed}
**Success Rate**: {(successful/total)*100:.1f}%

## Summary
{table}

## Details
"""
        
        # Add detailed results
        for result in results:
            if not result.success:
                report += f"\n### {result.instance_id} - FAILED\n"
                report += f"- **Error**: {result.error_message}\n"
                if result.test_results:
                    report += f"- **Test Results**: {result.test_results}\n"
        
        return report

