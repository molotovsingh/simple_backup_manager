"""
Rclone configuration management
"""
import subprocess
import os
from pathlib import Path
from typing import Dict, List, Any, Optional


class RcloneConfig:
    """Handle rclone configuration and remote management"""

    def __init__(self, config_dir: str = "~/.config/rclone"):
        self.config_dir = Path(config_dir).expanduser()
        self.config_file = self.config_dir / "rclone.conf"
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def is_rclone_installed(self) -> bool:
        """Check if rclone is installed"""
        try:
            result = subprocess.run(
                ["rclone", "version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def get_rclone_version(self) -> Optional[str]:
        """Get installed rclone version"""
        try:
            result = subprocess.run(
                ["rclone", "version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # First line usually contains version info
                return result.stdout.split('\n')[0].strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def list_remotes(self) -> List[str]:
        """List all configured rclone remotes"""
        try:
            result = subprocess.run(
                ["rclone", "listremotes"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                remotes = result.stdout.strip().split('\n')
                return [r.rstrip(':') for r in remotes if r.strip()]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return []

    def test_remote(self, remote_name: str) -> Dict[str, Any]:
        """Test remote connection"""
        try:
            # Try to list contents of remote
            result = subprocess.run(
                ["rclone", "lsd", f"{remote_name}:"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": "Remote connection successful",
                    "output": result.stdout
                }
            else:
                return {
                    "success": False,
                    "message": "Remote connection failed",
                    "error": result.stderr
                }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Connection test timed out",
                "error": "Request took too long"
            }
        except FileNotFoundError:
            return {
                "success": False,
                "message": "Rclone not installed",
                "error": "Rclone executable not found"
            }
        except Exception as e:
            return {
                "success": False,
                "message": "Connection test error",
                "error": str(e)
            }

    def get_remote_info(self, remote_name: str) -> Dict[str, Any]:
        """Get information about a remote"""
        try:
            result = subprocess.run(
                ["rclone", "config", "show", remote_name],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "info": result.stdout
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr
                }
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return {"success": False, "error": "Failed to get remote info"}

    def supported_backends(self) -> List[str]:
        """Get list of supported backends"""
        try:
            result = subprocess.run(
                ["rclone", "listproviders"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                backends = []
                for line in result.stdout.strip().split('\n'):
                    if line.strip() and not line.startswith(' '):
                        backend = line.split()[0]
                        if backend:
                            backends.append(backend)
                return backends
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback list of common backends
        return [
            "local",
            "s3",
            "drive",
            "dropbox",
            "b2",
            "azureblob",
            "gdrive",
            "sftp",
            "ftp",
            "http",
            "onedrive",
            "mega",
        ]

    def estimate_size(self, remote_name: str, path: str = "") -> Optional[Dict[str, Any]]:
        """Estimate size of remote path"""
        try:
            remote_path = f"{remote_name}:{path}" if path else f"{remote_name}:"
            result = subprocess.run(
                ["rclone", "size", remote_path],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "output": result.stdout
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr
                }
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None
