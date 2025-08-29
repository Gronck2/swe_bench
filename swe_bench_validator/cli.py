"""
Command-line interface for the SWE-bench data point validator.
"""

import click
from pathlib import Path
from .utils import console
from rich.progress import Progress, SpinnerColumn, TextColumn
import sys

from .validator import SWEBenchValidator




@click.command()
@click.option(
    "--instance",
    help="Specific SWE-bench instance to validate (e.g., 'astropy__astropy-11693')",
)
@click.option(
    "--data-points-dir",
    default="data_points",
    help="Directory containing JSON data point files (default: data_points/)",
)
@click.option(
    "--timeout",
    default=300,
    type=int,
    help="Timeout for test execution in seconds (default: 300)",
)
@click.option(
    "--max-workers",
    default=1,
    type=int,
    help="Maximum number of parallel workers (default: 1)",
)
@click.option(
    "--cache-level",
    default="base",
    type=click.Choice(["none", "base", "env", "instance"]),
    help="Docker cache level (default: base)",
)
@click.option(
    "--force-rebuild",
    is_flag=True,
    help="Force rebuild of Docker images",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)

@click.option(
    "--output-report",
    help="Save validation report to file",
)
def main(
    instance,
    data_points_dir,
    timeout,
    max_workers,
    cache_level,
    force_rebuild,
    verbose,
    output_report,
):
    """
    Validate SWE-bench data points using official evaluation harness.
    
    This tool validates that data points:
    1. Have correct structure and required fields
    2. Can be applied to their target repositories  
    3. Pass all FAIL_TO_PASS and PASS_TO_PASS tests using official swebench.harness.run_evaluation
    
    Examples:
    
    # Validate all data points
    python -m swe_bench_validator
    
    # Validate specific instance
    python -m swe_bench_validator --instance astropy__astropy-11693
    
    # Custom timeout and settings
    python -m swe_bench_validator --timeout 1800 --cache-level none
    """
    try:
        # Validate data points directory
        data_points_path = Path(data_points_dir)
        if not data_points_path.exists():
            console.print(f"[bold red]Error: Data points directory does not exist: {data_points_path}[/bold red]")
            sys.exit(1)
        
        # Initialize validator
        validator = SWEBenchValidator(
            data_points_dir=data_points_path,
            timeout=timeout,
            max_workers=max_workers,
            cache_level=cache_level,
            verbose=verbose,
            force_rebuild=force_rebuild,
        )
        
        if verbose:
            console.print(f"[bold]Validator initialized with:[/bold]")
            console.print(f"  • Data points directory: {data_points_path}")
            console.print(f"  • Timeout: {timeout}s")
            console.print(f"  • Max workers: {max_workers}")
            console.print(f"  • Cache level: {cache_level}")
            console.print(f"  • Force rebuild: {force_rebuild}")
        
        # Run validation
        if instance:
            # Validate single instance
            instance_file = data_points_path / f"{instance}.json"
            if not instance_file.exists():
                console.print(f"[bold red]Error: Instance file not found: {instance_file}[/bold red]")
                sys.exit(1)
            
            console.print(f"[bold]Validating single instance: {instance}[/bold]")
            result = validator.validate_single_data_point(instance_file)
            
            # Display result
            if result.success:
                console.print(f"[bold green]✅ Validation PASSED for {instance}[/bold green]")
                console.print(f"  • Patch applied: {'✅' if result.patch_applied else '❌'}")
                console.print(f"  • Tests passed: {'✅' if result.tests_passed else '❌'}")
                console.print(f"  • Execution time: {result.execution_time:.2f}s")
            else:
                console.print(f"[bold red]❌ Validation FAILED for {instance}[/bold red]")
                console.print(f"  • Error: {result.error_message}")
                console.print(f"  • Execution time: {result.execution_time:.2f}s")
                sys.exit(1)
            
            results = [result]
            
        else:
            # Validate all data points
            console.print(f"[bold]Validating all data points in {data_points_path}[/bold]")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("Starting validation...", total=None)
                
                results = validator.validate_directory(
                    progress_callback=lambda desc: progress.update(task, description=desc)
                )
        
        # Generate and display report
        if results:
            report = validator.generate_validation_report(results)
            
            # Display report
            console.print("\n" + "="*60)
            console.print(report)
            console.print("="*60)
            
            # Save report to file if requested
            if output_report:
                output_path = Path(output_report)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(report)
                console.print(f"\n[bold green]Report saved to: {output_path}[/bold green]")
            
            # Summary
            total = len(results)
            successful = sum(1 for r in results if r.success)
            failed = total - successful
            
            console.print(f"\n[bold]Summary:[/bold]")
            console.print(f"  • Total validated: {total}")
            console.print(f"  • Successful: {successful}")
            console.print(f"  • Failed: {failed}")
            console.print(f"  • Success rate: {(successful/total)*100:.1f}%")
            
            if failed > 0:
                console.print(f"\n[yellow]Warning: {failed} validations failed[/yellow]")
                sys.exit(1)
            else:
                console.print(f"\n[bold green]✅ All validations passed successfully![/bold green]")
                
        else:
            console.print("[yellow]No data points found for validation[/yellow]")
            
    except Exception as e:
        console.print(f"[bold red]✗ Error: {str(e)}[/bold red]")
        if verbose:
            console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()

