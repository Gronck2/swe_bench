"""
SWE-bench Data Point Validator

A command-line tool for validating SWE-bench data points using the official
SWE-bench evaluation harness to ensure data quality and correctness.
"""

__version__ = "0.1.0"

from .validator import SWEBenchValidator
from .cli import main

__all__ = ["SWEBenchValidator", "main"]

