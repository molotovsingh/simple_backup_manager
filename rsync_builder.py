"""
Rsync command builder - reuse logic from rsync-command-builder
"""
from typing import Dict, List, Any


def build_rsync_command(source: str, destination: str, args: Dict[str, Any], excludes: str = "") -> List[str]:
    """
    Build rsync command with proper argument handling
    
    Args:
        source: Source path
        destination: Destination path  
        args: Dictionary of rsync options
        excludes: Space-separated exclude patterns
    
    Returns:
        List of command arguments for subprocess
    """
    command = ["rsync"]
    
    # Add standard options
    if args.get("archive"):
        command.append("-a")
    
    if args.get("verbose"):
        command.append("-v")
    
    if args.get("human_readable"):
        command.append("-h")
    
    if args.get("progress"):
        command.append("-P")
    
    if args.get("compress"):
        command.append("--compress")
    
    if args.get("delete"):
        command.append("--delete")
    
    if args.get("dry_run"):
        command.append("--dry-run")
    
    if args.get("remove_source_files"):
        command.append("--remove-source-files")
    
    # Advanced options
    if args.get("checksum"):
        command.append("--checksum")
    
    if args.get("stats"):
        command.append("--stats")
    
    if args.get("itemize_changes"):
        command.append("--itemize-changes")
    
    if args.get("inplace"):
        command.append("--inplace")
    
    if args.get("sparse"):
        command.append("--sparse")
    
    if args.get("whole_file"):
        command.append("--whole-file")
    
    if args.get("update"):
        command.append("--update")
    
    if args.get("ignore_existing"):
        command.append("--ignore-existing")
    
    # Bandwidth limit
    if args.get("bwlimit"):
        bwlimit = args.get("bwlimit")
        if bwlimit and str(bwlimit).strip():
            command.append(f"--bwlimit={bwlimit}")
    
    # Partial directory
    if args.get("partial_dir"):
        partial_dir = args.get("partial_dir")
        if partial_dir and str(partial_dir).strip():
            command.append(f"--partial-dir={partial_dir}")
    
    # Add exclude patterns
    if excludes and excludes.strip():
        exclude_list = excludes.strip().split()
        for pattern in exclude_list:
            command.extend(["--exclude", pattern])
    
    # Add source and destination
    command.extend([source.strip() or "[SOURCE]", destination.strip() or "[DESTINATION]"])
    
    return command


def build_rsync_command_string(source: str, destination: str, args: Dict[str, Any], excludes: str = "") -> str:
    """
    Build rsync command as string (for display)
    """
    command_list = build_rsync_command(source, destination, args, excludes)
    return " ".join(command_list)


def get_default_rsync_args() -> Dict[str, Any]:
    """Get default rsync arguments"""
    return {
        "archive": True,
        "verbose": True,
        "human_readable": True,
        "progress": True,
        "compress": False,
        "delete": False,
        "dry_run": False,
        "remove_source_files": False,
        "checksum": False,
        "stats": True,
        "itemize_changes": False,
        "inplace": False,
        "sparse": False,
        "whole_file": False,
        "update": False,
        "ignore_existing": False,
        "bwlimit": "",
        "partial_dir": ""
    }


def validate_rsync_args(args: Dict[str, Any]) -> List[str]:
    """Validate rsync arguments and return error messages"""
    errors = []
    
    # Check for dangerous combinations
    if args.get("delete") and not args.get("dry_run"):
        errors.append("Warning: --delete will permanently remove files from destination")
    
    if args.get("remove_source_files"):
        if not args.get("dry_run"):
            errors.append("⚠️ DANGER: --remove-source-files will permanently delete source files after transfer")
        if not args.get("checksum") and args.get("remove_source_files"):
            errors.append("⚠️ WARNING: Consider using --checksum with --remove-source-files for data safety")
    
    # Check source/destination
    source = args.get("source")
    if not source or (isinstance(source, str) and not source.strip()):
        errors.append("Source path is required")
    
    destination = args.get("destination")
    if not destination or (isinstance(destination, str) and not destination.strip()):
        errors.append("Destination path is required")
    
    return errors
