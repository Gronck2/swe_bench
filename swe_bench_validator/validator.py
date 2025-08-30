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


class SWEBenchValidatorError(Exception):
    """Base exception for SWE-bench validator errors."""
    pass


class DockerError(SWEBenchValidatorError):
    """Docker-related errors."""
    pass


class ValidationError(SWEBenchValidatorError):
    """Validation-specific errors."""
    pass


class TimeoutError(SWEBenchValidatorError):
    """Timeout-related errors."""
    pass


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
            raise DockerError("Docker library not installed. Install with: pip install docker")
        except Exception as e:
            raise DockerError(f"Failed to initialize Docker client: {str(e)}")

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
            raise ValidationError(f"Invalid JSON in {file_path}: {str(e)}")
        except Exception as e:
            raise ValidationError(f"Failed to load {file_path}: {str(e)}")
    
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
            
            # Run evaluation
            if self.verbose:
                console.print(f"Running validation for {instance_id}...")

            # Run actual validation using SWE-bench harness
            validation_success, test_results = self._run_validation(data_point, prediction, test_spec)

            execution_time = time.time() - start_time

            if validation_success:
                return ValidationResult(
                    instance_id=instance_id,
                    success=True,
                    patch_applied=test_results.get('patch_applied', False),
                    tests_passed=test_results.get('fail_to_pass_passed', False) and test_results.get('pass_to_pass_passed', False),
                    execution_time=execution_time,
                    test_results=test_results
                )
            else:
                error_msg = test_results.get('error', 'Validation failed')
                if 'timeout' in test_results:
                    error_msg = f"Validation timed out after {self.timeout} seconds"
                elif 'error' in test_results:
                    error_msg = "Validation encountered an error during execution"

                return ValidationResult(
                    instance_id=instance_id,
                    success=False,
                    patch_applied=test_results.get('patch_applied', False),
                    tests_passed=False,
                    error_message=error_msg,
                    execution_time=execution_time,
                    test_results=test_results
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
    
    def _run_validation(self, data_point: Dict[str, Any], prediction: Dict[str, str], test_spec: TestSpec) -> Tuple[bool, Dict[str, Any]]:
        """
        Run actual validation using SWE-bench harness.

        Returns:
            (success, test_results)
        """
        import tempfile
        import os
        from pathlib import Path

        test_results = {
            'patch_applied': False,
            'fail_to_pass_passed': False,
            'pass_to_pass_passed': False,
            'test_output': '',
            'error': None
        }

        try:
            # Create temporary directory for logs
            with tempfile.TemporaryDirectory() as temp_dir:
                log_dir = Path(temp_dir) / "validation_logs"
                log_dir.mkdir(exist_ok=True)

                # Calculate timeout with multiplier based on instance type
                instance_id = data_point.get('instance_id', '')
                repo = data_point.get('repo', '')
                multiplier = 1.0

                # Apply timeout multiplier based on repo
                timeout_multipliers = {
                    'django': 1.5,
                    'astropy': 1.0,
                    'matplotlib': 1.2,
                    'scikit_learn': 1.0
                }

                for repo_key, mult in timeout_multipliers.items():
                    if repo_key in repo:
                        multiplier = mult
                        break

                adjusted_timeout = int(self.timeout * multiplier)

                if self.verbose:
                    console.print(f"Running evaluation with timeout: {adjusted_timeout}s (multiplier: {multiplier})")

                # Run the evaluation
                result = run_instance(
                    test_spec=test_spec,
                    pred=prediction,
                    rm_image=False,  # Keep images for debugging
                    timeout=adjusted_timeout,
                    force_rebuild=self.force_rebuild,
                    client=self.docker_client,  # Pass Docker client
                    run_id=f"validation-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                )

                # Parse results
                if result:
                    # SWE-bench harness returns a dict with instance_id as key
                    instance_id = data_point.get('instance_id', '')
                    if instance_id in result:
                        instance_result = result[instance_id]
                        test_results['instance_result'] = instance_result

                        # Check if patch was applied
                        test_results['patch_applied'] = instance_result.get('patch_successfully_applied', False)

                        # Check if resolved (all tests passed)
                        resolved = instance_result.get('resolved', False)
                        test_results['resolved'] = resolved

                        # Get test status details
                        tests_status = instance_result.get('tests_status', {})

                        # Check FAIL_TO_PASS tests
                        fail_to_pass = tests_status.get('FAIL_TO_PASS', {})
                        fail_to_pass_success = len(fail_to_pass.get('failure', [])) == 0 and len(fail_to_pass.get('success', [])) > 0
                        test_results['fail_to_pass_passed'] = fail_to_pass_success

                        # Check PASS_TO_PASS tests
                        pass_to_pass = tests_status.get('PASS_TO_PASS', {})
                        pass_to_pass_success = len(pass_to_pass.get('failure', [])) == 0
                        test_results['pass_to_pass_passed'] = pass_to_pass_success

                        # Overall success
                        if resolved and fail_to_pass_success and pass_to_pass_success:
                            return True, test_results
                        else:
                            return False, test_results
                    else:
                        test_results['error'] = f"No result found for instance {instance_id}"
                        return False, test_results
                else:
                    test_results['error'] = "No result returned from evaluation"
                    return False, test_results

        except TimeoutError as e:
            test_results['error'] = f"Validation timed out: {str(e)}"
            test_results['timeout'] = True
            if self.verbose:
                logger.warning(f"Timeout during validation: {e}")
            return False, test_results
        except DockerError as e:
            test_results['error'] = f"Docker error: {str(e)}"
            test_results['docker_error'] = True
            if self.verbose:
                logger.error(f"Docker error during validation: {e}")
            return False, test_results
        except ValidationError as e:
            test_results['error'] = f"Validation error: {str(e)}"
            test_results['validation_error'] = True
            if self.verbose:
                logger.error(f"Validation error: {e}")
            return False, test_results
        except Exception as e:
            test_results['error'] = f"Unexpected error: {str(e)}"
            test_results['unexpected_error'] = True
            if self.verbose:
                logger.exception(f"Unexpected error during validation: {e}")
            return False, test_results
    
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

