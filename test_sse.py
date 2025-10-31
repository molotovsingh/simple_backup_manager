#!/usr/bin/env python3
"""
Test SSE (Server-Sent Events) implementation
Ensures correct content type, headers, and heartbeat behavior
"""

import unittest
import threading
import time
from io import BytesIO
from app import app
from job_storage import JobStorage
from job_executor import JobExecutor


class TestSSE(unittest.TestCase):
    """Test SSE endpoint for correct implementation"""

    def setUp(self):
        """Set up test client"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_sse_content_type(self):
        """Test that SSE endpoint returns correct content type"""
        # Start SSE stream in thread (it's an infinite loop)
        response_data = {}

        def get_sse():
            with self.client.get('/api/progress', stream=True) as response:
                response_data['status'] = response.status_code
                response_data['content_type'] = response.content_type
                response_data['headers'] = dict(response.headers)
                # Read just first chunk to validate
                response_data['first_chunk'] = next(response.iter_encoded(), None)

        thread = threading.Thread(target=get_sse)
        thread.daemon = True
        thread.start()
        thread.join(timeout=3)

        # Verify response
        self.assertEqual(response_data.get('status'), 200, "SSE endpoint should return 200")
        self.assertEqual(
            response_data.get('content_type'),
            'text/event-stream',
            "SSE must use text/event-stream content type"
        )

    def test_sse_cache_control_header(self):
        """Test that SSE endpoint has no-cache header"""
        response_data = {}

        def get_sse():
            with self.client.get('/api/progress', stream=True) as response:
                response_data['headers'] = dict(response.headers)

        thread = threading.Thread(target=get_sse)
        thread.daemon = True
        thread.start()
        thread.join(timeout=3)

        headers = response_data.get('headers', {})
        self.assertIn('Cache-Control', headers, "SSE must have Cache-Control header")
        self.assertIn('no-cache', headers['Cache-Control'].lower(),
                     "SSE Cache-Control must include no-cache")

    def test_sse_heartbeat_when_no_data(self):
        """Test that SSE sends heartbeat when there's no progress data"""
        chunks = []

        def get_sse():
            with self.client.get('/api/progress', stream=True) as response:
                # Collect first few chunks (should include heartbeats)
                for i, chunk in enumerate(response.iter_encoded()):
                    if i < 5:  # Get first 5 chunks
                        chunks.append(chunk.decode('utf-8') if isinstance(chunk, bytes) else chunk)
                    else:
                        break

        thread = threading.Thread(target=get_sse)
        thread.daemon = True
        thread.start()
        thread.join(timeout=12)  # Wait enough for several 2-second intervals

        # Should have received some heartbeats (": " lines)
        heartbeats = [chunk for chunk in chunks if chunk.strip().startswith(':')]
        self.assertGreater(len(heartbeats), 0,
                          "SSE should send heartbeat comments when no data available")

    def test_sse_data_format(self):
        """Test that SSE data is correctly formatted"""
        chunks = []

        def get_sse():
            with self.client.get('/api/progress', stream=True) as response:
                for i, chunk in enumerate(response.iter_encoded()):
                    if i < 3:
                        chunks.append(chunk.decode('utf-8') if isinstance(chunk, bytes) else chunk)
                    else:
                        break

        thread = threading.Thread(target=get_sse)
        thread.daemon = True
        thread.start()
        thread.join(timeout=8)

        # Check that chunks follow SSE format
        for chunk in chunks:
            if chunk.strip():
                # Should either be a heartbeat (starts with :) or data (starts with data:)
                self.assertTrue(
                    chunk.strip().startswith(':') or chunk.strip().startswith('data:'),
                    f"SSE chunk should start with ':' or 'data:', got: {chunk[:50]}"
                )


class TestSSEIntegration(unittest.TestCase):
    """Integration tests for SSE with real job execution"""

    def setUp(self):
        """Set up test environment"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.storage = JobStorage()

    def test_sse_broadcasts_job_progress(self):
        """Test that SSE correctly broadcasts job progress updates"""
        # This is a more complex integration test that would require
        # starting a real job and monitoring the SSE stream
        # Placeholder for future implementation
        pass


def run_tests():
    """Run all SSE tests"""
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
