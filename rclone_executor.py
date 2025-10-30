"""
Rclone operation executor with progress tracking
"""
import subprocess
import threading
import time
import json
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

    def _get_log_file(self, operation_id: str) -> Path:
        """Get log file path for operation"""
        return self.log_dir / f"{operation_id}.log"

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
                universal_newlines=True
            )

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
                if line:
                    output_lines.append(line.strip())
                    self._log_message(operation_id, line.strip())

                    # Parse progress from rclone output
                    progress = self._parse_rclone_progress(line.strip())
                    if progress:
                        self._update_progress(operation_id, progress)

            # Wait for process to complete
            returncode = process.wait()

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
            # Clean up
            if operation_id in self.operation_processes:
                del self.operation_processes[operation_id]
            if operation_id in self.running_operations:
                del self.running_operations[operation_id]

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
                    self._update_progress(operation_id, {
                        "status": "running (retrying...)",
                        "retry_attempt": retry_count + 1
                    })
                    self._execute_rclone_operation(operation_id, operation_data)

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

        if operation_id in self.running_operations:
            print(f"Operation {operation_id} is already running")
            return False

        # Register progress callback
        if progress_callback:
            self.progress_callbacks[operation_id] = progress_callback

        # Reset retry count for manual restart
        self.storage.update_operation(operation_id, {"retry_count": 0})

        # Start operation in thread
        thread = threading.Thread(target=self._execute_rclone_operation, args=(operation_id, operation_data))
        thread.daemon = True
        thread.start()

        self.running_operations[operation_id] = thread
        return True

    def stop_operation(self, operation_id: str) -> bool:
        """Stop a running operation"""
        if operation_id not in self.operation_processes:
            print(f"Operation {operation_id} is not running")
            return False

        try:
            process = self.operation_processes[operation_id]
            process.terminate()

            # Give it a moment to terminate gracefully
            time.sleep(2)

            if process.poll() is None:
                process.kill()

            self._log_message(operation_id, "Operation stopped by user")
            self._update_progress(operation_id, {
                "status": "stopped",
                "stopped_at": datetime.now().isoformat()
            })

            return True
        except Exception as e:
            print(f"Error stopping operation {operation_id}: {e}")
            return False

    def get_running_operations(self) -> List[str]:
        """Get list of currently running operation IDs"""
        return list(self.running_operations.keys())

    def is_operation_running(self, operation_id: str) -> bool:
        """Check if an operation is currently running"""
        return operation_id in self.running_operations
