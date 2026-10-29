"""Real SDK parsing/stream handling with stubbed S3 responses, no network."""
import inspect
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from botocore.response import StreamingBody
    from botocore.stub import Stubber
    HAS_SDK = True
except ImportError:
    HAS_SDK = False
from tools import r2_assets as ra

ENDPOINT = 'https://example.r2.cloudflarestorage.com'
BUCKET = 'rimworld-17'
KEY = 'Game-Linux/Version.txt'


@unittest.skipUnless(HAS_SDK, 'optional SDK is not installed')
class SDKTests(unittest.TestCase):
    def setUp(self):
        self.assertIn('transport', inspect.signature(ra.R2).parameters,
                      'explicit SDK transport is missing')
        env = patch.dict(os.environ, {'AWS_ACCESS_KEY_ID': 'synthetic-id',
            'AWS_SECRET_ACCESS_KEY': 'synthetic-secret', 'AWS_PROFILE': 'nonexistent',
            'AWS_DEFAULT_PROFILE': 'nonexistent', 'AWS_CONFIG_FILE': '/nonexistent-config',
            'AWS_SHARED_CREDENTIALS_FILE': '/nonexistent-credentials'})
        env.start()
        self.addCleanup(env.stop)
        self.r2 = ra.R2(endpoint=ENDPOINT, bucket=BUCKET, transport='sdk')
        self.addCleanup(self.r2.close)
        self.stub = Stubber(self.r2._sdk.client)
        self.stub.activate()
        self.addCleanup(self.stub.deactivate)

    def response(self, payload, length=None):
        stream = io.BytesIO(payload)
        body = StreamingBody(stream, len(payload) if length is None else length)
        self.stub.add_response('get_object', {'Body': body,
            'ContentLength': len(payload) if length is None else length},
            {'Bucket': BUCKET, 'Key': KEY})
        return stream

    def test_get_is_atomic_cached_and_does_not_launch_cli(self):
        stream = self.response(b'new')
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(ra.subprocess, 'run', side_effect=AssertionError('CLI launched')):
            dest = Path(directory) / 'Version.txt'
            dest.write_bytes(b'old')
            self.assertEqual(self.r2.get(KEY, dest, 3, refresh=True), 'downloaded')
            self.assertEqual(dest.read_bytes(), b'new')
            self.assertEqual(self.r2.get(KEY, dest, 3), 'cached')
            self.assertEqual(list(Path(directory).glob('.r2-*')), [])
            if os.name != 'nt':
                self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
        self.assertTrue(stream.closed)
        self.stub.assert_no_pending_responses()
        self.assertEqual(os.environ['AWS_PROFILE'], 'nonexistent')

    def test_truncated_stream_preserves_cache_and_closes_body(self):
        stream = self.response(b'new', length=5)
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'Version.txt'
            dest.write_bytes(b'old')
            with self.assertRaises(ra.AssetError) as caught:
                self.r2.get(KEY, dest, 5, refresh=True)
            self.assertNotIn('example.r2', str(caught.exception))
            self.assertEqual(dest.read_bytes(), b'old')
            self.assertEqual(list(Path(directory).glob('.r2-*')), [])
        self.assertTrue(stream.closed)

    def test_expected_size_mismatch_closes_body_and_removes_partial(self):
        stream = self.response(b'new')
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'Version.txt'
            with self.assertRaises(ra.AssetError):
                self.r2.get(KEY, dest, 4)
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertTrue(stream.closed)

    def test_sdk_error_does_not_expose_service_message(self):
        self.stub.add_client_error('get_object', service_error_code='AccessDenied',
            service_message='PRIVATE', expected_params={'Bucket': BUCKET, 'Key': KEY})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ra.AssetError) as caught:
                self.r2.get(KEY, Path(directory) / 'Version.txt', 3)
            self.assertNotIn('PRIVATE', str(caught.exception))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_large_body_is_read_in_bounded_chunks(self):
        class BoundedStream(io.BytesIO):
            def read(self, amount=-1):
                if not 0 < amount <= 1024 * 1024:
                    raise AssertionError('unbounded read')
                return super().read(amount)
        payload = b'x' * (1024 * 1024 + 17)
        stream = BoundedStream(payload)
        self.stub.add_response('get_object', {'Body': StreamingBody(stream, len(payload)),
            'ContentLength': len(payload)}, {'Bucket': BUCKET, 'Key': KEY})
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'Version.txt'
            self.r2.get(KEY, dest, len(payload))
            self.assertEqual(dest.read_bytes(), payload)
        self.assertTrue(stream.closed)

    def test_oversized_response_is_rejected_before_body_read(self):
        class Tracking(io.BytesIO):
            def __init__(self, payload): super().__init__(payload); self.reads = 0
            def read(self, size=-1): self.reads += 1; return super().read(size)
        stream = Tracking(b'1234')
        self.stub.add_response('get_object', {'Body': StreamingBody(stream, 4), 'ContentLength': 4}, {'Bucket': BUCKET, 'Key': KEY})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ra.AssetError): self.r2.get(KEY, Path(directory) / 'Version.txt', 3)
            self.assertEqual(stream.reads, 0)
            self.assertTrue(stream.closed)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_misreported_content_length_reads_at_most_one_extra_byte(self):
        class Tracking(io.BytesIO):
            def __init__(self, payload): super().__init__(payload); self.total = 0
            def read(self, size=-1):
                data = super().read(size); self.total += len(data); return data
        stream = Tracking(b'1234567890')
        self.stub.add_response('get_object', {'Body': StreamingBody(stream, 10), 'ContentLength': 3}, {'Bucket': BUCKET, 'Key': KEY})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ra.AssetError): self.r2.get(KEY, Path(directory) / 'Version.txt', 3)
            self.assertLessEqual(stream.total, 4)
            self.assertTrue(stream.closed)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_static_audit_exact_key_uses_sdk_prefix_without_enumerating_game(self):
        self.stub.add_response('list_objects_v2', {'Contents': [{'Key': KEY, 'Size': 3}, {'Key': KEY + '.extra', 'Size': 4}]},
            {'Bucket': BUCKET, 'Prefix': KEY, 'MaxKeys': 1000})
        self.assertEqual(self.r2.list_static_audit_key(KEY), [{'key': KEY, 'size': 3}])
        self.stub.assert_no_pending_responses()

    def test_prefix_pagination_and_escape_guard_are_shared(self):
        prefix = 'Game-Linux/'
        self.stub.add_response('list_objects_v2', {'Contents': [{'Key': KEY, 'Size': 3}],
            'NextContinuationToken': 'next'}, {'Bucket': BUCKET, 'Prefix': prefix, 'MaxKeys': 1000})
        self.stub.add_response('list_objects_v2', {'Contents': [{'Key': 'Workshop/123/x', 'Size': 3}]},
            {'Bucket': BUCKET, 'Prefix': prefix, 'MaxKeys': 1000, 'ContinuationToken': 'next'})
        with self.assertRaises(ra.AssetError):
            self.r2.list_prefix(prefix)
        self.stub.assert_no_pending_responses()
        with self.assertRaises(ra.AssetError):
            self.r2.list_prefix('')

    def test_missing_explicit_keys_and_bad_transport_fail_closed(self):
        with patch.dict(os.environ, {'AWS_ACCESS_KEY_ID': '', 'AWS_SECRET_ACCESS_KEY': ''}):
            with self.assertRaises(ra.AssetError):
                ra.R2(endpoint=ENDPOINT, bucket=BUCKET, transport='sdk')
        with self.assertRaises(ra.AssetError):
            ra.R2(endpoint=ENDPOINT, bucket=BUCKET, transport='invalid')

    def test_context_closes_sdk_even_on_exception(self):
        with patch.object(self.r2._sdk.client, 'close') as close:
            with self.assertRaises(ValueError):
                with self.r2:
                    raise ValueError('synthetic')
            close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
