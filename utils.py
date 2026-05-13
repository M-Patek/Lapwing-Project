"""
Utility functions for Lapwing.
"""
import json
import os
from pathlib import Path
from typing import TypeVar, Optional

T = TypeVar('T')


def safe_json_loads(text: str, default: Optional[T] = None) -> T:
    """
    Safely parse JSON, handling markdown code blocks.

    Args:
        text: Text potentially containing JSON (possibly wrapped in markdown)
        default: Default value if parsing fails

    Returns:
        Parsed JSON object or default
    """
    if default is None:
        default = {}

    try:
        # Handle markdown code blocks
        if "```" in text:
            # Extract content between first { and last }
            json_text = text[text.find('{'): text.rfind('}') + 1]
        else:
            json_text = text.strip()

        return json.loads(json_text)
    except (json.JSONDecodeError, ValueError, IndexError):
        return default


def load_or_initialize_json(file_path: Path | str, default_structure: T) -> T:
    """
    Load JSON from file, or initialize with default if not exists/corrupted.

    Args:
        file_path: Path to JSON file
        default_structure: Default structure if file doesn't exist

    Returns:
        Loaded or initialized data
    """
    file_path = Path(file_path)

    if file_path.exists() and file_path.stat().st_size > 0:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            # Log but don't crash - return default
            print(f"Warning: Failed to load {file_path}: {e}")

    # Initialize with default
    save_json(file_path, default_structure)
    return default_structure


def save_json(file_path: Path | str, data: T) -> None:
    """
    Save data to JSON file, creating directories if needed.

    Args:
        file_path: Path to JSON file
        data: Data to serialize
    """
    file_path = Path(file_path)

    # Ensure directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate string to max length.

    Args:
        text: Input text
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def ensure_dirs():
    """Ensure all required directories exist."""
    dirs = ['json', 'logs', 'prompts']
    for d in dirs:
        Path(d).mkdir(exist_ok=True)
