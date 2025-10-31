#!/usr/bin/env python3
"""
Test validation utilities and security checks
Ensures path traversal, dangerous paths, and invalid inputs are rejected
"""

import unittest
import tempfile
import os
from pathlib import Path
from validation_utils import (
    sanitize_path,
    validate_path_exists,
    validate_path_readable,
    validate_path_writable,
    validate_paths_not_circular,
    validate_job_data,
    validate_operation_data,
    validate_remote_data,
    DANGEROUS_PATHS
)
from storage_errors import StorageValidationError


class TestPathSanitization(unittest.TestCase):
    """Test path sanitization and security checks"""

    def test_sanitize_valid_path(self):
        """Test that valid paths pass sanitization"""
        path = "/tmp/test/file.txt"
        result = sanitize_path(path)
        self.assertIsInstance(result, str)
        self.assertIn("tmp", result)

    def test_sanitize_rejects_null_bytes(self):
        """Test that paths with null bytes are rejected"""
        path = "/tmp/test\x00/file.txt"
        with self.assertRaises(StorageValidationError) as context:
            sanitize_path(path)
        self.assertIn("null bytes", str(context.exception).lower())

    def test_sanitize_rejects_path_traversal(self):
        """Test that path traversal attempts are caught"""
        dangerous_paths = [
            "/tmp/../../../etc/passwd",
            "/tmp/test/../../../../../../etc/passwd",
            "../../etc/passwd",
        ]

        for path in dangerous_paths:
            with self.assertRaises(StorageValidationError) as context:
                sanitize_path(path)
            self.assertIn("traversal", str(context.exception).lower(),
                         f"Path traversal not detected for: {path}")

    def test_sanitize_rejects_system_directories(self):
        """Test that dangerous system directories are rejected"""
        for dangerous_path in ["/etc", "/bin", "/sys", "/System"]:
            if dangerous_path in DANGEROUS_PATHS:
                with self.assertRaises(StorageValidationError):
                    sanitize_path(dangerous_path)

    def test_sanitize_empty_path(self):
        """Test that empty paths are rejected"""
        with self.assertRaises(StorageValidationError):
            sanitize_path("")

        with self.assertRaises(StorageValidationError):
            sanitize_path(None)


class TestPathValidation(unittest.TestCase):
    """Test path existence and permission validation"""

    def setUp(self):
        """Create temporary test directory"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = Path(self.temp_dir) / "test.txt"
        self.test_file.write_text("test content")

    def tearDown(self):
        """Clean up temporary test directory"""
        if self.test_file.exists():
            self.test_file.unlink()
        if Path(self.temp_dir).exists():
            Path(self.temp_dir).rmdir()

    def test_validate_existing_path(self):
        """Test that existing paths pass validation"""
        result = validate_path_exists(str(self.test_file), "source")
        self.assertTrue(result)

    def test_validate_nonexistent_path(self):
        """Test that non-existent paths are rejected"""
        with self.assertRaises(StorageValidationError) as context:
            validate_path_exists("/tmp/nonexistent_file_12345.txt", "source")
        self.assertIn("does not exist", str(context.exception).lower())

    def test_validate_readable_path(self):
        """Test that readable paths pass validation"""
        result = validate_path_readable(str(self.test_file))
        self.assertTrue(result)

    def test_validate_writable_path(self):
        """Test that writable paths pass validation"""
        result = validate_path_writable(str(self.temp_dir))
        self.assertTrue(result)


class TestCircularPaths(unittest.TestCase):
    """Test circular path detection"""

    def setUp(self):
        """Create temporary test directories"""
        self.temp_dir = tempfile.mkdtemp()
        self.source = Path(self.temp_dir) / "source"
        self.source.mkdir()
        self.dest_outside = Path(self.temp_dir) / "dest"
        self.dest_outside.mkdir()
        self.dest_inside = self.source / "dest"
        self.dest_inside.mkdir()

    def tearDown(self):
        """Clean up temporary directories"""
        import shutil
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_same_source_and_dest_rejected(self):
        """Test that identical source and destination are rejected"""
        with self.assertRaises(StorageValidationError) as context:
            validate_paths_not_circular(str(self.source), str(self.source))
        self.assertIn("cannot be the same", str(context.exception).lower())

    def test_dest_inside_source_rejected(self):
        """Test that destination inside source is rejected"""
        with self.assertRaises(StorageValidationError) as context:
            validate_paths_not_circular(str(self.source), str(self.dest_inside))
        self.assertIn("inside source", str(context.exception).lower())

    def test_valid_separate_paths_accepted(self):
        """Test that separate paths are accepted"""
        result = validate_paths_not_circular(str(self.source), str(self.dest_outside))
        self.assertTrue(result)


class TestJobDataValidation(unittest.TestCase):
    """Test job data validation"""

    def test_valid_job_data(self):
        """Test that valid job data passes validation"""
        job_data = {
            "name": "Test Job",
            "source": "/tmp",
            "destination": "/var/tmp",
            "max_retries": 5
        }
        is_valid, errors = validate_job_data(job_data, validate_paths=False)
        self.assertTrue(is_valid, f"Errors: {errors}")
        self.assertEqual(len(errors), 0)

    def test_missing_required_fields(self):
        """Test that missing required fields are caught"""
        job_data = {
            "name": "",  # Empty name
            "source": "",
            "destination": ""
        }
        is_valid, errors = validate_job_data(job_data, validate_paths=False)
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("name" in error.lower() for error in errors))

    def test_invalid_max_retries(self):
        """Test that invalid max_retries are caught"""
        job_data = {
            "name": "Test Job",
            "source": "/tmp",
            "destination": "/var/tmp",
            "max_retries": 150  # Too high
        }
        is_valid, errors = validate_job_data(job_data, validate_paths=False)
        self.assertFalse(is_valid)
        self.assertTrue(any("max_retries" in error.lower() for error in errors))

    def test_name_too_long(self):
        """Test that excessively long names are caught"""
        job_data = {
            "name": "A" * 300,  # 300 characters
            "source": "/tmp",
            "destination": "/var/tmp",
            "max_retries": 5
        }
        is_valid, errors = validate_job_data(job_data, validate_paths=False)
        self.assertFalse(is_valid)
        self.assertTrue(any("too long" in error.lower() for error in errors))


class TestOperationDataValidation(unittest.TestCase):
    """Test rclone operation data validation"""

    def test_valid_operation_data(self):
        """Test that valid operation data passes validation"""
        operation_data = {
            "operation_type": "copy",
            "source": "remote:path/to/source",
            "destination": "remote:path/to/dest",
            "max_retries": 3
        }
        is_valid, errors = validate_operation_data(operation_data, validate_paths=False)
        self.assertTrue(is_valid, f"Errors: {errors}")
        self.assertEqual(len(errors), 0)

    def test_invalid_operation_type(self):
        """Test that invalid operation types are caught"""
        operation_data = {
            "operation_type": "invalid_operation",
            "source": "remote:path",
            "destination": "remote:dest",
            "max_retries": 3
        }
        is_valid, errors = validate_operation_data(operation_data, validate_paths=False)
        self.assertFalse(is_valid)
        self.assertTrue(any("invalid operation type" in error.lower() for error in errors))

    def test_missing_operation_type(self):
        """Test that missing operation type is caught"""
        operation_data = {
            "operation_type": "",
            "source": "remote:path",
            "destination": "remote:dest"
        }
        is_valid, errors = validate_operation_data(operation_data, validate_paths=False)
        self.assertFalse(is_valid)
        self.assertTrue(any("operation type" in error.lower() for error in errors))


class TestRemoteDataValidation(unittest.TestCase):
    """Test remote configuration validation"""

    def test_valid_remote_data(self):
        """Test that valid remote data passes validation"""
        remote_data = {
            "name": "my-remote",
            "type": "s3"
        }
        is_valid, errors = validate_remote_data(remote_data)
        self.assertTrue(is_valid, f"Errors: {errors}")
        self.assertEqual(len(errors), 0)

    def test_invalid_remote_name_format(self):
        """Test that invalid remote name formats are caught"""
        invalid_names = [
            "my remote",  # Space
            "my@remote",  # Special char
            "my.remote",  # Dot
        ]

        for invalid_name in invalid_names:
            remote_data = {
                "name": invalid_name,
                "type": "s3"
            }
            is_valid, errors = validate_remote_data(remote_data)
            self.assertFalse(is_valid, f"Name '{invalid_name}' should be invalid")
            self.assertTrue(any("invalid" in error.lower() and "format" in error.lower()
                              for error in errors))

    def test_remote_name_too_long(self):
        """Test that excessively long remote names are caught"""
        remote_data = {
            "name": "a" * 60,  # Too long
            "type": "s3"
        }
        is_valid, errors = validate_remote_data(remote_data)
        self.assertFalse(is_valid)
        self.assertTrue(any("too long" in error.lower() for error in errors))


def run_tests():
    """Run all validation tests"""
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
