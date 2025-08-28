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
            
            # Run evaluation
            run_id = f"validation-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            
            if self.verbose:
                console.print(f"Running validation for {instance_id}...")
            
            # Run the actual SWE-bench evaluation harness
            validation_success, test_results = self._run_evaluation_harness(data_point, prediction, test_spec)
            
            execution_time = time.time() - start_time
            
            if validation_success:
                return ValidationResult(
                    instance_id=instance_id,
                    success=True,
                    patch_applied=test_results.get('patch_applied', True),
                    tests_passed=test_results.get('tests_passed', True),
                    execution_time=execution_time,
                    test_results=test_results
                )
            else:
                return ValidationResult(
                    instance_id=instance_id,
                    success=False,
                    patch_applied=test_results.get('patch_applied', False),
                    tests_passed=test_results.get('tests_passed', False),
                    error_message=test_results.get('error_message', 'Validation failed'),
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
    
    def _run_evaluation_harness(self, data_point: Dict[str, Any], prediction: Dict[str, str], test_spec: TestSpec) -> Tuple[bool, Dict[str, Any]]:
        """
        Run the actual SWE-bench evaluation harness to validate the data point.
        
        Args:
            data_point: The data point to validate
            prediction: The prediction in SWE-bench format
            test_spec: The test specification
            
        Returns:
            (validation_success, test_results)
        """
        try:
            if self.verbose:
                console.print(f"[cyan]Running SWE-bench harness for {prediction[KEY_INSTANCE_ID]}[/cyan]")
            
            # Run the official SWE-bench evaluation
            # This is the key function that actually validates the patch
            eval_result = run_instance(
                test_spec=test_spec,
                pred=prediction,
                run_id=f"validation-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                timeout=self.timeout,
                rm_image=not self.cache_level == "instance",
                force_rebuild=self.force_rebuild,
                client=self.docker_client
            )
            
            if self.verbose:
                console.print(f"[cyan]Evaluation result: {eval_result}[/cyan]")
            
            # Parse the evaluation result
            test_results = {
                'eval_result': eval_result,
                'patch_applied': False,
                'tests_passed': False
            }
            
            # Check if the evaluation was successful
            if eval_result and 'report' in eval_result:
                report = eval_result['report']
                
                # Check if patch was applied successfully
                if report.get('applied', False):
                    test_results['patch_applied'] = True
                
                # Check if tests passed
                # The evaluation is successful if all FAIL_TO_PASS tests now pass
                # and all PASS_TO_PASS tests continue to pass
                if report.get('resolved', False):
                    test_results['tests_passed'] = True
                    return True, test_results
                else:
                    # Get details about failed tests
                    test_results['failed_tests'] = report.get('failed_tests', [])
                    test_results['error_message'] = report.get('error_message', 'Tests failed')
                    return False, test_results
            else:
                test_results['error_message'] = 'Evaluation harness failed to run'
                return False, test_results
                
        except Exception as e:
            error_msg = f"Error running evaluation harness: {str(e)}"
            if self.verbose:
                console.print(f"[red]{error_msg}[/red]")
            
            test_results = {
                'error_message': error_msg,
                'patch_applied': False,
                'tests_passed': False
            }
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

