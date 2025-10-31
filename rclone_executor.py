"""
Rclone operation executor with progress tracking
"""
import subprocess
import threading
import time
import json
import signal
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from rclone_storage import RcloneStorage
from rclone_builder import build_rclone_command


class RcloneExecutor:
    """Handles rclone operation execution with retry logic"""

    def __init__(self, storage: RcloneStorage, log_dir: str = "logs"):
        self.storage = storage
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.running_operations: Dict[str, threading.Thread] = {}
        self.operation_processes: Dict[str, subprocess.Popen] = {}
        self.progress_callbacks: Dict[str, Callable] = {}
        self.operation_locks: Dict[str, threading.Lock] = {}
        self.stop_flags: Dict[str, threading.Event] = {}
        self.paused_operations: Dict[str, bool] = {}
        self._state_lock = threading.Lock()  # Global state lock

    def _get_log_file(self, operation_id: str) -> Path:
        """Get log file path for operation (internal method)"""
        return self.log_dir / f"{operation_id}.log"

    def get_log_file(self, operation_id: str) -> Path:
        """Get log file path for operation (public method)"""
        return self._get_log_file(operation_id)

    def _log_message(self, operation_id: str, message: str):
        """Log message to operation log file"""
        log_file = self._get_log_file(operation_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, 'a') as f:
            f.write(f"[{timestamp}] {message}\n")

    def _update_progress(self, operation_id: str, progress_data: Dict[str, Any]):
        """Update operation progress and notify callbacks"""
        # Update storage
        self.storage.update_operation(operation_id, {
            "progress": progress_data,
            "status": progress_data.get("status", "running")
        })

        # Notify progress callback if exists
        if operation_id in self.progress_callbacks:
            self.progress_callbacks[operation_id](operation_id, progress_data)

    def _execute_rclone_operation(self, operation_id: str, operation_data: Dict[str, Any]):
        """Execute rclone operation with monitoring"""
        process = None
        try:
            self._log_message(operation_id, f"Starting rclone operation: {operation_data.get('name', 'Unnamed')}")

            # Build command
            operation_type = operation_data.get("operation_type", "copy")
            source = operation_data.get("source", "")
            destination = operation_data.get("destination", "")
            rclone_args = operation_data.get("rclone_args", {})
            excludes = operation_data.get("excludes", "")

            command = build_rclone_command(operation_type, source, destination, rclone_args, excludes)

            self._log_message(operation_id, f"Command: {' '.join(command)}")

            # Start process
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                preexec_fn=os.setsid if os.name != 'nt' else None  # Create process group on Unix
            )

            with self._state_lock:
                self.operation_processes[operation_id] = process

            # Update status to running
            self._update_progress(operation_id, {
                "status": "running",
                "started_at": datetime.now().isoformat(),
                "percent": 0,
                "files_transferred": 0,
                "total_files": 0,
                "bytes_transferred": 0,
                "total_bytes": 0
            })

            # Monitor output
            output_lines = []
            for line in iter(process.stdout.readline, ''):
                # Check if stop was requested
                if operation_id in self.stop_flags and self.stop_flags[operation_id].is_set():
                    self._log_message(operation_id, "Stop requested, terminating...")
                    break

                if line:
                    output_lines.append(line.strip())
                    self._log_message(operation_id, line.strip())

                    # Parse progress from rclone output
                    progress = self._parse_rclone_progress(line.strip())
                    if progress:
                        self._update_progress(operation_id, progress)

            # Check if we broke out due to stop
            if operation_id in self.stop_flags and self.stop_flags[operation_id].is_set():
                # Process was stopped by user
                self._log_message(operation_id, "Operation stopped by user")
                self._update_progress(operation_id, {
                    "status": "stopped",
                    "stopped_at": datetime.now().isoformat()
                })
                return

            # Wait for process to complete
            returncode = process.wait()

            # Check if process died unexpectedly
            if returncode is None:
                error_msg = "Process died unexpectedly (returncode is None)"
                self._log_message(operation_id, error_msg)
                self._update_progress(operation_id, {
                    "status": "failed",
                    "failed_at": datetime.now().isoformat(),
                    "error_message": error_msg
                })
                return

            # Handle completion
            if returncode == 0:
                self._log_message(operation_id, "Operation completed successfully")
                self._update_progress(operation_id, {
                    "status": "completed",
                    "completed_at": datetime.now().isoformat(),
                    "percent": 100
                })
            else:
                error_msg = f"Operation failed with return code {returncode}"
                self._log_message(operation_id, error_msg)
                self._update_progress(operation_id, {
                    "status": "failed",
                    "failed_at": datetime.now().isoformat(),
                    "error_message": error_msg,
                    "return_code": returncode
                })

                # Check if we should retry
                self._handle_operation_failure(operation_id, operation_data)

        except Exception as e:
            error_msg = f"Operation execution error: {str(e)}"
            self._log_message(operation_id, error_msg)
            self._update_progress(operation_id, {
                "status": "failed",
                "failed_at": datetime.now().isoformat(),
                "error_message": error_msg
            })

        finally:
            # Clean up process resources
            if process:
                try:
                    if process.poll() is None:
                        # Process still running, kill it
                        if os.name != 'nt':
                            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                        else:
                            process.terminate()
                        process.wait(timeout=5)
                except Exception as e:
                    self._log_message(operation_id, f"Error during process cleanup: {e}")

            # Clean up tracking dictionaries
            with self._state_lock:
                if operation_id in self.operation_processes:
                    del self.operation_processes[operation_id]
                if operation_id in self.running_operations:
                    del self.running_operations[operation_id]
                if operation_id in self.stop_flags:
                    del self.stop_flags[operation_id]
                if operation_id in self.operation_locks:
                    del self.operation_locks[operation_id]
                if operation_id in self.paused_operations:
                    del self.paused_operations[operation_id]

    def _parse_rclone_progress(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse progress information from rclone output"""
        progress = {}

        # Look for transfer progress patterns
        # Example: "Transferred:   10.5M / 100.0M, 10%, 1.2M/s, ETA 1m30s"
        if "Transferred:" in line:
            try:
                parts = line.split(',')
                if len(parts) > 0:
                    # Extract bytes transferred
                    transferred_part = parts[0].split('/')
                    if len(transferred_part) >= 2:
                        transferred = transferred_part[0].replace("Transferred:", "").strip()
                        total = transferred_part[1].strip()
                        progress["transferred_display"] = f"{transferred} / {total}"

                # Extract percentage
                if len(parts) > 1:
                    percent_part = parts[1].strip()
                    if "%" in percent_part:
                        try:
                            percent = int(percent_part.split("%")[0])
                            progress["percent"] = percent
                            progress["status"] = "running"
                        except ValueError:
                            pass

                # Extract speed and ETA
                if len(parts) > 2:
                    speed = parts[2].strip()
                    progress["speed"] = speed

                if len(parts) > 3:
                    eta = parts[3].replace("ETA", "").strip()
                    progress["eta"] = eta

            except (ValueError, IndexError):
                pass

        # Look for file count progress
        if "files..." in line.lower() or "Checking" in line:
            progress["status"] = "scanning"

        return progress if progress else None

    def _handle_operation_failure(self, operation_id: str, operation_data: Dict[str, Any]):
        """Handle operation failure and determine if retry is needed"""
        retry_count = operation_data.get("retry_count", 0)
        max_retries = operation_data.get("max_retries", 3)

        if retry_count < max_retries:
            # Increment retry count and schedule retry
            self.storage.increment_retry_count(operation_id)

            # Calculate backoff delay (exponential: 1s, 2s, 4s, max 30s)
            backoff = min(2 ** retry_count, 30)

            self._log_message(operation_id, f"Scheduling retry in {backoff}s (attempt {retry_count + 1}/{max_retries})")

            # Schedule retry
            def retry_operation():
                time.sleep(backoff)
                if operation_id not in self.running_operations:
                    # Refetch operation data to pick up any user edits made during execution
                    fresh_operation_data = self.storage.get_operation(operation_id)
                    if fresh_operation_data:
                        self._update_progress(operation_id, {
                            "status": "running",
                            "retry_attempt": retry_count + 1
                        })
                        self._execute_rclone_operation(operation_id, fresh_operation_data)
                    else:
                        self._log_message(operation_id, "Operation not found for retry, skipping")

            retry_thread = threading.Thread(target=retry_operation, daemon=True)
            retry_thread.start()
        else:
            self._log_message(operation_id, f"Max retries ({max_retries}) exceeded, giving up")

    def start_operation(self, operation_id: str, progress_callback: Optional[Callable] = None) -> bool:
        """Start an rclone operation"""
        operation_data = self.storage.get_operation(operation_id)
        if not operation_data:
            print(f"Operation {operation_id} not found")
            return False

        with self._state_lock:
            if operation_id in self.running_operations:
                print(f"Operation {operation_id} is already running")
                return False

            # Initialize synchronization primitives
            self.operation_locks[operation_id] = threading.Lock()
            self.stop_flags[operation_id] = threading.Event()
            self.paused_operations[operation_id] = False

        # Register progress callback
        if progress_callback:
            self.progress_callbacks[operation_id] = progress_callback

        # Reset retry count for manual restart
        self.storage.update_operation(operation_id, {"retry_count": 0})

        # Start operation in thread
        thread = threading.Thread(target=self._execute_rclone_operation, args=(operation_id, operation_data))
        thread.daemon = True
        thread.start()

        with self._state_lock:
            self.running_operations[operation_id] = thread

        return True

    def stop_operation(self, operation_id: str) -> bool:
        """Stop a running operation"""
        with self._state_lock:
            # Check if operation is tracked
            if operation_id not in self.running_operations and operation_id not in self.operation_processes:
                print(f"Operation {operation_id} is not running")
                return False

            # Set stop flag to signal the thread
            if operation_id in self.stop_flags:
                self.stop_flags[operation_id].set()

            # Get references before releasing lock
            process = self.operation_processes.get(operation_id)
            thread = self.running_operations.get(operation_id)

        try:
            # Terminate the process if it exists
            if process and process.poll() is None:
                self._log_message(operation_id, "Stopping operation...")

                try:
                    # Try graceful termination first
                    if os.name != 'nt':
                        # Unix: send SIGTERM to process group
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    else:
                        # Windows: use terminate
                        process.terminate()

                    # Wait up to 10 seconds for graceful shutdown
                    try:
                        process.wait(timeout=10)
                        self._log_message(operation_id, "Operation stopped gracefully")
                    except subprocess.TimeoutExpired:
                        # Force kill if still running
                        self._log_message(operation_id, "Timeout, force killing process...")
                        if os.name != 'nt':
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                        else:
                            process.kill()
                        process.wait()
                        self._log_message(operation_id, "Operation force killed")

                except (ProcessLookupError, OSError) as e:
                    self._log_message(operation_id, f"Process already terminated: {e}")

            # Wait for thread to finish (with timeout)
            if thread and thread.is_alive():
                thread.join(timeout=5)
                if thread.is_alive():
                    self._log_message(operation_id, "Warning: Thread did not terminate cleanly")

            # Update status
            self._update_progress(operation_id, {
                "status": "stopped",
                "stopped_at": datetime.now().isoformat()
            })

            self._log_message(operation_id, "Operation stopped by user")
            return True

        except Exception as e:
            error_msg = f"Error stopping operation {operation_id}: {e}"
            print(error_msg)
            self._log_message(operation_id, error_msg)
            return False

    def pause_operation(self, operation_id: str) -> bool:
        """Pause a running operation"""
        with self._state_lock:
            if operation_id not in self.operation_processes:
                print(f"Operation {operation_id} is not running")
                return False

            if self.paused_operations.get(operation_id, False):
                print(f"Operation {operation_id} is already paused")
                return False

            process = self.operation_processes.get(operation_id)

        try:
            if process and process.poll() is None:
                if os.name != 'nt':
                    # Unix: send SIGSTOP to process group
                    os.killpg(os.getpgid(process.pid), signal.SIGSTOP)
                    with self._state_lock:
                        self.paused_operations[operation_id] = True

                    self._log_message(operation_id, "Operation paused")
                    self._update_progress(operation_id, {
                        "status": "paused",
                        "paused_at": datetime.now().isoformat()
                    })
                    return True
                else:
                    # Windows doesn't support SIGSTOP, would need different approach
                    print("Pause not supported on Windows")
                    return False
            return False

        except Exception as e:
            error_msg = f"Error pausing operation {operation_id}: {e}"
            print(error_msg)
            self._log_message(operation_id, error_msg)
            return False

    def resume_operation(self, operation_id: str) -> bool:
        """Resume a paused operation"""
        with self._state_lock:
            if operation_id not in self.operation_processes:
                print(f"Operation {operation_id} is not running")
                return False

            if not self.paused_operations.get(operation_id, False):
                print(f"Operation {operation_id} is not paused")
                return False

            process = self.operation_processes.get(operation_id)

        try:
            if process and process.poll() is None:
                if os.name != 'nt':
                    # Unix: send SIGCONT to process group
                    os.killpg(os.getpgid(process.pid), signal.SIGCONT)
                    with self._state_lock:
                        self.paused_operations[operation_id] = False

                    self._log_message(operation_id, "Operation resumed")
                    self._update_progress(operation_id, {
                        "status": "running",
                        "resumed_at": datetime.now().isoformat()
                    })
                    return True
                else:
                    # Windows doesn't support SIGCONT
                    print("Resume not supported on Windows")
                    return False
            return False

        except Exception as e:
            error_msg = f"Error resuming operation {operation_id}: {e}"
            print(error_msg)
            self._log_message(operation_id, error_msg)
            return False

    def cleanup_zombie_operations(self) -> int:
        """Clean up operations in problematic states (running, pending, failed preview, initializing)"""
        cleaned = 0
        operations = self.storage.get_all_operations()

        for op in operations:
            op_id = op.get("id")
            status = op.get("status")

            # Check for various problematic states
            problematic_statuses = ["running", "scanning", "pending_approval", "preview_failed", "initializing"]

            if status in problematic_statuses:
                with self._state_lock:
                    is_tracked = op_id in self.running_operations or op_id in self.operation_processes

                if not is_tracked:
                    # Check if operation is old (> 1 hour) before cleaning up
                    try:
                        created_at_str = op.get("created_at", "")
                        if created_at_str:
                            from datetime import datetime, timedelta
                            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                            age = datetime.now() - created_at

                            # Only clean up operations older than 1 hour
                            if age > timedelta(hours=1):
                                # This is a zombie - mark it as failed
                                self._log_message(op_id, f"Cleaning up zombie operation (status: {status}, age: {age})")
                                self.storage.update_operation(op_id, {
                                    "status": "failed",
                                    "failed_at": datetime.now().isoformat(),
                                    "error_message": f"Operation cleaned up as zombie (status: {status}, age: {age})"
                                })
                                cleaned += 1
                                print(f"Cleaned up zombie operation: {op_id} (status: {status}, age: {age})")
                    except Exception as e:
                        print(f"Error checking operation age for {op_id}: {e}")

        return cleaned

    def get_running_operations(self) -> List[str]:
        """Get list of currently running operation IDs"""
        with self._state_lock:
            return list(self.running_operations.keys())

    def is_operation_running(self, operation_id: str) -> bool:
        """Check if an operation is currently running"""
        with self._state_lock:
            return operation_id in self.running_operations

    def is_operation_paused(self, operation_id: str) -> bool:
        """Check if an operation is currently paused"""
        with self._state_lock:
            return self.paused_operations.get(operation_id, False)

    def get_transfer_size(self, path: str) -> Optional[Dict[str, Any]]:
        """Get size of files at path using rclone size --json"""
        try:
            command = ["rclone", "size", "--json", path]

            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    return {
                        "count": data.get("count", 0),
                        "bytes": data.get("bytes", 0),
                        "size_formatted": self._format_bytes(data.get("bytes", 0))
                    }
                except json.JSONDecodeError:
                    return None
            else:
                print(f"rclone size failed: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            print(f"rclone size timed out for {path}")
            return None
        except Exception as e:
            print(f"Error getting transfer size: {e}")
            return None

    def _format_bytes(self, bytes_count: int) -> str:
        """Format bytes into human-readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_count < 1024.0:
                return f"{bytes_count:.2f} {unit}"
            bytes_count /= 1024.0
        return f"{bytes_count:.2f} PB"

    def estimate_transfer_time(self, size_bytes: int, source: str, destination: str) -> Dict[str, Any]:
        """Estimate transfer time based on source/destination types and size"""
        # Determine transfer type
        is_source_remote = ":" in source
        is_dest_remote = ":" in destination

        # Set speed estimates in bytes/second
        if not is_source_remote and not is_dest_remote:
            # Local to local
            speed_bps = 100 * 1024 * 1024  # 100 MB/s
            transfer_type = "local"
        elif is_source_remote and is_dest_remote:
            # Cloud to cloud
            speed_bps = 5 * 1024 * 1024  # 5 MB/s
            transfer_type = "cloud"
        else:
            # Local to cloud or cloud to local
            speed_bps = 10 * 1024 * 1024  # 10 MB/s
            transfer_type = "hybrid"

        # Calculate time in seconds
        if size_bytes > 0 and speed_bps > 0:
            time_seconds = size_bytes / speed_bps

            # Format time
            if time_seconds < 60:
                time_formatted = f"~{int(time_seconds)} seconds"
            elif time_seconds < 3600:
                minutes = int(time_seconds / 60)
                time_formatted = f"~{minutes} minute{'s' if minutes != 1 else ''}"
            else:
                hours = time_seconds / 3600
                time_formatted = f"~{hours:.1f} hour{'s' if hours >= 2 else ''}"
        else:
            time_seconds = 0
            time_formatted = "Unknown"

        return {
            "seconds": time_seconds,
            "formatted": time_formatted,
            "speed_bps": speed_bps,
            "speed_formatted": self._format_bytes(speed_bps) + "/s",
            "transfer_type": transfer_type
        }

    def _parse_dry_run_output(self, output: str) -> Dict[str, Any]:
        """Parse rclone dry-run output for statistics"""
        import re

        stats = {
            "files_to_transfer": 0,
            "files_to_check": 0,
            "files_to_delete": 0,
            "bytes_transferred": 0,
            "scan_time": 0.0,
            "errors": 0
        }

        lines = output.split('\n')

        for line in lines:
            # Parse: "Transferred:         125 / 125, 100%"
            if line.strip().startswith("Transferred:") and "/" in line:
                match = re.search(r'(\d+)\s*/\s*(\d+)', line)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    # Use total if it's the final count
                    if current == total or "100%" in line:
                        stats["files_to_transfer"] = total

            # Parse: "Checks:              150 / 150, 100%"
            if line.strip().startswith("Checks:"):
                match = re.search(r'(\d+)\s*/\s*(\d+)', line)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    if current == total or "100%" in line:
                        stats["files_to_check"] = total

            # Parse: "Deleted:               5 (files), 0 (dirs)"
            if line.strip().startswith("Deleted:"):
                match = re.search(r'(\d+)\s*\(files\)', line)
                if match:
                    stats["files_to_delete"] = int(match.group(1))

            # Parse: "Elapsed time:         5.2s"
            if "Elapsed time:" in line:
                match = re.search(r'(\d+\.?\d*)s', line)
                if match:
                    stats["scan_time"] = float(match.group(1))

            # Parse: "Errors:               119"
            if line.strip().startswith("Errors:"):
                match = re.search(r'Errors:\s+(\d+)', line)
                if match:
                    stats["errors"] = int(match.group(1))

        return stats

    def run_dry_run_preview(self, operation_type: str, source: str, destination: str,
                           rclone_args: Dict[str, Any], excludes: str) -> Optional[Dict[str, Any]]:
        """Run rclone dry-run to preview transfer statistics"""
        try:
            # Get source size first for accurate estimates
            size_info = self.get_transfer_size(source)

            # Force dry-run and stats flags
            preview_args = rclone_args.copy()
            preview_args["dry_run"] = True
            preview_args["stats"] = True  # Enable stats
            preview_args["stats_interval"] = "0"  # Show stats at end only
            preview_args["stats_one_line"] = False  # We want multi-line for parsing
            preview_args["verbose"] = True  # Get detailed output

            # Build command
            command = build_rclone_command(operation_type, source, destination, preview_args, excludes)

            print(f"Running preview command: {' '.join(command)}")

            # Execute dry-run with timeout
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=300  # 5 minute timeout for large operations
            )

            # Parse output
            output = result.stdout
            stats = self._parse_dry_run_output(output)

            # Add size information
            if size_info:
                stats["size_bytes"] = size_info["bytes"]
                stats["size_formatted"] = size_info["size_formatted"]
                stats["file_count"] = size_info["count"]
            else:
                stats["size_bytes"] = 0
                stats["size_formatted"] = "Unknown"
                stats["file_count"] = 0

            # Estimate transfer time
            time_estimate = self.estimate_transfer_time(
                stats.get("size_bytes", 0),
                source,
                destination
            )
            stats["estimated_time"] = time_estimate["formatted"]
            stats["estimated_seconds"] = time_estimate["seconds"]
            stats["speed_estimate"] = time_estimate["speed_formatted"]
            stats["transfer_type"] = time_estimate["transfer_type"]

            # Generate warnings
            warnings = []
            if stats["files_to_delete"] > 0:
                warnings.append(f"⚠️ This operation will DELETE {stats['files_to_delete']} files from destination")
            if operation_type == "move":
                warnings.append(f"⚠️ Move operation will REMOVE source files after transfer")
            if stats["errors"] > 0:
                warnings.append(f"⚠️ Dry-run encountered {stats['errors']} errors - check logs before proceeding")
            if rclone_args.get("delete"):
                warnings.append("⚠️ --delete flag is enabled")

            stats["warnings"] = warnings
            stats["command"] = " ".join(command)
            stats["success"] = result.returncode == 0

            return stats

        except subprocess.TimeoutExpired:
            print("Dry-run preview timed out after 300 seconds")
            return {
                "success": False,
                "error": "Preview timed out after 5 minutes. The operation may be very large.",
                "timeout": True,
                "allow_skip": True  # Allow user to skip preview and proceed
            }
        except Exception as e:
            print(f"Error running dry-run preview: {e}")
            return {
                "success": False,
                "error": str(e)
            }
