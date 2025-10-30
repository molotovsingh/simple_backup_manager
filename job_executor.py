"""
Job executor with retry logic and progress tracking
"""
import subprocess
import threading
import time
import os
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
    
    def _get_log_file(self, job_id: str) -> Path:
        """Get log file path for job"""
        return self.log_dir / f"{job_id}.log"
    
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
                universal_newlines=True
            )
            
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
                if line:
                    output_lines.append(line.strip())
                    self._log_message(job_id, line.strip())
                    
                    # Parse progress from rsync output (basic parsing)
                    progress = self._parse_rsync_progress(line.strip())
                    if progress:
                        self._update_progress(job_id, progress)
            
            # Wait for process to complete
            returncode = process.wait()
            
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
            # Clean up
            if job_id in self.job_processes:
                del self.job_processes[job_id]
            if job_id in self.running_jobs:
                del self.running_jobs[job_id]
    
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
                    self._update_progress(job_id, {
                        "status": "running (retrying...)",
                        "retry_attempt": retry_count + 1
                    })
                    self._execute_rsync_job(job_id, job_data)
            
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
        
        if job_id in self.running_jobs:
            print(f"Job {job_id} is already running")
            return False
        
        # Register progress callback
        if progress_callback:
            self.progress_callbacks[job_id] = progress_callback
        
        # Reset retry count for manual restart
        self.storage.update_job(job_id, {"retry_count": 0})
        
        # Start job in thread
        thread = threading.Thread(target=self._execute_rsync_job, args=(job_id, job_data))
        thread.daemon = True
        thread.start()
        
        self.running_jobs[job_id] = thread
        return True
    
    def stop_job(self, job_id: str) -> bool:
        """Stop a running job gracefully"""
        if job_id not in self.job_processes:
            print(f"Job {job_id} is not running")
            return False
        
        try:
            process = self.job_processes[job_id]
            self._log_message(job_id, "Stopping job gracefully...")
            
            # Try SIGINT first (Ctrl+C) - rsync handles this cleanly
            try:
                os.kill(process.pid, 2)  # SIGINT
                self._log_message(job_id, "Sent SIGINT, waiting for cleanup...")
            except (OSError, ProcessLookupError):
                pass
            
            # Wait up to 10 seconds for graceful shutdown
            try:
                process.wait(timeout=10)
                self._log_message(job_id, "Job stopped cleanly")
            except subprocess.TimeoutExpired:
                # If still running, try SIGTERM
                self._log_message(job_id, "Timeout, sending SIGTERM...")
                process.terminate()
                
                # Wait another 5 seconds
                try:
                    process.wait(timeout=5)
                    self._log_message(job_id, "Job terminated")
                except subprocess.TimeoutExpired:
                    # Last resort: SIGKILL
                    self._log_message(job_id, "Force killing process...")
                    process.kill()
                    process.wait()
                    self._log_message(job_id, "Job force killed")
            
            self._update_progress(job_id, {
                "status": "stopped",
                "stopped_at": datetime.now().isoformat()
            })
            
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
    
    def get_running_jobs(self) -> List[str]:
        """Get list of currently running job IDs"""
        return list(self.running_jobs.keys())
    
    def is_job_running(self, job_id: str) -> bool:
        """Check if a job is currently running"""
        return job_id in self.running_jobs
