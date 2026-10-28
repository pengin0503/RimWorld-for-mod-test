"""Clients are closed before orchestration returns or propagates an error."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_codex_workflow import sample_index
from tools import codex_workflow as cw


class LifetimeTests(unittest.TestCase):
    def test_prepare_closes_client_after_failed_listing(self):
        class Client:
            closed = False
            def list_prefix(self, prefix):
                raise cw.r2_assets.AssetError('synthetic')
            def close(self):
                self.closed = True
        client = Client()
        with tempfile.TemporaryDirectory() as directory, patch.object(cw, 'r2_client', return_value=client):
            with self.assertRaises(cw.r2_assets.AssetError):
                cw.prepare(SimpleNamespace(private_root=Path(directory), aws='aws', refresh=False))
        self.assertTrue(client.closed)

    def test_index_closes_client_after_failed_download(self):
        class Client:
            closed = False
            def get(self, *args, **kwargs):
                raise cw.r2_assets.AssetError('synthetic')
            def close(self):
                self.closed = True
        client = Client()
        with tempfile.TemporaryDirectory() as directory, patch.object(cw, 'r2_client', return_value=client):
            with self.assertRaises(cw.r2_assets.AssetError):
                cw.private_index(SimpleNamespace(index_zip=None, aws='aws', refresh=False), Path(directory))
        self.assertTrue(client.closed)

    def test_mod_client_closes_on_success_and_metadata_error(self):
        for valid in (True, False):
            with self.subTest(valid=valid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                sample_index(root / 'index.zip')
                payload = (b'<ModMetaData><packageId>author.example</packageId></ModMetaData>'
                           if valid else b'<broken')
                class Client:
                    closed = False
                    def list_prefix(self, prefix):
                        return [{'key': prefix + 'About/About.xml', 'size': len(payload)}]
                    def get(self, key, dest, size, **kwargs):
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(payload)
                        return 'downloaded'
                    def close(self):
                        self.closed = True
                client = Client()
                args = SimpleNamespace(private_root=root / 'private', index_zip=root / 'index.zip',
                    aws='aws', target='Example', local_target=None, dependency=[],
                    official=['Core'], language='English', scope='validation', refresh=False)
                with patch.object(cw, 'r2_client', return_value=client):
                    if valid:
                        self.assertEqual(cw.fetch_mods(args)['status'], 'modsReady')
                    else:
                        with self.assertRaises(cw.WorkflowError):
                            cw.fetch_mods(args)
                self.assertTrue(client.closed)
