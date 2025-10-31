"""
Thread-safe rclone operations and remote storage
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


class RcloneStorage:
    """Thread-safe storage for rclone operations and remotes"""

    def __init__(self, operations_file: str = "rclone_operations.json", remotes_file: str = "rclone_remotes.json"):
        self.operations_file = Path(operations_file)
        self.remotes_file = Path(remotes_file)
        self._lock = threading.RLock()  # Reentrant lock for thread safety

        # Initialize operations file
        if not self.operations_file.exists():
            self.operations_file.touch(exist_ok=True)
            with open(self.operations_file, 'w') as f:
                json.dump({"operations": []}, f, indent=2)

        # Initialize remotes file
        if not self.remotes_file.exists():
            self.remotes_file.touch(exist_ok=True)
            with open(self.remotes_file, 'w') as f:
                json.dump({"remotes": []}, f, indent=2)

        self._operations = self._load_operations()
        self._remotes = self._load_remotes()

    def _load_operations(self) -> Dict[str, Any]:
        """Load operations from JSON file"""
        default = {"operations": []}

        try:
            return safe_json_load(self.operations_file, default)
        except Exception as e:
            print(f"Error loading operations from {self.operations_file}: {e}")
            # Try to recover from backup
            from storage_utils import recover_from_backup
            if recover_from_backup(self.operations_file):
                return safe_json_load(self.operations_file, default)
            return default

    def _load_remotes(self) -> Dict[str, Any]:
        """Load remotes from JSON file"""
        default = {"remotes": []}

        try:
            return safe_json_load(self.remotes_file, default)
        except Exception as e:
            print(f"Error loading remotes from {self.remotes_file}: {e}")
            # Try to recover from backup
            from storage_utils import recover_from_backup
            if recover_from_backup(self.remotes_file):
                return safe_json_load(self.remotes_file, default)
            return default

    def _save_operations(self):
        """Save operations to JSON file atomically"""
        try:
            # Create backup before saving
            backup_file(self.operations_file, keep_count=5)

            # Atomic write
            atomic_write(self.operations_file, self._operations, indent=2)

        except Exception as e:
            raise StorageIOError(f"Failed to save operations: {e}") from e

    def _save_remotes(self):
        """Save remotes to JSON file atomically"""
        try:
            # Create backup before saving
            backup_file(self.remotes_file, keep_count=5)

            # Atomic write
            atomic_write(self.remotes_file, self._remotes, indent=2)

        except Exception as e:
            raise StorageIOError(f"Failed to save remotes: {e}") from e

    def get_all_operations(self) -> List[Dict[str, Any]]:
        """Get all rclone operations (thread-safe)"""
        with self._lock:
            ops_list = self._operations.get("operations", [])
            if not isinstance(ops_list, list):
                print(f"Warning: operations data corrupted (expected list, got {type(ops_list)})")
                return []
            return [op.copy() for op in ops_list]

    def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get specific operation by ID (thread-safe)"""
        with self._lock:
            for operation in self._operations.get("operations", []):
                if operation.get("id") == operation_id:
                    return operation.copy()
            return None

    def get_running_operations(self) -> List[Dict[str, Any]]:
        """Get all running operations (thread-safe)"""
        with self._lock:
            return [
                op.copy() for op in self._operations.get("operations", [])
                if op.get("status") == "running"
            ]

    def create_operation(self, operation_data: Dict[str, Any]) -> str:
        """
        Create new rclone operation and return ID (thread-safe)

        Args:
            operation_data: Dictionary containing operation configuration

        Returns:
            Unique operation ID

        Raises:
            StorageError: If operation creation fails
        """
        with self._lock:
            try:
                # Generate unique UUID-based ID (no collisions)
                operation_id = generate_unique_id("rclone")

                # Ensure ID is truly unique (should never happen with UUID)
                existing_ids = {op.get("id") for op in self._operations.get("operations", [])}
                if operation_id in existing_ids:
                    # This should be impossible with UUID4
                    raise StorageError(f"ID collision detected: {operation_id}")

                # Prepare operation data
                operation_data["id"] = operation_id
                operation_data["status"] = "created"
                operation_data["created_at"] = datetime.now().isoformat()
                operation_data["retry_count"] = 0
                operation_data["max_retries"] = operation_data.get("max_retries", 3)

                # Add to operations list
                self._operations["operations"].append(operation_data)

                # Save atomically
                self._save_operations()

                return operation_id

            except Exception as e:
                raise StorageError(f"Failed to create operation: {e}") from e

    def update_operation(self, operation_id: str, updates: Dict[str, Any]):
        """
        Update operation with new data (thread-safe)

        Args:
            operation_id: ID of operation to update
            updates: Dictionary of fields to update

        Raises:
            StorageError: If update fails
        """
        with self._lock:
            try:
                op_found = False

                for i, operation in enumerate(self._operations["operations"]):
                    if operation.get("id") == operation_id:
                        self._operations["operations"][i].update(updates)
                        self._operations["operations"][i]["updated_at"] = datetime.now().isoformat()
                        op_found = True
                        break

                if not op_found:
                    print(f"Warning: Operation {operation_id} not found for update")
                    return

                # Save atomically
                self._save_operations()

            except Exception as e:
                raise StorageError(f"Failed to update operation {operation_id}: {e}") from e

    def delete_operation(self, operation_id: str):
        """
        Delete operation by ID (thread-safe)

        Args:
            operation_id: ID of operation to delete

        Raises:
            StorageError: If deletion fails
        """
        with self._lock:
            try:
                original_count = len(self._operations["operations"])

                # Filter out the operation
                self._operations["operations"] = [
                    op for op in self._operations["operations"]
                    if op.get("id") != operation_id
                ]

                new_count = len(self._operations["operations"])

                if original_count == new_count:
                    print(f"Warning: Operation {operation_id} not found for deletion")
                    return

                # Save atomically
                self._save_operations()

            except Exception as e:
                raise StorageError(f"Failed to delete operation {operation_id}: {e}") from e

    def increment_retry_count(self, operation_id: str):
        """
        Increment retry count for operation (thread-safe)

        Args:
            operation_id: ID of operation to increment retry count
        """
        with self._lock:
            operation = self.get_operation(operation_id)
            if operation:
                new_count = operation.get("retry_count", 0) + 1
                self.update_operation(operation_id, {"retry_count": new_count})

    # Remote management

    def get_all_remotes(self) -> List[Dict[str, Any]]:
        """Get all configured remotes (thread-safe)"""
        with self._lock:
            remotes_list = self._remotes.get("remotes", [])
            if not isinstance(remotes_list, list):
                print(f"Warning: remotes data corrupted (expected list, got {type(remotes_list)})")
                return []
            return [remote.copy() for remote in remotes_list]

    def get_remote(self, remote_name: str) -> Optional[Dict[str, Any]]:
        """Get specific remote by name (thread-safe)"""
        with self._lock:
            for remote in self._remotes.get("remotes", []):
                if remote.get("name") == remote_name:
                    return remote.copy()
            return None

    def add_remote(self, remote_data: Dict[str, Any]) -> str:
        """
        Add new rclone remote (thread-safe)

        Args:
            remote_data: Dictionary containing remote configuration

        Returns:
            Remote name

        Raises:
            StorageError: If remote addition fails
            ValueError: If remote name is missing or already exists
        """
        with self._lock:
            try:
                remote_name = remote_data.get("name")
                if not remote_name:
                    raise ValueError("Remote name is required")

                # Check if remote already exists
                if self.get_remote(remote_name):
                    raise ValueError(f"Remote '{remote_name}' already exists")

                # Prepare remote data
                remote_data["created_at"] = datetime.now().isoformat()

                # Add to remotes list
                self._remotes["remotes"].append(remote_data)

                # Save atomically
                self._save_remotes()

                return remote_name

            except (ValueError, KeyError) as e:
                # Re-raise validation errors as-is
                raise
            except Exception as e:
                raise StorageError(f"Failed to add remote: {e}") from e

    def update_remote(self, remote_name: str, updates: Dict[str, Any]):
        """
        Update remote configuration (thread-safe)

        Args:
            remote_name: Name of remote to update
            updates: Dictionary of fields to update

        Raises:
            StorageError: If update fails
        """
        with self._lock:
            try:
                remote_found = False

                for i, remote in enumerate(self._remotes["remotes"]):
                    if remote.get("name") == remote_name:
                        self._remotes["remotes"][i].update(updates)
                        self._remotes["remotes"][i]["updated_at"] = datetime.now().isoformat()
                        remote_found = True
                        break

                if not remote_found:
                    print(f"Warning: Remote {remote_name} not found for update")
                    return

                # Save atomically
                self._save_remotes()

            except Exception as e:
                raise StorageError(f"Failed to update remote {remote_name}: {e}") from e

    def delete_remote(self, remote_name: str):
        """
        Delete remote by name (thread-safe)

        Args:
            remote_name: Name of remote to delete

        Raises:
            StorageError: If deletion fails
        """
        with self._lock:
            try:
                original_count = len(self._remotes["remotes"])

                # Filter out the remote
                self._remotes["remotes"] = [
                    r for r in self._remotes["remotes"]
                    if r.get("name") != remote_name
                ]

                new_count = len(self._remotes["remotes"])

                if original_count == new_count:
                    print(f"Warning: Remote {remote_name} not found for deletion")
                    return

                # Save atomically
                self._save_remotes()

            except Exception as e:
                raise StorageError(f"Failed to delete remote {remote_name}: {e}") from e

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
