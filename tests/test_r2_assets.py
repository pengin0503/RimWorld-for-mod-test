"""Synthetic-only R2 selection and CLI tests; never call real S3."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import r2_assets as ra


class AssetTests(unittest.TestCase):
    def test_key_scope_blocks_traversal(self):
        for key in ('Workshop/../evil', 'Workshop/abc/About/About.xml',
                    'Game-Linux/../../secret', '/Game-Linux/x',
                    'Game-Linux//x', 'Game-Linux/\\file', 'Data/Core/About/About.xml'):
            with self.subTest(key=key), self.assertRaises(ra.AssetError):
                ra.validate_key(key)
        self.assertEqual(ra.validate_key('Workshop/123/1.7/Defs/A.xml'), 'Workshop/123/1.7/Defs/A.xml')

    def test_scopes_limit_mod_reads(self):
        items = [{'key': 'Workshop/123/About/About.xml', 'size': 1},
                 {'key': 'Workshop/123/About/Preview.png', 'size': 2},
                 {'key': 'Workshop/123/1.7/Defs/Test.xml', 'size': 3},
                 {'key': 'Workshop/123/1.7/Assemblies/A.dll', 'size': 4}]
        self.assertEqual(len(ra.selection('about', items)), 1)
        self.assertEqual(len(ra.selection('xml', items)), 2)
        self.assertEqual(len(ra.selection('all', items)), 4)

    def test_listing_is_prefix_bounded_and_paginated(self):
        r2 = ra.R2(endpoint='https://abc.r2.cloudflarestorage.com', bucket='rimworld-17')
        responses = iter([{'Contents': [{'Key': 'Workshop/123/About/About.xml', 'Size': 3}],
                           'NextContinuationToken': 'tok'},
                          {'Contents': [{'Key': 'Workshop/123/1.7/Defs/a.xml', 'Size': 7}]}])
        with patch.object(r2, 'call', side_effect=lambda *args: next(responses)) as mocked:
            result = r2.list_prefix('Workshop/123/')
        self.assertEqual(len(result), 2)
        self.assertIn('--continuation-token', mocked.call_args.args)
        self.assertEqual(mocked.call_args.args[-1], 'tok')

    def test_listing_cannot_escape_prefix(self):
        r2 = ra.R2(endpoint='https://abc.r2.cloudflarestorage.com', bucket='rimworld-17')
        with patch.object(r2, 'call', return_value={'Contents': [{'Key': 'Workshop/999/A.xml', 'Size': 3}]}):
            with self.assertRaises(ra.AssetError):
                r2.list_prefix('Workshop/123/')

    def test_dry_run_only_lists(self):
        args = type('Args', (), dict(endpoint='https://abc.r2.cloudflarestorage.com', bucket='rimworld-17',
                                    aws='aws', action='mod', workshop_id='123', scope='about',
                                    key=None, dest='/tmp/private', dry_run=True, refresh=False))()
        with patch.object(ra.R2, 'list_prefix', return_value=[{'key': 'Workshop/123/About/About.xml', 'size': 12}]), \
             patch.object(ra.R2, 'get') as get:
            result = ra.run(args)
        self.assertEqual(result['count'], 1)
        get.assert_not_called()

    def test_endpoint_rejects_foreign_host_and_userinfo(self):
        for endpoint in ("https://example.com/abc.r2.cloudflarestorage.com",
                         "https://user:pass@abc.r2.cloudflarestorage.com",
                         "http://abc.r2.cloudflarestorage.com"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ra.AssetError):
                ra.R2(endpoint=endpoint, bucket="rimworld-17")

    def test_no_symlink_destination(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / 'alias').symlink_to(base, target_is_directory=True)
            with self.assertRaises(ra.AssetError):
                ra.ensure_safe_destination(base / 'alias', 'x.xml')

    def test_get_checks_length_and_cleans_partial(self):
        r2 = ra.R2(endpoint='https://abc.r2.cloudflarestorage.com', bucket='rimworld-17')
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'About.xml'
            with patch.object(r2, 'call', return_value={'ContentLength': 8}):
                with self.assertRaises(ra.AssetError):
                    r2.get('Workshop/123/About/About.xml', target, 8)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(d).glob('.r2-*')), [])


    def test_profile_is_unset_only_in_aws_child(self):
        r2 = ra.R2(endpoint='https://abc.r2.cloudflarestorage.com', bucket='rimworld-17')
        with patch.dict('os.environ', {'AWS_PROFILE': 'nonexistent', 'AWS_DEFAULT_PROFILE': 'missing',
                                      'AWS_ACCESS_KEY_ID': 'test-id', 'AWS_SECRET_ACCESS_KEY': 'test-secret'}), \
             patch.object(ra.subprocess, 'run') as call:
            call.return_value.returncode = 0
            call.return_value.stdout = '{}'
            r2.call('head-object', '--bucket', 'rimworld-17', '--key', 'Game-Linux/Version.txt')
            child = call.call_args.kwargs['env']
            self.assertNotIn('AWS_PROFILE', child)
            self.assertNotIn('AWS_DEFAULT_PROFILE', child)
            self.assertEqual(child['AWS_ACCESS_KEY_ID'], 'test-id')

    def test_private_index_allows_only_one_exact_object(self):
        self.assertEqual(ra.validate_key(ra.PRIVATE_INDEX_KEY), ra.PRIVATE_INDEX_KEY)
        for key in ('PrivateIndex/other.zip', 'PrivateIndex/../outside',
                    'PrivateIndex/rimworld-mod-index-2026-10-26.zip/another'):
            with self.subTest(key=key), self.assertRaises(ra.AssetError):
                ra.validate_key(key)


if __name__ == '__main__':
    unittest.main()
