"""
Common utilities for SWE-bench validator.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
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
    
    # Validate simple string fields
    for field in ['instance_id', 'repo', 'base_commit', 'patch']:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"Field '{field}' must be a non-empty string"
    
    # Validate repo format: owner/repo
    repo = data.get('repo', '')
    if '/' not in repo or repo.count('/') != 1 or any(not part.strip() for part in repo.split('/')):
        return "Field 'repo' must be in format 'owner/repo'"
    
    # Validate base_commit looks like a hex string (min 7)
    base_commit = data.get('base_commit', '')
    if len(base_commit) < 7 or any(c not in '0123456789abcdef' for c in base_commit.lower()):
        return "Field 'base_commit' must be a hex commit hash (>=7 chars)"
    
    # Validate lists of tests: allow either list[str] or JSON-encoded string of list[str]
    def ensure_list_of_strings(value: Any, field_name: str) -> Optional[str]:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                return f"Field '{field_name}' must be a list of strings or JSON-encoded list of strings"
            value = parsed
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            return f"Field '{field_name}' must be a list of strings"
        return None
    
    err = ensure_list_of_strings(data.get('FAIL_TO_PASS'), 'FAIL_TO_PASS')
    if err:
        return err
    err = ensure_list_of_strings(data.get('PASS_TO_PASS'), 'PASS_TO_PASS')
    if err:
        return err
    
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
