#!/usr/bin/env python3
"""
Comprehensive Test Automation Script for Flask Job Restart Manager
Tests all frontend functionality through backend API endpoints
"""

import requests
import json
import time
import subprocess
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Any


class FrontendTester:
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        self.test_results = []
        
    def log_test(self, test_name: str, status: str, details: str = "", response_data: Any = None):
        """Log test results"""
        result = {
            "timestamp": datetime.now().isoformat(),
            "test": test_name,
            "status": status,
            "details": details,
            "response": response_data
        }
        self.test_results.append(result)
        print(f"[{status}] {test_name}: {details}")
        
    def test_api_endpoint(self, method: str, endpoint: str, data: Dict = None, expected_status: int = 200) -> Dict:
        """Generic API test method"""
        url = f"{self.base_url}{endpoint}"
        try:
            if method.upper() == "GET":
                response = self.session.get(url)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data)
            elif method.upper() == "DELETE":
                response = self.session.delete(url)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            response_data = response.json() if response.content else {}
            
            if response.status_code == expected_status:
                return {"success": True, "data": response_data}
            else:
                return {"success": False, "data": response_data, "status_code": response.status_code}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def test_initial_setup(self):
        """Test Phase 1: Application Setup"""
        print("\n=== Phase 1: Application Setup & Basic Navigation ===")
        
        # Test main page load
        result = self.test_api_endpoint("GET", "/")
        if result["success"]:
            self.log_test("Main Page Load", "PASS", "Flask application serving HTML")
        else:
            self.log_test("Main Page Load", "FAIL", f"HTTP {result.get('status_code', 'Unknown')}")
        
        # Test jobs API
        result = self.test_api_endpoint("GET", "/api/jobs")
        if result["success"]:
            jobs = result["data"].get("jobs", [])
            self.log_test("Jobs API", "PASS", f"Found {len(jobs)} jobs")
        else:
            self.log_test("Jobs API", "FAIL", f"HTTP {result.get('status_code', 'Unknown')}")
            
        # Test rclone status
        result = self.test_api_endpoint("GET", "/api/rclone/status")
        if result["success"]:
            rclone_status = result["data"]
            self.log_test("Rclone Status", "PASS", f"rclone {rclone_status.get('version', 'N/A')}")
        else:
            self.log_test("Rclone Status", "FAIL", f"HTTP {result.get('status_code', 'Unknown')}")
    
    def test_job_management(self):
        """Test Phase 2: Core Job Management"""
        print("\n=== Phase 2: Core Job Management Testing ===")
        
        # Test job creation
        job_data = {
            "name": f"Frontend Test Job {int(time.time())}",
            "source": "/tmp/frontend_test_source",
            "destination": "/tmp/frontend_test_destination",
            "rsync_args": {
                "archive": True,
                "verbose": True,
                "progress": True,
                "dry_run": True
            },
            "excludes": "*.tmp .DS_Store",
            "max_retries": 3
        }
        
        result = self.test_api_endpoint("POST", "/api/job/create", job_data)
        if result["success"]:
            job_id = result["data"]["job_id"]
            self.log_test("Job Creation", "PASS", f"Created job {job_id}")
            
            # Test job operations
            start_result = self.test_api_endpoint("POST", f"/api/job/{job_id}/start")
            if start_result["success"]:
                self.log_test("Job Start", "PASS", "Job started successfully")
                
                # Check job status
                time.sleep(2)
                status_result = self.test_api_endpoint("GET", f"/api/job/{job_id}")
                if status_result["success"]:
                    status = status_result["data"].get("status")
                    self.log_test("Job Status Check", "PASS", f"Job status: {status}")
                
                # Test job logs
                logs_result = self.test_api_endpoint("GET", f"/api/job/{job_id}/logs")
                if logs_result["success"]:
                    self.log_test("Job Logs", "PASS", f"Logs retrieved ({len(logs_result['data'].get('logs', ''))} chars)")
            else:
                self.log_test("Job Start", "FAIL", "Failed to start job")
        else:
            self.log_test("Job Creation", "FAIL", "Failed to create job")
    
    def test_command_preview(self):
        """Test command preview functionality"""
        print("\n=== Phase 2: Command Preview Testing ===")
        
        # Test safe command preview
        preview_data = {
            "source": "/tmp/test_source",
            "destination": "/tmp/test_destination",
            "rsync_args": {
                "archive": True,
                "verbose": True,
                "progress": True,
                "dry_run": True
            },
            "excludes": "*.tmp .DS_Store"
        }
        
        result = self.test_api_endpoint("POST", "/api/rsync/preview", preview_data)
        if result["success"]:
            command = result["data"].get("command", "")
            errors = result["data"].get("errors", [])
            self.log_test("Command Preview (Safe)", "PASS", f"Generated: {command[:50]}...")
            
            # Test dangerous command preview
            dangerous_data = preview_data.copy()
            dangerous_data["rsync_args"]["delete"] = True
            
            dangerous_result = self.test_api_endpoint("POST", "/api/rsync/preview", dangerous_data)
            if dangerous_result["success"]:
                dangerous_errors = dangerous_result["data"].get("errors", [])
                if any("delete" in error.lower() for error in dangerous_errors):
                    self.log_test("Command Preview (Dangerous)", "PASS", "Proper warnings for dangerous operations")
                else:
                    self.log_test("Command Preview (Dangerous)", "WARN", "Missing warnings for delete operation")
            else:
                self.log_test("Command Preview (Dangerous)", "FAIL", "Failed to preview dangerous command")
        else:
            self.log_test("Command Preview (Safe)", "FAIL", "Failed to generate command preview")
    
    def test_rclone_integration(self):
        """Test Phase 4: Rclone Integration"""
        print("\n=== Phase 4: Rclone Integration Testing ===")
        
        # Test rclone operations
        result = self.test_api_endpoint("GET", "/api/rclone/operations")
        if result["success"]:
            operations = result["data"].get("operations", [])
            self.log_test("Rclone Operations", "PASS", f"Found {len(operations)} rclone operations")
            
            # Analyze operation statuses
            status_counts = {}
            for op in operations:
                status = op.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
            
            self.log_test("Rclone Status Analysis", "PASS", f"Statuses: {status_counts}")
        else:
            self.log_test("Rclone Operations", "FAIL", "Failed to fetch rclone operations")
        
        # Test rclone backends
        backends_result = self.test_api_endpoint("GET", "/api/rclone/backends")
        if backends_result["success"]:
            backends = backends_result["data"].get("backends", [])
            self.log_test("Rclone Backends", "PASS", f"Supported backends: {len(backends)}")
        else:
            self.log_test("Rclone Backends", "FAIL", "Failed to fetch rclone backends")
    
    def test_advanced_features(self):
        """Test Phase 3: Advanced Frontend Features"""
        print("\n=== Phase 3: Advanced Frontend Features Testing ===")
        
        # Test Server-Sent Events endpoint
        try:
            response = self.session.get(f"{self.base_url}/api/progress", stream=True, timeout=5)
            if response.status_code == 200:
                self.log_test("Server-Sent Events", "PASS", "Progress streaming endpoint available")
            else:
                self.log_test("Server-Sent Events", "FAIL", f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Server-Sent Events", "FAIL", f"Connection error: {str(e)}")

    def run_all_tests(self):
        """Run all test phases in sequence"""
        print(f"\n{'='*70}")
        print(f"Starting Comprehensive Test Suite for {self.base_url}")
        print(f"{'='*70}")

        # Run all test phases
        self.test_initial_setup()
        self.test_job_management()
        self.test_command_preview()
        self.test_rclone_integration()
        self.test_advanced_features()

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test results summary"""
        print(f"\n{'='*70}")
        print("TEST RESULTS SUMMARY")
        print(f"{'='*70}")

        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed_tests = sum(1 for r in self.test_results if r["status"] == "FAIL")
        warn_tests = sum(1 for r in self.test_results if r["status"] == "WARN")

        print(f"\nTotal Tests:  {total_tests}")
        print(f"Passed:       {passed_tests} ✅")
        print(f"Failed:       {failed_tests} ❌")
        print(f"Warnings:     {warn_tests} ⚠️")
        print(f"\nSuccess Rate: {(passed_tests/total_tests*100):.1f}%")

        if failed_tests > 0:
            print(f"\n{'='*70}")
            print("FAILED TESTS:")
            print(f"{'='*70}")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"❌ {result['test']}: {result['details']}")

        print(f"\n{'='*70}\n")

        return failed_tests == 0


def main():
    """Main entry point for test automation script"""
    parser = argparse.ArgumentParser(
        description="Comprehensive Test Automation for Flask Job Restart Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 test_automation.py
  python3 test_automation.py --url http://localhost:8080
  python3 test_automation.py --url http://192.168.1.100:8080
        """
    )

    parser.add_argument(
        '--url',
        type=str,
        default='http://localhost:8080',
        help='Base URL of the Flask application (default: http://localhost:8080)'
    )

    args = parser.parse_args()

    # Initialize tester
    tester = FrontendTester(base_url=args.url)

    try:
        # Run all tests
        tester.run_all_tests()

        # Determine exit code based on test results
        all_passed = tester.print_summary()

        # Exit with appropriate code
        sys.exit(0 if all_passed else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Testing interrupted by user")
        sys.exit(2)
    except requests.exceptions.ConnectionError:
        print(f"\n❌ ERROR: Cannot connect to {args.url}")
        print("   Make sure the Flask application is running.")
        sys.exit(3)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(4)


if __name__ == "__main__":
    main()
