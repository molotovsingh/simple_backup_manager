"""
Validation utilities for job and rclone operation inputs
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple
from storage_errors import StorageValidationError


# Dangerous paths that should never be allowed as destinations
DANGEROUS_PATHS = {
    "/", "/bin", "/sbin", "/usr", "/usr/bin", "/usr/sbin",
    "/etc", "/boot", "/sys", "/proc", "/dev",
    "/System", "/Library", "/Applications",  # macOS
    "C:\\", "C:\\Windows", "C:\\Program Files",  # Windows
}

# Allowed operation types for rclone
ALLOWED_RCLONE_OPERATIONS = {
    "copy", "sync", "move", "check", "delete", "mount", "rcat", "copyto", "moveto"
}


def sanitize_path(path: str) -> str:
    """
    Sanitize path to prevent path traversal attacks

    Args:
        path: Path string to sanitize

    Returns:
        Sanitized path string

    Raises:
        StorageValidationError: If path contains dangerous patterns
    """
    if not path or not isinstance(path, str):
        raise StorageValidationError("Path must be a non-empty string")

    # Remove null bytes
    if "\x00" in path:
        raise StorageValidationError("Path contains null bytes")

    # Check for path traversal attempts
    normalized = os.path.normpath(path)

    # Check for .. in the normalized path (path traversal)
    if ".." in Path(normalized).parts:
        raise StorageValidationError(f"Path traversal detected: {path}")

    # Check for dangerous absolute paths
    for dangerous in DANGEROUS_PATHS:
        if normalized == dangerous or normalized.startswith(dangerous + os.sep):
            raise StorageValidationError(f"Access to system directory not allowed: {path}")

    return normalized


def validate_path_exists(path: str, path_type: str = "source") -> bool:
    """
    Validate that a path exists

    Args:
        path: Path to validate
        path_type: Type of path ("source" or "destination") for error messages

    Returns:
        True if path exists

    Raises:
        StorageValidationError: If path doesn't exist or is not accessible
    """
    try:
        sanitized_path = sanitize_path(path)
        path_obj = Path(sanitized_path)

        if not path_obj.exists():
            raise StorageValidationError(f"{path_type.capitalize()} path does not exist: {path}")

        return True

    except (OSError, PermissionError) as e:
        raise StorageValidationError(f"Cannot access {path_type} path {path}: {e}") from e


def validate_path_readable(path: str) -> bool:
    """
    Validate that a path is readable

    Args:
        path: Path to validate

    Returns:
        True if path is readable

    Raises:
        StorageValidationError: If path is not readable
    """
    try:
        sanitized_path = sanitize_path(path)
        path_obj = Path(sanitized_path)

        if not os.access(path_obj, os.R_OK):
            raise StorageValidationError(f"Path is not readable: {path}")

        return True

    except (OSError, PermissionError) as e:
        raise StorageValidationError(f"Cannot check read permissions for {path}: {e}") from e


def validate_path_writable(path: str, create_if_missing: bool = False) -> bool:
    """
    Validate that a path is writable

    Args:
        path: Path to validate
        create_if_missing: Create parent directories if they don't exist

    Returns:
        True if path is writable

    Raises:
        StorageValidationError: If path is not writable
    """
    try:
        sanitized_path = sanitize_path(path)
        path_obj = Path(sanitized_path)

        # If path exists, check if it's writable
        if path_obj.exists():
            if not os.access(path_obj, os.W_OK):
                raise StorageValidationError(f"Path is not writable: {path}")
        else:
            # Check if parent directory is writable
            parent = path_obj.parent
            if not parent.exists():
                if create_if_missing:
                    try:
                        parent.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        raise StorageValidationError(f"Cannot create parent directory for {path}: {e}") from e
                else:
                    raise StorageValidationError(f"Parent directory does not exist: {parent}")

            if not os.access(parent, os.W_OK):
                raise StorageValidationError(f"Parent directory is not writable: {parent}")

        return True

    except (OSError, PermissionError) as e:
        raise StorageValidationError(f"Cannot check write permissions for {path}: {e}") from e


def validate_paths_not_circular(source: str, destination: str) -> bool:
    """
    Validate that source and destination are not the same

    Args:
        source: Source path
        destination: Destination path

    Returns:
        True if paths are different

    Raises:
        StorageValidationError: If paths are the same
    """
    try:
        source_sanitized = sanitize_path(source)
        dest_sanitized = sanitize_path(destination)

        # Resolve to absolute paths for comparison
        source_abs = str(Path(source_sanitized).resolve())
        dest_abs = str(Path(dest_sanitized).resolve())

        if source_abs == dest_abs:
            raise StorageValidationError(f"Source and destination cannot be the same: {source}")

        # Check if destination is inside source (problematic for some operations)
        if dest_abs.startswith(source_abs + os.sep):
            raise StorageValidationError(
                f"Destination cannot be inside source: {destination} is inside {source}"
            )

        return True

    except StorageValidationError:
        raise
    except Exception as e:
        # If we can't resolve paths, allow it (might be remote paths)
        print(f"Warning: Could not validate circular paths: {e}")
        return True


def validate_job_data(job_data: Dict[str, Any], validate_paths: bool = True) -> Tuple[bool, List[str]]:
    """
    Validate job data before creation

    Args:
        job_data: Job data dictionary
        validate_paths: Whether to validate filesystem paths (set False for remotes)

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Required fields
    if not job_data.get("name"):
        errors.append("Job name is required")

    if not job_data.get("source"):
        errors.append("Source path is required")

    if not job_data.get("destination"):
        errors.append("Destination path is required")

    # Validate name length
    name = job_data.get("name", "")
    if len(name) > 200:
        errors.append(f"Job name too long (max 200 characters): {len(name)}")

    # Validate max_retries
    max_retries = job_data.get("max_retries", 5)
    if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 100:
        errors.append(f"max_retries must be between 0 and 100: {max_retries}")

    # Path validation
    if validate_paths and not errors:
        source = job_data.get("source", "")
        destination = job_data.get("destination", "")

        try:
            # Sanitize paths
            sanitize_path(source)
            sanitize_path(destination)

            # Check source exists and is readable
            validate_path_exists(source, "source")
            validate_path_readable(source)

            # Check destination is writable (create parent if needed)
            validate_path_writable(destination, create_if_missing=False)

            # Check for circular paths
            validate_paths_not_circular(source, destination)

        except StorageValidationError as e:
            errors.append(str(e))

    return (len(errors) == 0, errors)


def validate_operation_data(operation_data: Dict[str, Any], validate_paths: bool = False) -> Tuple[bool, List[str]]:
    """
    Validate rclone operation data before creation

    Args:
        operation_data: Operation data dictionary
        validate_paths: Whether to validate paths (usually False for remotes)

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Required fields
    if not operation_data.get("operation_type"):
        errors.append("Operation type is required")

    if not operation_data.get("source"):
        errors.append("Source is required")

    if not operation_data.get("destination"):
        errors.append("Destination is required")

    # Validate operation type
    operation_type = operation_data.get("operation_type", "")
    if operation_type and operation_type not in ALLOWED_RCLONE_OPERATIONS:
        errors.append(
            f"Invalid operation type: {operation_type}. "
            f"Allowed: {', '.join(sorted(ALLOWED_RCLONE_OPERATIONS))}"
        )

    # Validate max_retries
    max_retries = operation_data.get("max_retries", 3)
    if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 100:
        errors.append(f"max_retries must be between 0 and 100: {max_retries}")

    # Optional path validation (for local paths)
    if validate_paths and not errors:
        source = operation_data.get("source", "")
        destination = operation_data.get("destination", "")

        # Only validate if they look like local paths (not remote://path)
        if ":" not in source:
            try:
                sanitize_path(source)
                validate_path_exists(source, "source")
            except StorageValidationError as e:
                errors.append(str(e))

        if ":" not in destination:
            try:
                sanitize_path(destination)
            except StorageValidationError as e:
                errors.append(str(e))

    return (len(errors) == 0, errors)


def validate_remote_data(remote_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate remote configuration data

    Args:
        remote_data: Remote data dictionary

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Required fields
    if not remote_data.get("name"):
        errors.append("Remote name is required")

    if not remote_data.get("type"):
        errors.append("Remote type is required")

    # Validate name format (alphanumeric, underscores, hyphens only)
    name = remote_data.get("name", "")
    if name and not re.match(r'^[a-zA-Z0-9_-]+$', name):
        errors.append(f"Invalid remote name format: {name}. Use only letters, numbers, underscores, and hyphens.")

    if len(name) > 50:
        errors.append(f"Remote name too long (max 50 characters): {len(name)}")

    return (len(errors) == 0, errors)
