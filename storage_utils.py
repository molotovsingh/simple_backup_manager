"""
Utility functions for safe storage operations
"""
import json
import os
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from storage_errors import StorageIOError, StorageCorruptionError


def generate_unique_id(prefix: str = "item") -> str:
    """
    Generate a unique ID using UUID4

    Args:
        prefix: Prefix for the ID (e.g., "job", "rclone")

    Returns:
        Unique ID string in format: prefix_uuid

    Example:
        generate_unique_id("job") -> "job_a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    """
    unique_uuid = str(uuid.uuid4())
    return f"{prefix}_{unique_uuid}"


def atomic_write(filepath: Path, data: Dict[str, Any], indent: int = 2):
    """
    Write JSON data to file atomically

    Uses temp file + atomic rename to prevent corruption if process crashes
    during write.

    Args:
        filepath: Path to the target file
        data: Dictionary to write as JSON
        indent: JSON indentation level

    Raises:
        StorageIOError: If write fails
    """
    filepath = Path(filepath)
    temp_file = filepath.with_suffix('.tmp')

    try:
        # Write to temp file first
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=indent, default=str)

        # Atomic rename (works on Unix and Windows)
        # On Unix: os.replace is atomic
        # On Windows: os.replace is atomic if target doesn't exist or both on same filesystem
        os.replace(temp_file, filepath)

    except Exception as e:
        # Clean up temp file if it exists
        if temp_file.exists():
            temp_file.unlink()
        raise StorageIOError(f"Failed to write {filepath}: {e}") from e


def safe_json_load(filepath: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely load JSON file with fallback to default

    Args:
        filepath: Path to JSON file
        default: Default value if file doesn't exist or is corrupted

    Returns:
        Loaded data or default

    Raises:
        StorageCorruptionError: If file exists but is corrupted and backup recovery fails
    """
    filepath = Path(filepath)

    # File doesn't exist - return default
    if not filepath.exists():
        return default.copy()

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Validate it's a dict
        if not isinstance(data, dict):
            raise StorageCorruptionError(f"{filepath} contains non-dict data: {type(data)}")

        return data

    except json.JSONDecodeError as e:
        # File is corrupted - try to recover from backup
        backup_path = find_latest_backup(filepath)
        if backup_path:
            print(f"Warning: {filepath} corrupted, recovering from backup {backup_path}")
            try:
                with open(backup_path, 'r') as f:
                    return json.load(f)
            except Exception:
                pass  # Backup also corrupted, fall through to error

        raise StorageCorruptionError(
            f"Failed to load {filepath}: {e}. No valid backup found."
        ) from e

    except Exception as e:
        raise StorageIOError(f"Failed to read {filepath}: {e}") from e


def backup_file(filepath: Path, keep_count: int = 5) -> Optional[Path]:
    """
    Create a timestamped backup of a file

    Args:
        filepath: Path to file to backup
        keep_count: Number of backups to keep (oldest deleted)

    Returns:
        Path to backup file, or None if source doesn't exist
    """
    filepath = Path(filepath)

    if not filepath.exists():
        return None

    # Create backup with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = filepath.with_suffix(f'.backup.{timestamp}{filepath.suffix}')

    try:
        shutil.copy2(filepath, backup_path)

        # Clean up old backups
        cleanup_old_backups(filepath, keep_count)

        return backup_path

    except Exception as e:
        print(f"Warning: Failed to create backup of {filepath}: {e}")
        return None


def cleanup_old_backups(filepath: Path, keep_count: int = 5):
    """
    Remove old backup files, keeping only the most recent ones

    Args:
        filepath: Original file path
        keep_count: Number of backups to keep
    """
    filepath = Path(filepath)
    backup_pattern = f"{filepath.stem}.backup.*{filepath.suffix}"
    backup_dir = filepath.parent

    # Find all backups
    backups = sorted(
        backup_dir.glob(backup_pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True  # Newest first
    )

    # Delete old backups beyond keep_count
    for old_backup in backups[keep_count:]:
        try:
            old_backup.unlink()
        except Exception as e:
            print(f"Warning: Failed to delete old backup {old_backup}: {e}")


def find_latest_backup(filepath: Path) -> Optional[Path]:
    """
    Find the most recent backup of a file

    Args:
        filepath: Original file path

    Returns:
        Path to most recent backup, or None if no backups exist
    """
    filepath = Path(filepath)
    backup_pattern = f"{filepath.stem}.backup.*{filepath.suffix}"
    backup_dir = filepath.parent

    backups = sorted(
        backup_dir.glob(backup_pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True  # Newest first
    )

    return backups[0] if backups else None


def recover_from_backup(filepath: Path) -> bool:
    """
    Recover a file from its most recent backup

    Args:
        filepath: Path to corrupted file

    Returns:
        True if recovery successful, False otherwise
    """
    filepath = Path(filepath)
    backup_path = find_latest_backup(filepath)

    if not backup_path:
        print(f"No backup found for {filepath}")
        return False

    try:
        # Backup the corrupted file before overwriting
        corrupted_path = filepath.with_suffix('.corrupted')
        if filepath.exists():
            shutil.move(filepath, corrupted_path)

        # Restore from backup
        shutil.copy2(backup_path, filepath)
        print(f"Recovered {filepath} from backup {backup_path}")
        return True

    except Exception as e:
        print(f"Failed to recover {filepath} from backup: {e}")
        return False
