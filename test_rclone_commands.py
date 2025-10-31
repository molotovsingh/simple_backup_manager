#!/usr/bin/env python3
"""
Test rclone command builder
Ensures commands are correctly built and don't include invalid flags
"""

import unittest
from rclone_builder import (
    build_rclone_command,
    build_rclone_command_string,
    get_default_rclone_args,
    validate_rclone_args,
    get_rclone_operations
)


class TestRcloneCommandBuilder(unittest.TestCase):
    """Test rclone command building"""

    def test_basic_copy_command(self):
        """Test basic copy command generation"""
        command = build_rclone_command(
            "copy",
            "/source",
            "/dest",
            {"verbose": True},
            ""
        )

        self.assertIn("rclone", command[0])
        self.assertIn("copy", command)
        self.assertIn("-v", command)
        self.assertIn("/source", command)
        self.assertIn("/dest", command)

    def test_no_json_flag_in_command(self):
        """Test that --json flag is NOT added (invalid for copy/sync/move)"""
        args = get_default_rclone_args()
        # Even if json was in the args, it shouldn't appear in the command
        args_with_json = args.copy()
        args_with_json["json"] = True  # Try to force it

        command = build_rclone_command(
            "copy",
            "/source",
            "/dest",
            args_with_json,
            ""
        )

        # Verify --json is NOT in the command
        self.assertNotIn("--json", command,
                        "--json flag should not be added to rclone copy/sync/move commands")

    def test_stats_flag_correct_format(self):
        """Test that stats flags are correctly formatted"""
        args = {
            "stats": True,
            "stats_interval": "10s",
            "stats_one_line": False
        }

        command = build_rclone_command("copy", "/source", "/dest", args, "")

        # Should have --stats with the interval value
        self.assertIn("--stats", command)
        stats_idx = command.index("--stats")
        self.assertEqual(command[stats_idx + 1], "10s")

    def test_stats_end_only_for_preview(self):
        """Test that preview dry-run uses stats at end only"""
        args = {
            "dry_run": True,
            "stats": True,
            "stats_interval": "0",  # End only
            "verbose": True
        }

        command = build_rclone_command("copy", "/source", "/dest", args, "")

        self.assertIn("--dry-run", command)
        self.assertIn("--stats", command)
        # Verify stats interval is "0" (end-of-run only)
        stats_idx = command.index("--stats")
        self.assertEqual(command[stats_idx + 1], "0")

    def test_exclude_patterns(self):
        """Test that exclude patterns are correctly added"""
        command = build_rclone_command(
            "copy",
            "/source",
            "/dest",
            {},
            "*.tmp *.log .DS_Store"
        )

        self.assertIn("--exclude", command)
        self.assertIn("*.tmp", command)
        self.assertIn("*.log", command)
        self.assertIn(".DS_Store", command)

    def test_operation_specific_flags(self):
        """Test that operation-specific flags are added correctly"""
        # Sync with delete
        sync_command = build_rclone_command(
            "sync",
            "/source",
            "/dest",
            {"delete": True},
            ""
        )
        self.assertIn("--delete-during", sync_command)

        # Move with delete empty dirs
        move_command = build_rclone_command(
            "move",
            "/source",
            "/dest",
            {"delete_empty_src_dirs": True},
            ""
        )
        self.assertIn("--delete-empty-src-dirs", move_command)

    def test_performance_flags(self):
        """Test that performance flags are correctly formatted"""
        args = {
            "transfers": "8",
            "checkers": "16",
            "bwlimit": "10M"
        }

        command = build_rclone_command("copy", "/source", "/dest", args, "")

        self.assertIn("--transfers", command)
        self.assertIn("8", command)
        self.assertIn("--checkers", command)
        self.assertIn("16", command)
        self.assertIn("--bwlimit", command)
        self.assertIn("10M", command)

    def test_dry_run_flag(self):
        """Test that dry-run flag is correctly added"""
        command = build_rclone_command(
            "copy",
            "/source",
            "/dest",
            {"dry_run": True},
            ""
        )

        self.assertIn("--dry-run", command)


class TestRcloneDefaults(unittest.TestCase):
    """Test default rclone arguments"""

    def test_default_args_structure(self):
        """Test that default args have expected structure"""
        defaults = get_default_rclone_args()

        self.assertIsInstance(defaults, dict)
        self.assertIn("verbose", defaults)
        self.assertIn("progress", defaults)
        self.assertIn("transfers", defaults)
        self.assertIn("stats", defaults)

    def test_no_json_in_defaults(self):
        """Test that 'json' is NOT in default args"""
        defaults = get_default_rclone_args()

        self.assertNotIn("json", defaults,
                        "'json' should not be in default rclone args (invalid flag)")

    def test_stats_enabled_by_default(self):
        """Test that stats are enabled by default"""
        defaults = get_default_rclone_args()

        self.assertTrue(defaults.get("stats"),
                       "Stats should be enabled by default")


class TestRcloneValidation(unittest.TestCase):
    """Test rclone argument validation"""

    def test_validate_delete_warning(self):
        """Test that delete flag triggers warning"""
        args = {
            "source": "/source",
            "destination": "/dest",
            "delete": True
        }

        errors = validate_rclone_args(args)

        self.assertGreater(len(errors), 0)
        self.assertTrue(any("delete" in error.lower() for error in errors))

    def test_validate_missing_source(self):
        """Test that missing source triggers error"""
        args = {
            "source": "",
            "destination": "/dest"
        }

        errors = validate_rclone_args(args)

        self.assertGreater(len(errors), 0)
        self.assertTrue(any("source" in error.lower() for error in errors))

    def test_validate_missing_destination(self):
        """Test that missing destination triggers error"""
        args = {
            "source": "/source",
            "destination": ""
        }

        errors = validate_rclone_args(args)

        self.assertGreater(len(errors), 0)
        self.assertTrue(any("destination" in error.lower() for error in errors))


class TestRcloneOperations(unittest.TestCase):
    """Test rclone operation types"""

    def test_get_rclone_operations(self):
        """Test that supported operations are returned"""
        operations = get_rclone_operations()

        self.assertIsInstance(operations, list)
        self.assertIn("copy", operations)
        self.assertIn("sync", operations)
        self.assertIn("move", operations)
        self.assertIn("delete", operations)
        self.assertIn("check", operations)


class TestCommandStringGeneration(unittest.TestCase):
    """Test command string generation for display"""

    def test_command_string_format(self):
        """Test that command string is properly formatted"""
        command_str = build_rclone_command_string(
            "copy",
            "/source",
            "/dest",
            {"verbose": True},
            ""
        )

        self.assertIsInstance(command_str, str)
        self.assertIn("rclone", command_str)
        self.assertIn("copy", command_str)
        self.assertIn("-v", command_str)

    def test_command_string_no_json(self):
        """Test that command string doesn't contain --json"""
        args = get_default_rclone_args()

        command_str = build_rclone_command_string(
            "sync",
            "remote:source",
            "remote:dest",
            args,
            ""
        )

        self.assertNotIn("--json", command_str,
                        "Command string should not contain --json flag")


def run_tests():
    """Run all rclone command tests"""
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
