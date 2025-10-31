"""
Job executor with retry logic and progress tracking
"""
import subprocess
import threading
import time
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from job_storage import JobStorage
from rsync_builder import build_rsync_command


class JobExecutor:
    """Handles job execution with retry logic"""

    def __init__(self, storage: JobStorage, log_dir: str = "logs"):
        self.storage = storage
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.running_jobs: Dict[str, threading.Thread] = {}
        self.job_processes: Dict[str, subprocess.Popen] = {}
        self.progress_callbacks: Dict[str, Callable] = {}
        self.job_locks: Dict[str, threading.Lock] = {}
        self.stop_flags: Dict[str, threading.Event] = {}
        self.paused_jobs: Dict[str, bool] = {}
        self._state_lock = threading.Lock()  # Global state lock
    
    def _get_log_file(self, job_id: str) -> Path:
        """Get log file path for job (internal method)"""
        return self.log_dir / f"{job_id}.log"

    def get_log_file(self, job_id: str) -> Path:
        """Get log file path for job (public method)"""
        return self._get_log_file(job_id)
    
    def _log_message(self, job_id: str, message: str):
        """Log message to job log file"""
        log_file = self._get_log_file(job_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, 'a') as f:
            f.write(f"[{timestamp}] {message}\n")
    
    def _update_progress(self, job_id: str, progress_data: Dict[str, Any]):
        """Update job progress and notify callbacks"""
        # Update storage
        self.storage.update_job(job_id, {
            "progress": progress_data,
            "status": progress_data.get("status", "running")
        })
        
        # Notify progress callback if exists
        if job_id in self.progress_callbacks:
            self.progress_callbacks[job_id](job_id, progress_data)
    
    def _execute_rsync_job(self, job_id: str, job_data: Dict[str, Any]):
        """Execute rsync job with monitoring"""
        process = None
        try:
            self._log_message(job_id, f"Starting job: {job_data.get('name', 'Unnamed')}")

            # Build command
            source = job_data.get("source", "")
            destination = job_data.get("destination", "")
            rsync_args = job_data.get("rsync_args", {})
            excludes = job_data.get("excludes", "")

            command = build_rsync_command(source, destination, rsync_args, excludes)

            self._log_message(job_id, f"Command: {' '.join(command)}")

            # Start process
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                preexec_fn=os.setsid if os.name != 'nt' else None  # Create process group on Unix
            )

            with self._state_lock:
                self.job_processes[job_id] = process

            # Update status to running
            self._update_progress(job_id, {
                "status": "running",
                "started_at": datetime.now().isoformat(),
                "percent": 0,
                "bytes_transferred": 0,
                "total_bytes": 0
            })

            # Monitor output
            output_lines = []
            for line in iter(process.stdout.readline, ''):
                # Check if stop was requested
                if job_id in self.stop_flags and self.stop_flags[job_id].is_set():
                    self._log_message(job_id, "Stop requested, terminating...")
                    break

                if line:
                    output_lines.append(line.strip())
                    self._log_message(job_id, line.strip())

                    # Parse progress from rsync output (basic parsing)
                    progress = self._parse_rsync_progress(line.strip())
                    if progress:
                        self._update_progress(job_id, progress)

            # Check if we broke out due to stop
            if job_id in self.stop_flags and self.stop_flags[job_id].is_set():
                # Process was stopped by user
                self._log_message(job_id, "Job stopped by user")
                self._update_progress(job_id, {
                    "status": "stopped",
                    "stopped_at": datetime.now().isoformat()
                })
                return

            # Wait for process to complete
            returncode = process.wait()

            # Check if process died unexpectedly
            if returncode is None:
                error_msg = "Process died unexpectedly (returncode is None)"
                self._log_message(job_id, error_msg)
                self._update_progress(job_id, {
                    "status": "failed",
                    "failed_at": datetime.now().isoformat(),
                    "error_message": error_msg
                })
                return

            # Handle completion
            if returncode == 0:
                self._log_message(job_id, "Job completed successfully")
                self._update_progress(job_id, {
                    "status": "completed",
                    "completed_at": datetime.now().isoformat(),
                    "percent": 100
                })
            else:
                error_msg = f"Job failed with return code {returncode}"
                self._log_message(job_id, error_msg)
                self._update_progress(job_id, {
                    "status": "failed",
                    "failed_at": datetime.now().isoformat(),
                    "error_message": error_msg,
                    "return_code": returncode
                })

                # Check if we should retry
                self._handle_job_failure(job_id, job_data)

        except Exception as e:
            error_msg = f"Job execution error: {str(e)}"
            self._log_message(job_id, error_msg)
            self._update_progress(job_id, {
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
                    self._log_message(job_id, f"Error during process cleanup: {e}")

            # Clean up tracking dictionaries
            with self._state_lock:
                if job_id in self.job_processes:
                    del self.job_processes[job_id]
                if job_id in self.running_jobs:
                    del self.running_jobs[job_id]
                if job_id in self.stop_flags:
                    del self.stop_flags[job_id]
                if job_id in self.job_locks:
                    del self.job_locks[job_id]
                if job_id in self.paused_jobs:
                    del self.paused_jobs[job_id]
    
    def _parse_rsync_progress(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse progress information from rsync output"""
        # Basic rsync progress parsing
        # This is a simplified version - you can enhance based on your rsync output format
        
        progress = {}
        
        # Look for transfer progress like "sent 1,234,567 bytes  received 987 bytes"
        if "sent" in line and "bytes" in line:
            try:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "sent" and i + 1 < len(parts):
                        bytes_str = parts[i + 1].replace(",", "")
                        if bytes_str.isdigit():
                            progress["bytes_transferred"] = int(bytes_str)
            except (ValueError, IndexError):
                pass
        
        # Look for file count progress
        if "files..." in line.lower():
            progress["status"] = "running"
        
        return progress if progress else None
    
    def _handle_job_failure(self, job_id: str, job_data: Dict[str, Any]):
        """Handle job failure and determine if retry is needed"""
        retry_count = job_data.get("retry_count", 0)
        max_retries = job_data.get("max_retries", 5)
        
        if retry_count < max_retries:
            # Increment retry count and schedule retry
            self.storage.increment_retry_count(job_id)
            
            # Calculate backoff delay (exponential: 1s, 2s, 4s, 8s, 16s, max 60s)
            backoff = min(2 ** retry_count, 60)
            
            self._log_message(job_id, f"Scheduling retry in {backoff}s (attempt {retry_count + 1}/{max_retries})")
            
            # Schedule retry
            def retry_job():
                time.sleep(backoff)
                if job_id not in self.running_jobs:  # Don't retry if job was manually restarted
                    # Refetch job data to pick up any user edits made during execution
                    fresh_job_data = self.storage.get_job(job_id)
                    if fresh_job_data:
                        self._update_progress(job_id, {
                            "status": "running",
                            "retry_attempt": retry_count + 1
                        })
                        self._execute_rsync_job(job_id, fresh_job_data)
                    else:
                        self._log_message(job_id, "Job not found for retry, skipping")
            
            retry_thread = threading.Thread(target=retry_job, daemon=True)
            retry_thread.start()
        else:
            self._log_message(job_id, f"Max retries ({max_retries}) exceeded, giving up")
    
    def start_job(self, job_id: str, progress_callback: Optional[Callable] = None) -> bool:
        """Start a job"""
        job_data = self.storage.get_job(job_id)
        if not job_data:
            print(f"Job {job_id} not found")
            return False

        with self._state_lock:
            if job_id in self.running_jobs:
                print(f"Job {job_id} is already running")
                return False

            # Initialize synchronization primitives
            self.job_locks[job_id] = threading.Lock()
            self.stop_flags[job_id] = threading.Event()
            self.paused_jobs[job_id] = False

        # Register progress callback
        if progress_callback:
            self.progress_callbacks[job_id] = progress_callback

        # Reset retry count for manual restart
        self.storage.update_job(job_id, {"retry_count": 0})

        # Start job in thread
        thread = threading.Thread(target=self._execute_rsync_job, args=(job_id, job_data))
        thread.daemon = True
        thread.start()

        with self._state_lock:
            self.running_jobs[job_id] = thread

        return True
    
    def stop_job(self, job_id: str) -> bool:
        """Stop a running job gracefully"""
        with self._state_lock:
            # Check if job is tracked
            if job_id not in self.running_jobs and job_id not in self.job_processes:
                print(f"Job {job_id} is not running")
                return False

            # Set stop flag to signal the thread
            if job_id in self.stop_flags:
                self.stop_flags[job_id].set()

            # Get references before releasing lock
            process = self.job_processes.get(job_id)
            thread = self.running_jobs.get(job_id)

        try:
            # Terminate the process if it exists
            if process and process.poll() is None:
                self._log_message(job_id, "Stopping job...")

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
                        self._log_message(job_id, "Job stopped gracefully")
                    except subprocess.TimeoutExpired:
                        # Force kill if still running
                        self._log_message(job_id, "Timeout, force killing process...")
                        if os.name != 'nt':
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                        else:
                            process.kill()
                        process.wait()
                        self._log_message(job_id, "Job force killed")

                except (ProcessLookupError, OSError) as e:
                    self._log_message(job_id, f"Process already terminated: {e}")

            # Wait for thread to finish (with timeout)
            if thread and thread.is_alive():
                thread.join(timeout=5)
                if thread.is_alive():
                    self._log_message(job_id, "Warning: Thread did not terminate cleanly")

            # Update status
            self._update_progress(job_id, {
                "status": "stopped",
                "stopped_at": datetime.now().isoformat()
            })

            self._log_message(job_id, "Job stopped by user")
            return True

        except Exception as e:
            error_msg = f"Error stopping job {job_id}: {e}"
            print(error_msg)
            self._log_message(job_id, error_msg)
            return False
    
    def restart_failed_jobs(self, progress_callback: Optional[Callable] = None) -> int:
        """Restart all failed jobs that haven't exceeded max retries"""
        failed_jobs = self.storage.get_failed_jobs()
        restarted_count = 0
        
        for job in failed_jobs:
            retry_count = job.get("retry_count", 0)
            max_retries = job.get("max_retries", 5)
            
            if retry_count < max_retries:
                if self.start_job(job["id"], progress_callback):
                    restarted_count += 1
                    print(f"Restarted job: {job.get('name', job['id'])}")
        
        return restarted_count
    
    def pause_job(self, job_id: str) -> bool:
        """Pause a running job"""
        with self._state_lock:
            if job_id not in self.job_processes:
                print(f"Job {job_id} is not running")
                return False

            if self.paused_jobs.get(job_id, False):
                print(f"Job {job_id} is already paused")
                return False

            process = self.job_processes.get(job_id)

        try:
            if process and process.poll() is None:
                if os.name != 'nt':
                    # Unix: send SIGSTOP to process group
                    os.killpg(os.getpgid(process.pid), signal.SIGSTOP)
                    with self._state_lock:
                        self.paused_jobs[job_id] = True

                    self._log_message(job_id, "Job paused")
                    self._update_progress(job_id, {
                        "status": "paused",
                        "paused_at": datetime.now().isoformat()
                    })
                    return True
                else:
                    # Windows doesn't support SIGSTOP
                    print("Pause not supported on Windows")
                    return False
            return False

        except Exception as e:
            error_msg = f"Error pausing job {job_id}: {e}"
            print(error_msg)
            self._log_message(job_id, error_msg)
            return False

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job"""
        with self._state_lock:
            if job_id not in self.job_processes:
                print(f"Job {job_id} is not running")
                return False

            if not self.paused_jobs.get(job_id, False):
                print(f"Job {job_id} is not paused")
                return False

            process = self.job_processes.get(job_id)

        try:
            if process and process.poll() is None:
                if os.name != 'nt':
                    # Unix: send SIGCONT to process group
                    os.killpg(os.getpgid(process.pid), signal.SIGCONT)
                    with self._state_lock:
                        self.paused_jobs[job_id] = False

                    self._log_message(job_id, "Job resumed")
                    self._update_progress(job_id, {
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
            error_msg = f"Error resuming job {job_id}: {e}"
            print(error_msg)
            self._log_message(job_id, error_msg)
            return False

    def cleanup_zombie_jobs(self) -> int:
        """Clean up jobs that are marked as running but have no active process"""
        cleaned = 0
        jobs = self.storage.get_all_jobs()

        for job in jobs:
            job_id = job.get("id")
            status = job.get("status")

            # Check if marked as running but not actually running
            if status == "running":
                with self._state_lock:
                    is_tracked = job_id in self.running_jobs or job_id in self.job_processes

                if not is_tracked:
                    # This is a zombie - mark it as failed
                    self._log_message(job_id, "Detected zombie job, marking as failed")
                    self.storage.update_job(job_id, {
                        "status": "failed",
                        "failed_at": datetime.now().isoformat(),
                        "error_message": "Process terminated unexpectedly (zombie detected)"
                    })
                    cleaned += 1
                    print(f"Cleaned up zombie job: {job_id}")

        return cleaned

    def get_running_jobs(self) -> List[str]:
        """Get list of currently running job IDs"""
        with self._state_lock:
            return list(self.running_jobs.keys())

    def is_job_running(self, job_id: str) -> bool:
        """Check if a job is currently running"""
        with self._state_lock:
            return job_id in self.running_jobs

    def is_job_paused(self, job_id: str) -> bool:
        """Check if a job is currently paused"""
        with self._state_lock:
            return self.paused_jobs.get(job_id, False)
