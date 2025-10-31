#!/usr/bin/env python3
"""
Test status string enumeration
Ensures status fields never contain spaces or special characters
that would break CSS classes and JavaScript comparisons
"""

import unittest
import re
from job_storage import JobStorage
from job_executor import JobExecutor
from rclone_storage import RcloneStorage
from rclone_executor import RcloneExecutor


# Valid status values (enumerated)
VALID_JOB_STATUSES = {
    'pending', 'pending_restart', 'running', 'paused', 'stopped',
    'completed', 'failed', 'created'
}

VALID_RCLONE_STATUSES = {
    'pending', 'pending_approval', 'initializing', 'preview_failed',
    'running', 'scanning', 'paused', 'stopped', 'completed', 'failed', 'created'
}


class TestStatusEnumeration(unittest.TestCase):
    """Test that status strings are properly enumerated"""

    def test_status_no_spaces(self):
        """Status values must not contain spaces"""
        for status in VALID_JOB_STATUSES | VALID_RCLONE_STATUSES:
            self.assertNotIn(' ', status,
                           f"Status '{status}' contains spaces - will break CSS classes")

    def test_status_no_special_chars(self):
        """Status values should only contain alphanumeric, underscore, hyphen"""
        pattern = re.compile(r'^[a-z0-9_-]+$')
        for status in VALID_JOB_STATUSES | VALID_RCLONE_STATUSES:
            self.assertTrue(pattern.match(status),
                          f"Status '{status}' contains invalid characters")

    def test_status_lowercase(self):
        """Status values should be lowercase (for consistent CSS classes)"""
        for status in VALID_JOB_STATUSES | VALID_RCLONE_STATUSES:
            self.assertEqual(status, status.lower(),
                           f"Status '{status}' should be lowercase")


class TestJobExecutorStatus(unittest.TestCase):
    """Test JobExecutor status handling"""

    def setUp(self):
        """Set up test environment"""
        self.storage = JobStorage()
        self.executor = JobExecutor(self.storage)

    def test_retry_keeps_running_status(self):
        """Test that retries don't modify status with extra text"""
        # Create a mock job
        job_data = {
            "name": "Test Job",
            "source": "/tmp/test_source",
            "destination": "/tmp/test_dest",
            "rsync_args": {},
            "max_retries": 5,
            "retry_count": 2
        }
        job_id = self.storage.create_job(job_data)

        # Simulate retry - update progress with retry_attempt
        self.executor._update_progress(job_id, {
            "status": "running",
            "retry_attempt": 3
        })

        # Retrieve job and check status
        job = self.storage.get_job(job_id)
        self.assertIsNotNone(job)
        self.assertIn(job['progress']['status'], VALID_JOB_STATUSES,
                     f"Status '{job['progress']['status']}' is not in valid statuses")
        self.assertEqual(job['progress']['status'], 'running',
                        "Retry should keep status as 'running', not modify it")
        self.assertEqual(job['progress'].get('retry_attempt'), 3,
                        "Retry attempt should be in separate field")

    def test_all_job_statuses_are_valid(self):
        """Test that all possible job statuses are enumerated"""
        # Test various status transitions
        test_statuses = ['pending', 'running', 'completed', 'failed', 'stopped', 'paused']

        for status in test_statuses:
            self.assertIn(status, VALID_JOB_STATUSES,
                         f"Status '{status}' should be in VALID_JOB_STATUSES")


class TestRcloneExecutorStatus(unittest.TestCase):
    """Test RcloneExecutor status handling"""

    def setUp(self):
        """Set up test environment"""
        self.storage = RcloneStorage()
        self.executor = RcloneExecutor(self.storage)

    def test_retry_keeps_running_status(self):
        """Test that rclone retries don't modify status with extra text"""
        # Create a mock operation
        operation_data = {
            "name": "Test Operation",
            "source": "/tmp/test_source",
            "destination": "/tmp/test_dest",
            "operation_type": "copy",
            "rclone_args": {},
            "max_retries": 3,
            "retry_count": 1
        }
        operation_id = self.storage.create_operation(operation_data)

        # Simulate retry - update progress with retry_attempt
        self.executor._update_progress(operation_id, {
            "status": "running",
            "retry_attempt": 2
        })

        # Retrieve operation and check status
        operation = self.storage.get_operation(operation_id)
        self.assertIsNotNone(operation)
        self.assertIn(operation['progress']['status'], VALID_RCLONE_STATUSES,
                     f"Status '{operation['progress']['status']}' is not in valid statuses")
        self.assertEqual(operation['progress']['status'], 'running',
                        "Retry should keep status as 'running', not modify it")
        self.assertEqual(operation['progress'].get('retry_attempt'), 2,
                        "Retry attempt should be in separate field")

    def test_all_rclone_statuses_are_valid(self):
        """Test that all possible rclone statuses are enumerated"""
        test_statuses = [
            'pending', 'pending_approval', 'initializing', 'preview_failed',
            'running', 'scanning', 'completed', 'failed', 'stopped', 'paused'
        ]

        for status in test_statuses:
            self.assertIn(status, VALID_RCLONE_STATUSES,
                         f"Status '{status}' should be in VALID_RCLONE_STATUSES")


class TestCSSClassGeneration(unittest.TestCase):
    """Test that status values generate valid CSS classes"""

    def test_status_generates_valid_css_class(self):
        """Test that status values create valid CSS class names"""
        # CSS class name pattern: alphanumeric, hyphen, underscore
        css_class_pattern = re.compile(r'^status-[a-z0-9_-]+$')

        for status in VALID_JOB_STATUSES | VALID_RCLONE_STATUSES:
            css_class = f"status-{status}"
            self.assertTrue(css_class_pattern.match(css_class),
                           f"Status '{status}' generates invalid CSS class: {css_class}")

    def test_no_parentheses_in_status(self):
        """Ensure no status contains parentheses (would break CSS)"""
        for status in VALID_JOB_STATUSES | VALID_RCLONE_STATUSES:
            self.assertNotIn('(', status, f"Status '{status}' contains '('")
            self.assertNotIn(')', status, f"Status '{status}' contains ')'")


def run_tests():
    """Run all status enumeration tests"""
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
