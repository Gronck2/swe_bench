"""
Common utilities for SWE-bench validator.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from rich.console import Console

# Shared console instance
console = Console()

# Configure logging
def setup_logging(verbose: bool = False) -> logging.Logger:
    """Setup logging configuration."""
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def load_json_safely(file_path: Path) -> Dict[str, Any]:
    """
    Safely load JSON file with proper error handling.
    
    Args:
        file_path: Path to JSON file
        
    Returns:
        Dict containing JSON data
        
    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If JSON is invalid
        IOError: If file can't be read
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Invalid JSON in {file_path}: {e.msg}", e.doc, e.pos)
    except IOError as e:
        raise IOError(f"Cannot read file {file_path}: {e}")

def validate_data_point_structure(data: Dict[str, Any]) -> Optional[str]:
    """
    Validate that data point has required structure.
    
    Args:
        data: Data point dictionary
        
    Returns:
        None if valid, error message if invalid
    """
    required_fields = [
        'instance_id', 'repo', 'base_commit', 'patch',
        'FAIL_TO_PASS', 'PASS_TO_PASS'
    ]
    
    for field in required_fields:
        if field not in data:
            return f"Missing required field: {field}"
        
        if not isinstance(data[field], str) or not data[field].strip():
            return f"Field '{field}' must be a non-empty string"
    
    # Validate patch format
    if not data['patch'].startswith('diff --git'):
        return "Patch must start with 'diff --git'"
    
    return None

def format_execution_time(seconds: float) -> str:
    """Format execution time in human-readable format."""
    if seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"

def truncate_message(message: str, max_length: int = 200) -> str:
    """Truncate message if too long."""
    if len(message) <= max_length:
        return message
    return message[:max_length - 3] + "..."
