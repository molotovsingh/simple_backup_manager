"""
Thread-safe JSON-based job storage for restart manager
"""
import json
import os
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from storage_utils import (
    generate_unique_id,
    atomic_write,
    safe_json_load,
    backup_file
)
from storage_errors import StorageError, StorageIOError


class JobStorage:
    """Thread-safe JSON file-based job storage"""

    def __init__(self, jobs_file: str = "jobs.json"):
        self.jobs_file = Path(jobs_file)
        self._lock = threading.RLock()  # Reentrant lock for thread safety

        # Initialize file if it doesn't exist
        if not self.jobs_file.exists():
            self.jobs_file.touch(exist_ok=True)
            with open(self.jobs_file, 'w') as f:
                json.dump({"jobs": []}, f, indent=2)

        self._jobs = self._load_jobs()

    def _load_jobs(self) -> Dict[str, Any]:
        """Load jobs from JSON file"""
        default = {"jobs": []}

        try:
            return safe_json_load(self.jobs_file, default)
        except Exception as e:
            print(f"Error loading jobs from {self.jobs_file}: {e}")
            # Try to recover from backup
            from storage_utils import recover_from_backup
            if recover_from_backup(self.jobs_file):
                return safe_json_load(self.jobs_file, default)
            return default

    def _save_jobs(self):
        """Save jobs to JSON file atomically"""
        try:
            # Create backup before saving
            backup_file(self.jobs_file, keep_count=5)

            # Atomic write
            atomic_write(self.jobs_file, self._jobs, indent=2)

        except Exception as e:
            raise StorageIOError(f"Failed to save jobs: {e}") from e

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs (thread-safe)"""
        with self._lock:
            return self._jobs.get("jobs", []).copy()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get specific job by ID (thread-safe)"""
        with self._lock:
            for job in self._jobs.get("jobs", []):
                if job.get("id") == job_id:
                    return job.copy()
            return None

    def get_failed_jobs(self) -> List[Dict[str, Any]]:
        """Get all failed jobs (thread-safe)"""
        with self._lock:
            return [
                job.copy() for job in self._jobs.get("jobs", [])
                if job.get("status") == "failed"
            ]

    def create_job(self, job_data: Dict[str, Any]) -> str:
        """
        Create new job and return ID (thread-safe)

        Args:
            job_data: Dictionary containing job configuration

        Returns:
            Unique job ID

        Raises:
            StorageError: If job creation fails
        """
        with self._lock:
            try:
                # Generate unique UUID-based ID (no collisions)
                job_id = generate_unique_id("job")

                # Ensure ID is truly unique (should never happen with UUID)
                existing_ids = {job.get("id") for job in self._jobs.get("jobs", [])}
                if job_id in existing_ids:
                    # This should be impossible with UUID4
                    raise StorageError(f"ID collision detected: {job_id}")

                # Prepare job data
                job_data["id"] = job_id
                job_data["status"] = "created"
                job_data["created_at"] = datetime.now().isoformat()
                job_data["retry_count"] = 0
                job_data["max_retries"] = job_data.get("max_retries", 5)

                # Add to jobs list
                self._jobs["jobs"].append(job_data)

                # Save atomically
                self._save_jobs()

                return job_id

            except Exception as e:
                raise StorageError(f"Failed to create job: {e}") from e

    def update_job(self, job_id: str, updates: Dict[str, Any]):
        """
        Update job with new data (thread-safe)

        Args:
            job_id: ID of job to update
            updates: Dictionary of fields to update

        Raises:
            StorageError: If update fails
        """
        with self._lock:
            try:
                job_found = False

                for i, job in enumerate(self._jobs["jobs"]):
                    if job.get("id") == job_id:
                        self._jobs["jobs"][i].update(updates)
                        self._jobs["jobs"][i]["updated_at"] = datetime.now().isoformat()
                        job_found = True
                        break

                if not job_found:
                    print(f"Warning: Job {job_id} not found for update")
                    return

                # Save atomically
                self._save_jobs()

            except Exception as e:
                raise StorageError(f"Failed to update job {job_id}: {e}") from e

    def delete_job(self, job_id: str):
        """
        Delete job by ID (thread-safe)

        Args:
            job_id: ID of job to delete

        Raises:
            StorageError: If deletion fails
        """
        with self._lock:
            try:
                original_count = len(self._jobs["jobs"])

                # Filter out the job
                self._jobs["jobs"] = [
                    job for job in self._jobs["jobs"]
                    if job.get("id") != job_id
                ]

                new_count = len(self._jobs["jobs"])

                if original_count == new_count:
                    print(f"Warning: Job {job_id} not found for deletion")
                    return

                # Save atomically
                self._save_jobs()

            except Exception as e:
                raise StorageError(f"Failed to delete job {job_id}: {e}") from e

    def increment_retry_count(self, job_id: str):
        """
        Increment retry count for job (thread-safe)

        Args:
            job_id: ID of job to increment retry count
        """
        with self._lock:
            job = self.get_job(job_id)
            if job:
                new_count = job.get("retry_count", 0) + 1
                self.update_job(job_id, {"retry_count": new_count})
