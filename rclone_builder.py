"""
Rclone command builder
"""
from typing import Dict, List, Any


def build_rclone_command(operation: str, source: str, destination: str,
                        args: Dict[str, Any], excludes: str = "") -> List[str]:
    """
    Build rclone command with proper argument handling

    Args:
        operation: Rclone operation (sync, copy, move, delete, check)
        source: Source path (local or remote)
        destination: Destination path (local or remote)
        args: Dictionary of rclone options
        excludes: Space-separated exclude patterns

    Returns:
        List of command arguments for subprocess
    """
    command = ["rclone", operation]

    # Add common options
    if args.get("verbose"):
        command.append("-v")

    if args.get("progress"):
        command.append("--progress")

    if args.get("dry_run"):
        command.append("--dry-run")

    # Add operation-specific options
    if operation == "sync":
        if args.get("delete"):
            command.append("--delete-during")
        if args.get("create_empty_src_dirs"):
            command.append("--create-empty-src-dirs")

    if operation == "move":
        if args.get("delete_empty_src_dirs"):
            command.append("--delete-empty-src-dirs")

    if operation in ["copy", "sync", "move"]:
        if args.get("checksum"):
            command.append("--checksum")
        if args.get("ignore_times"):
            command.append("--ignore-times")

    # Add performance options
    transfers = args.get("transfers")
    if transfers and str(transfers).strip():
        command.extend(["--transfers", str(transfers)])

    checkers = args.get("checkers")
    if checkers and str(checkers).strip():
        command.extend(["--checkers", str(checkers)])

    # Add bandwidth limiting
    bwlimit = args.get("bwlimit")
    if bwlimit and str(bwlimit).strip():
        command.extend(["--bwlimit", str(bwlimit)])

    # Advanced transfer options
    if args.get("update"):
        command.append("--update")

    if args.get("ignore_existing"):
        command.append("--ignore-existing")

    if args.get("ignore_size"):
        command.append("--ignore-size")

    if args.get("size_only"):
        command.append("--size-only")

    if args.get("immutable"):
        command.append("--immutable")

    if args.get("use_server_modtime"):
        command.append("--use-server-modtime")

    # Retry and timeout options
    retries = args.get("retries")
    if retries and str(retries).strip():
        command.extend(["--retries", str(retries)])

    low_level_retries = args.get("low_level_retries")
    if low_level_retries and str(low_level_retries).strip():
        command.extend(["--low-level-retries", str(low_level_retries)])

    timeout = args.get("timeout")
    if timeout and str(timeout).strip():
        command.extend(["--timeout", str(timeout)])

    contimeout = args.get("contimeout")
    if contimeout and str(contimeout).strip():
        command.extend(["--contimeout", str(contimeout)])

    # Buffer and chunk sizes
    buffer_size = args.get("buffer_size")
    if buffer_size and str(buffer_size).strip():
        command.extend(["--buffer-size", str(buffer_size)])

    drive_chunk_size = args.get("drive_chunk_size")
    if drive_chunk_size and str(drive_chunk_size).strip():
        command.extend(["--drive-chunk-size", str(drive_chunk_size)])

    # Logging and stats
    if args.get("stats"):
        stats_interval = args.get("stats_interval", "1m")
        command.extend(["--stats", str(stats_interval)])

    if args.get("stats_one_line"):
        command.append("--stats-one-line")

    if args.get("no_traverse"):
        command.append("--no-traverse")

    if args.get("fast_list"):
        command.append("--fast-list")

    # Advanced options
    if args.get("track_renames"):
        command.append("--track-renames")

    if args.get("no_update_modtime"):
        command.append("--no-update-modtime")

    if args.get("use_mmap"):
        command.append("--use-mmap")

    if args.get("inplace"):
        command.append("--inplace")

    max_delete = args.get("max_delete")
    if max_delete and str(max_delete).strip():
        command.extend(["--max-delete", str(max_delete)])

    min_size = args.get("min_size")
    if min_size and str(min_size).strip():
        command.extend(["--min-size", str(min_size)])

    max_size = args.get("max_size")
    if max_size and str(max_size).strip():
        command.extend(["--max-size", str(max_size)])

    max_age = args.get("max_age")
    if max_age and str(max_age).strip():
        command.extend(["--max-age", str(max_age)])

    min_age = args.get("min_age")
    if min_age and str(min_age).strip():
        command.extend(["--min-age", str(min_age)])

    # Add exclude patterns
    if excludes and excludes.strip():
        exclude_list = excludes.strip().split()
        for pattern in exclude_list:
            command.extend(["--exclude", pattern])

    # Add include patterns if specified
    includes = args.get("includes")
    if includes and includes.strip():
        include_list = includes.strip().split()
        for pattern in include_list:
            command.extend(["--include", pattern])

    # Add source and destination
    source_str = source.strip() if source else "[SOURCE]"
    dest_str = destination.strip() if destination else "[DESTINATION]"
    command.extend([source_str, dest_str])

    return command


def build_rclone_command_string(operation: str, source: str, destination: str,
                               args: Dict[str, Any], excludes: str = "") -> str:
    """
    Build rclone command as string (for display)
    """
    command_list = build_rclone_command(operation, source, destination, args, excludes)
    return " ".join(command_list)


def get_default_rclone_args() -> Dict[str, Any]:
    """Get default rclone arguments"""
    return {
        # Basic options
        "verbose": True,
        "progress": True,
        "dry_run": False,
        "delete": False,
        "checksum": False,
        "ignore_times": False,
        
        # Performance options
        "transfers": "4",
        "checkers": "8",
        "bwlimit": "",
        
        # Sync options
        "create_empty_src_dirs": False,
        "delete_empty_src_dirs": False,
        
        # Advanced transfer options
        "update": False,
        "ignore_existing": False,
        "ignore_size": False,
        "size_only": False,
        "immutable": False,
        "use_server_modtime": False,
        
        # Retry and timeout
        "retries": "3",
        "low_level_retries": "10",
        "timeout": "",
        "contimeout": "",
        
        # Buffer and chunks
        "buffer_size": "",
        "drive_chunk_size": "",
        
        # Stats and logging
        "stats": True,
        "stats_interval": "1m",
        "stats_one_line": False,
        "no_traverse": False,
        "fast_list": False,
        
        # Advanced
        "track_renames": False,
        "no_update_modtime": False,
        "use_mmap": False,
        "inplace": False,
        "max_delete": "",
        "min_size": "",
        "max_size": "",
        "max_age": "",
        "min_age": "",
    }


def validate_rclone_args(args: Dict[str, Any]) -> List[str]:
    """Validate rclone arguments and return error messages"""
    errors = []

    # Check for dangerous combinations
    if args.get("delete"):
        errors.append("⚠️ WARNING: Sync with --delete will remove files from destination that don't exist in source")

    # Check source/destination
    source = args.get("source")
    if source is None or not str(source).strip():
        errors.append("Source path is required")

    destination = args.get("destination")
    if destination is None or not str(destination).strip():
        errors.append("Destination path is required")

    return errors


def get_rclone_operations() -> List[str]:
    """Get list of available rclone operations"""
    return [
        "sync",      # Make destination match source
        "copy",      # Copy files from source to destination
        "move",      # Move files from source to destination
        "delete",    # Delete files from destination
        "check",     # Check files in source and destination
    ]
