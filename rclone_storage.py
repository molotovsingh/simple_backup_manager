"""
Rclone operations and remote storage
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path


class RcloneStorage:
    """Storage for rclone operations and remotes"""

    def __init__(self, operations_file: str = "rclone_operations.json", remotes_file: str = "rclone_remotes.json"):
        self.operations_file = Path(operations_file)
        self.remotes_file = Path(remotes_file)
        self.operations_file.touch(exist_ok=True)
        self.remotes_file.touch(exist_ok=True)
        self._operations = self._load_operations()
        self._remotes = self._load_remotes()

    def _load_operations(self) -> Dict[str, Any]:
        """Load operations from JSON file"""
        try:
            if self.operations_file.stat().st_size == 0:
                return {"operations": []}

            with open(self.operations_file, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, dict) and "operations" in data else {"operations": []}
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error loading operations: {e}")
            return {"operations": []}

    def _load_remotes(self) -> Dict[str, Any]:
        """Load remotes from JSON file"""
        try:
            if self.remotes_file.stat().st_size == 0:
                return {"remotes": []}

            with open(self.remotes_file, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, dict) and "remotes" in data else {"remotes": []}
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error loading remotes: {e}")
            return {"remotes": []}

    def _save_operations(self):
        """Save operations to JSON file"""
        try:
            with open(self.operations_file, 'w') as f:
                json.dump(self._operations, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving operations: {e}")

    def _save_remotes(self):
        """Save remotes to JSON file"""
        try:
            with open(self.remotes_file, 'w') as f:
                json.dump(self._remotes, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving remotes: {e}")

    def get_all_operations(self) -> List[Dict[str, Any]]:
        """Get all rclone operations"""
        ops_list = self._operations.get("operations", [])
        return ops_list if isinstance(ops_list, list) else []

    def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get specific operation by ID"""
        for operation in self.get_all_operations():
            if operation.get("id") == operation_id:
                return operation
        return None

    def get_running_operations(self) -> List[Dict[str, Any]]:
        """Get all running operations"""
        return [op for op in self.get_all_operations() if op.get("status") == "running"]

    def create_operation(self, operation_data: Dict[str, Any]) -> str:
        """Create new rclone operation and return ID"""
        operation_id = f"rclone_{int(datetime.now().timestamp())}"
        operation_data["id"] = operation_id
        operation_data["status"] = "created"
        operation_data["created_at"] = datetime.now().isoformat()
        operation_data["retry_count"] = 0
        operation_data["max_retries"] = operation_data.get("max_retries", 3)

        self._operations["operations"].append(operation_data)
        self._save_operations()
        return operation_id

    def update_operation(self, operation_id: str, updates: Dict[str, Any]):
        """Update operation with new data"""
        ops_list = self._operations.get("operations", [])
        for i, operation in enumerate(ops_list):
            if operation.get("id") == operation_id:
                ops_list[i].update(updates)
                ops_list[i]["updated_at"] = datetime.now().isoformat()
                break
        self._save_operations()

    def delete_operation(self, operation_id: str):
        """Delete operation by ID"""
        ops_list = self._operations.get("operations", [])
        self._operations["operations"] = [op for op in ops_list if op.get("id") != operation_id]
        self._save_operations()

    def increment_retry_count(self, operation_id: str):
        """Increment retry count for operation"""
        operation = self.get_operation(operation_id)
        if operation:
            new_count = operation.get("retry_count", 0) + 1
            self.update_operation(operation_id, {"retry_count": new_count})

    # Remote management
    def get_all_remotes(self) -> List[Dict[str, Any]]:
        """Get all configured remotes"""
        remotes_list = self._remotes.get("remotes", [])
        return remotes_list if isinstance(remotes_list, list) else []

    def get_remote(self, remote_name: str) -> Optional[Dict[str, Any]]:
        """Get specific remote by name"""
        for remote in self.get_all_remotes():
            if remote.get("name") == remote_name:
                return remote
        return None

    def add_remote(self, remote_data: Dict[str, Any]) -> str:
        """Add new rclone remote"""
        remote_name = remote_data.get("name")
        if not remote_name:
            raise ValueError("Remote name is required")

        # Check if remote already exists
        if self.get_remote(remote_name):
            raise ValueError(f"Remote '{remote_name}' already exists")

        remote_data["created_at"] = datetime.now().isoformat()
        self._remotes["remotes"].append(remote_data)
        self._save_remotes()
        return remote_name

    def update_remote(self, remote_name: str, updates: Dict[str, Any]):
        """Update remote configuration"""
        remotes_list = self._remotes.get("remotes", [])
        for i, remote in enumerate(remotes_list):
            if remote.get("name") == remote_name:
                remotes_list[i].update(updates)
                remotes_list[i]["updated_at"] = datetime.now().isoformat()
                break
        self._save_remotes()

    def delete_remote(self, remote_name: str):
        """Delete remote by name"""
        remotes_list = self._remotes.get("remotes", [])
        self._remotes["remotes"] = [r for r in remotes_list if r.get("name") != remote_name]
        self._save_remotes()

    def get_remote_types(self) -> List[str]:
        """Get list of supported remote types"""
        return [
            "s3",
            "dropbox",
            "google_cloud_storage",
            "azure_blob",
            "b2",
            "sftp",
            "ftp",
            "local",
        ]
