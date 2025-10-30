"""
Simple JSON-based job storage for restart manager
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path


class JobStorage:
    """Simple JSON file-based job storage"""
    
    def __init__(self, jobs_file: str = "jobs.json"):
        self.jobs_file = Path(jobs_file)
        self.jobs_file.touch(exist_ok=True)
        self._jobs = self._load_jobs()
    
    def _load_jobs(self) -> List[Dict[str, Any]]:
        """Load jobs from JSON file"""
        try:
            if self.jobs_file.stat().st_size == 0:
                return {"jobs": []}
            
            with open(self.jobs_file, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, dict) and "jobs" in data else {"jobs": []}
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error loading jobs: {e}")
            return {"jobs": []}
    
    def _save_jobs(self):
        """Save jobs to JSON file"""
        try:
            with open(self.jobs_file, 'w') as f:
                json.dump(self._jobs, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving jobs: {e}")
    
    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs"""
        return self._jobs.get("jobs", [])
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get specific job by ID"""
        for job in self.get_all_jobs():
            if job.get("id") == job_id:
                return job
        return None
    
    def get_failed_jobs(self) -> List[Dict[str, Any]]:
        """Get all failed jobs"""
        return [job for job in self.get_all_jobs() if job.get("status") == "failed"]
    
    def create_job(self, job_data: Dict[str, Any]) -> str:
        """Create new job and return ID"""
        job_id = f"job_{int(datetime.now().timestamp())}"
        job_data["id"] = job_id
        job_data["status"] = "created"
        job_data["created_at"] = datetime.now().isoformat()
        job_data["retry_count"] = 0
        job_data["max_retries"] = job_data.get("max_retries", 5)
        
        self._jobs["jobs"].append(job_data)
        self._save_jobs()
        return job_id
    
    def update_job(self, job_id: str, updates: Dict[str, Any]):
        """Update job with new data"""
        for i, job in enumerate(self._jobs["jobs"]):
            if job.get("id") == job_id:
                self._jobs["jobs"][i].update(updates)
                self._jobs["jobs"][i]["updated_at"] = datetime.now().isoformat()
                break
        self._save_jobs()
    
    def delete_job(self, job_id: str):
        """Delete job by ID"""
        self._jobs["jobs"] = [job for job in self._jobs["jobs"] if job.get("id") != job_id]
        self._save_jobs()
    
    def increment_retry_count(self, job_id: str):
        """Increment retry count for job"""
        job = self.get_job(job_id)
        if job:
            new_count = job.get("retry_count", 0) + 1
            self.update_job(job_id, {"retry_count": new_count})
