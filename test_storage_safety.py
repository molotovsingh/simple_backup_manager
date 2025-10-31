#!/usr/bin/env python3
"""
Test script to verify thread safety and UUID generation in storage classes
"""
import threading
import time
from job_storage import JobStorage
from rclone_storage import RcloneStorage


def test_concurrent_job_creation():
    """Test concurrent job creation to verify no ID collisions"""
    print("\n" + "="*70)
    print("Testing Concurrent Job Creation")
    print("="*70)

    storage = JobStorage("test_jobs.json")
    job_ids = []
    errors = []

    def create_job(thread_num):
        try:
            job_data = {
                "name": f"Test Job {thread_num}",
                "source": "/tmp/test_source",
                "destination": "/tmp/test_dest",
                "rsync_args": {"archive": True},
                "excludes": "",
                "max_retries": 3
            }
            job_id = storage.create_job(job_data)
            job_ids.append(job_id)
            print(f"Thread {thread_num}: Created job {job_id}")
        except Exception as e:
            errors.append(f"Thread {thread_num}: {e}")
            print(f"Thread {thread_num}: ERROR - {e}")

    # Create 50 jobs concurrently
    threads = []
    num_threads = 50

    print(f"\nCreating {num_threads} jobs concurrently...")
    start_time = time.time()

    for i in range(num_threads):
        thread = threading.Thread(target=create_job, args=(i,))
        threads.append(thread)
        thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    elapsed = time.time() - start_time

    # Check results
    print(f"\nCompleted in {elapsed:.2f} seconds")
    print(f"Jobs created: {len(job_ids)}")
    print(f"Errors: {len(errors)}")

    # Check for duplicate IDs
    unique_ids = set(job_ids)
    if len(unique_ids) != len(job_ids):
        print(f"\n❌ FAIL: ID collision detected!")
        print(f"   Expected {len(job_ids)} unique IDs, got {len(unique_ids)}")
        return False
    else:
        print(f"\n✅ PASS: All {len(job_ids)} IDs are unique")

    # Verify all IDs use UUID format
    uuid_format = all("job_" in job_id and "-" in job_id for job_id in job_ids)
    if uuid_format:
        print(f"✅ PASS: All IDs use UUID format")
    else:
        print(f"❌ FAIL: Some IDs don't use UUID format")
        return False

    if errors:
        print(f"\n⚠️  Errors encountered:")
        for error in errors:
            print(f"   {error}")

    return len(errors) == 0


def test_concurrent_operation_creation():
    """Test concurrent rclone operation creation"""
    print("\n" + "="*70)
    print("Testing Concurrent Rclone Operation Creation")
    print("="*70)

    storage = RcloneStorage("test_operations.json", "test_remotes.json")
    operation_ids = []
    errors = []

    def create_operation(thread_num):
        try:
            op_data = {
                "operation_type": "copy",
                "source": "local:/tmp/source",
                "destination": "remote:/tmp/dest",
                "rclone_args": {},
                "excludes": "",
                "max_retries": 3
            }
            op_id = storage.create_operation(op_data)
            operation_ids.append(op_id)
            print(f"Thread {thread_num}: Created operation {op_id}")
        except Exception as e:
            errors.append(f"Thread {thread_num}: {e}")
            print(f"Thread {thread_num}: ERROR - {e}")

    # Create 50 operations concurrently
    threads = []
    num_threads = 50

    print(f"\nCreating {num_threads} operations concurrently...")
    start_time = time.time()

    for i in range(num_threads):
        thread = threading.Thread(target=create_operation, args=(i,))
        threads.append(thread)
        thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    elapsed = time.time() - start_time

    # Check results
    print(f"\nCompleted in {elapsed:.2f} seconds")
    print(f"Operations created: {len(operation_ids)}")
    print(f"Errors: {len(errors)}")

    # Check for duplicate IDs
    unique_ids = set(operation_ids)
    if len(unique_ids) != len(operation_ids):
        print(f"\n❌ FAIL: ID collision detected!")
        print(f"   Expected {len(operation_ids)} unique IDs, got {len(unique_ids)}")
        return False
    else:
        print(f"\n✅ PASS: All {len(operation_ids)} IDs are unique")

    # Verify all IDs use UUID format
    uuid_format = all("rclone_" in op_id and "-" in op_id for op_id in operation_ids)
    if uuid_format:
        print(f"✅ PASS: All IDs use UUID format")
    else:
        print(f"❌ FAIL: Some IDs don't use UUID format")
        return False

    if errors:
        print(f"\n⚠️  Errors encountered:")
        for error in errors:
            print(f"   {error}")

    return len(errors) == 0


def cleanup_test_files():
    """Clean up test files"""
    import os
    test_files = ["test_jobs.json", "test_operations.json", "test_remotes.json"]
    for file in test_files:
        if os.path.exists(file):
            os.remove(file)
            print(f"Cleaned up {file}")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("Storage Safety Test Suite")
    print("="*70)

    try:
        # Run tests
        job_test_passed = test_concurrent_job_creation()
        operation_test_passed = test_concurrent_operation_creation()

        # Summary
        print("\n" + "="*70)
        print("FINAL RESULTS")
        print("="*70)
        print(f"Job Creation Test: {'✅ PASS' if job_test_passed else '❌ FAIL'}")
        print(f"Operation Creation Test: {'✅ PASS' if operation_test_passed else '❌ FAIL'}")

        if job_test_passed and operation_test_passed:
            print("\n🎉 All tests passed! Storage is thread-safe with unique UUIDs.")
            exit_code = 0
        else:
            print("\n❌ Some tests failed. Check output above.")
            exit_code = 1

    finally:
        # Cleanup
        print("\n" + "="*70)
        print("Cleaning up test files...")
        print("="*70)
        cleanup_test_files()

    import sys
    sys.exit(exit_code)
