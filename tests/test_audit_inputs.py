import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import subprocess
import sys
import unittest
import zipfile
import zlib

from tools.audit_inputs import audit_zip
from tools import audit_inputs


class ZipAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, entries):
        path = self.root / 'input.zip'
        with zipfile.ZipFile(path, 'w') as z:
            for name, data in entries:
                if isinstance(name, str):
                    # ZipInfo normalizes backslashes on Windows. Preserve raw
                    # hostile fixture names so every OS tests the same bytes.
                    info = zipfile.ZipInfo(name)
                    info.filename = info.orig_filename = name
                    name = info
                z.writestr(name, data)
        return path

    def codes(self, report):
        return {d['code'] for d in report['diagnostics']}

    def test_reads_xml_without_extracting_or_claiming_game_success(self):
        path = self.archive([('Data/Core/Defs/a.xml', '<Defs><A /></Defs>')])
        before = path.read_bytes()
        report = audit_zip(path)
        self.assertEqual(report['auditStatus'], 'passed')
        self.assertEqual(report['gameVerification'], 'notRun')
        self.assertEqual(report['statistics']['xmlFilesChecked'], 1)
        self.assertEqual(report['statistics']['payloadFilesRead'], 1)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_invalid_xml_is_not_hidden_by_valid_zip_crc(self):
        report = audit_zip(self.archive([('a.xml', '<Defs><</Defs>')]))
        self.assertEqual(report['auditStatus'], 'failed')
        self.assertIn('xmlSyntax', self.codes(report))

    def test_utf16_doctype_is_rejected_before_entity_expansion(self):
        xml = '<!DOCTYPE a [<!ENTITY x "expanded">]><a>&x;</a>'
        report = audit_zip(self.archive([('a.xml', xml.encode('utf-16'))]))
        self.assertEqual(report['auditStatus'], 'failed')
        self.assertIn('xmlSyntax', self.codes(report))

    def test_rejects_traversal_absolute_drive_and_backslash_paths(self):
        for name in ['../outside', '/outside', 'C:/outside', 'a\\b']:
            with self.subTest(name=name):
                report = audit_zip(self.archive([(name, b'x')]))
                self.assertIn('unsafePath', self.codes(report))
                self.assertEqual(report['auditStatus'], 'failed')

    def test_case_and_unicode_collisions_are_errors(self):
        for names in [('A.xml', 'a.xml'), ('café.txt', 'cafe\u0301.txt')]:
            with self.subTest(names=names):
                report = audit_zip(self.archive([(n, b'x') for n in names]))
                self.assertIn('pathCollision', self.codes(report))

    def test_symlink_is_not_accepted_as_regular_file(self):
        link = zipfile.ZipInfo('Resources/link')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        report = audit_zip(self.archive([(link, '../outside')]))
        self.assertIn('link', self.codes(report))

    def test_crc_corruption_fails(self):
        path = self.archive([('plain.txt', b'original')])
        raw = bytearray(path.read_bytes())
        raw[30 + len('plain.txt')] ^= 1
        path.write_bytes(raw)
        report = audit_zip(path)
        self.assertEqual(report['auditStatus'], 'failed')
        self.assertIn('archiveRead', self.codes(report))

    def test_unsupported_compression_is_incomplete(self):
        path = self.archive([('plain.txt', b'original')])
        raw = bytearray(path.read_bytes())
        struct.pack_into('<H', raw, 8, 99)
        struct.pack_into('<H', raw, raw.index(b'PK\x01\x02') + 10, 99)
        path.write_bytes(raw)
        report = audit_zip(path)
        self.assertEqual(report['auditStatus'], 'incomplete')
        self.assertIn('unsupportedCompression', self.codes(report))

    def test_byte_and_entry_limits_do_not_pass_unread_input(self):
        for options in [{'max_entry_bytes': 3}, {'max_total_bytes': 3}, {'max_entries': 1}]:
            with self.subTest(options=options):
                report = audit_zip(self.archive([('a', b'1234'), ('b', b'x')]), **options)
                self.assertEqual(report['auditStatus'], 'incomplete')
                self.assertIn('limit', self.codes(report))

    def test_manifest_alias_coverage_does_not_require_synthesizing_files(self):
        h = hashlib.sha256(b'font').hexdigest()
        manifest = self.root / 'bake.manifest'
        manifest.write_text(f'Resources/Fonts/a.ttf {h}\nResources/Fonts/b.ttf {h}\nResources/Sounds/a.ogg {h}\n')
        report = audit_zip(self.archive([('Resources/Fonts/a.ttf', b'font')]), manifest=manifest, scopes=['Resources/Fonts/'])
        self.assertEqual(report['auditStatus'], 'passed')
        self.assertEqual(report['manifestComparison']['contentCoveredPaths'], 2)
        self.assertEqual(report['manifestComparison']['aliasCoveredPaths'], 1)
        self.assertEqual(report['gameVerification'], 'notRun')

    def test_manifest_mismatch_and_missing_contents_are_reported(self):
        manifest = self.root / 'bake.manifest'
        manifest.write_text('a ' + '0' * 64 + '\nb ' + '1' * 64 + '\n')
        report = audit_zip(self.archive([('a', b'modified')]), manifest=manifest)
        self.assertEqual(report['auditStatus'], 'failed')
        self.assertIn('hashMismatch', self.codes(report))
        self.assertIn('missingContent', self.codes(report))

    def test_nested_archives_are_not_claimed_as_inspected(self):
        report = audit_zip(self.archive([('Assets.zip', b'not inspected as zip')]))
        self.assertEqual(report['auditStatus'], 'passed')
        self.assertEqual(report['coverage']['nestedArchives'], 'notInspected')

    def test_unread_manifest_contents_are_incomplete_not_proven_missing(self):
        manifest = self.root / 'bake.manifest'
        manifest.write_text('a ' + '0' * 64 + '\n')
        report = audit_zip(self.archive([('a', b'large')]), manifest=manifest, max_entry_bytes=1)
        self.assertEqual(report['auditStatus'], 'incomplete')

    def test_empty_archive_does_not_pass_without_payload(self):
        self.assertEqual(audit_zip(self.archive([]))['auditStatus'], 'failed')

    def test_deflate_corruption_returns_diagnostic_instead_of_exception(self):
        path = self.root / 'broken.zip'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('a', b'a' * 100)
        raw = bytearray(path.read_bytes())
        raw[31] = 0xff
        path.write_bytes(raw)
        self.assertEqual(audit_zip(path)['auditStatus'], 'failed')

    def test_diagnostics_are_bounded(self):
        report = audit_zip(self.archive([(f'../{i}', b'x') for i in range(250)]))
        self.assertLessEqual(len(report['diagnostics']), 200)
        self.assertGreater(report['omittedDiagnostics'], 0)
        self.assertEqual(report['auditStatus'], 'failed')

    def test_unknown_xml_encoding_produces_json_instead_of_crashing(self):
        report = audit_zip(self.archive([('a.xml', '<?xml version="1.0" encoding="madeup"?><a/>')]))
        self.assertEqual(report['auditStatus'], 'failed')
        self.assertIn('xmlSyntax', self.codes(report))

    def test_nul_in_original_zip_filename_is_rejected(self):
        p = self.archive([('abcde', b'x')])
        p.write_bytes(p.read_bytes().replace(b'abcde', b'a\x00cde'))
        self.assertEqual(audit_zip(p)['auditStatus'], 'failed')

    def test_noncanonical_paths_and_parent_file_conflicts_are_rejected(self):
        for names in [('a/b', 'a//b'), ('a/b', 'a/./b'), ('a', 'a/b'), ('a/b', 'a')]:
            with self.subTest(names=names):
                report = audit_zip(self.archive([(n, b'x') for n in names]))
                self.assertEqual(report['auditStatus'], 'failed')

    def test_declared_size_cannot_hide_extra_decompressed_bytes(self):
        p = self.root / 'lying.zip'
        with zipfile.ZipFile(p, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('a', b'abcdef')
        raw = bytearray(p.read_bytes());central = raw.index(b'PK\x01\x02')
        for offset in (14, central + 16):
            struct.pack_into('<I', raw, offset, zlib.crc32(b'a'))
        for offset in (22, central + 24):
            struct.pack_into('<I', raw, offset, 1)
        p.write_bytes(raw)
        report = audit_zip(p)
        self.assertEqual(report['auditStatus'], 'failed')
        self.assertNotEqual(report['coverage']['zipEntryCrc'], 'all')

    def test_lzma_is_explicitly_unsupported_even_when_corrupt(self):
        p = self.root / 'lzma.zip'
        with zipfile.ZipFile(p, 'w', compression=zipfile.ZIP_LZMA) as z:
            z.writestr('a', b'a' * 100)
        raw = bytearray(p.read_bytes());raw[40:45] = b'\xff' * 5;p.write_bytes(raw)
        report = audit_zip(p)
        self.assertEqual(report['auditStatus'], 'incomplete')
        self.assertNotEqual(report['coverage']['zipEntryCrc'], 'all')


class MetadataAndCliTests(unittest.TestCase):
    setUp = ZipAuditTests.setUp
    archive = ZipAuditTests.archive
    def metadata(self, manifest, textures):
        m, t = self.root / 'bake.manifest', self.root / 'textures.info'
        m.write_text(manifest)
        t.write_text(textures)
        return m, t

    def test_metadata_agreement_accepts_spaces_in_paths(self):
        m, t = self.metadata('Resources/Textures/a b.dds ' + '1' * 64 + '\n',
                             'Resources/Textures/a b.dds 1 2 3 4 0 0\n')
        report = audit_inputs.audit_metadata(m, t)
        self.assertEqual(report['auditStatus'], 'passed')
        self.assertEqual(report['statistics']['textureEntries'], 1)
        self.assertEqual(report['gameVerification'], 'notRun')

    def test_bad_manifest_rows_duplicates_empty_and_unsafe_are_errors(self):
        for manifest in ['broken', '', 'a ' + '1' * 64 + '\na ' + '1' * 64,
                         '../a ' + '1' * 64]:
            with self.subTest(manifest=manifest):
                m, t = self.metadata(manifest, '')
                self.assertEqual(audit_inputs.audit_metadata(m, t)['auditStatus'], 'failed')

    def test_bad_texture_rows_duplicates_and_missing_paths_are_errors(self):
        for textures in ['broken', 'Resources/Textures/a 1 1 1 1 0 0\n' * 2,
                         'Resources/Textures/b 1 1 1 1 0 0', '']:
            with self.subTest(textures=textures):
                m, t = self.metadata('Resources/Textures/a ' + '1' * 64, textures)
                self.assertEqual(audit_inputs.audit_metadata(m, t)['auditStatus'], 'failed')

    def test_oversized_metadata_does_not_get_parsed(self):
        m, t = self.metadata('x' * (16 * 1024 * 1024 + 1), '')
        self.assertEqual(audit_inputs.audit_metadata(m, t)['auditStatus'], 'failed')

    def cli(self, *args):
        return subprocess.run([sys.executable, 'tools/audit_inputs.py', *map(str, args)],
                              capture_output=True, text=True, check=False)

    def test_cli_writes_json_and_uses_status_exit_codes(self):
        for xml, code, status in [('<a/>', 0, 'passed'), ('<a>', 1, 'failed')]:
            p = self.archive([('a.xml', xml)])
            out = self.cli('zip', p)
            self.assertEqual(out.returncode, code, out.stderr)
            self.assertEqual(json.loads(out.stdout)['auditStatus'], status)
        out = self.cli('zip', p, '--max-entry-mib', '0')
        self.assertNotEqual(out.returncode, 0)

    def test_cli_incomplete_and_missing_input_are_machine_readable(self):
        p = self.archive([('a', b'x' * (1024 * 1024 + 1))])
        out = self.cli('zip', p, '--max-entry-mib', '1')
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertEqual(json.loads(out.stdout)['auditStatus'], 'incomplete')
        out = self.cli('zip', self.root / 'missing.zip')
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertEqual(json.loads(out.stdout)['gameVerification'], 'notRun')

    def test_cli_refuses_output_aliases_of_inputs(self):
        p = self.archive([('a', b'content')]);before = p.read_bytes()
        for alias in [p, self.root / 'link.zip']:
            if alias != p:
                os.link(p, alias)
            out = self.cli('zip', p, '--output', alias)
            self.assertEqual(out.returncode, 1, out.stderr)
            self.assertEqual(p.read_bytes(), before)
            self.assertEqual(json.loads(out.stdout)['auditStatus'], 'failed')

    def test_cli_output_file_and_metadata_subcommand(self):
        m, t = self.metadata('Resources/Textures/a ' + '1' * 64,
                             'Resources/Textures/a 1 1 1 1 0 0')
        output = self.root / 'report.json'
        out = self.cli('metadata', m, t, '--output', output)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(output.read_text())['auditStatus'], 'passed')

    def test_output_does_not_overwrite_manifest(self):
        m, _ = self.metadata('a ' + '1' * 64, '')
        before = m.read_bytes()
        out = self.cli('zip', self.archive([('a', b'x')]), '--manifest', m, '--output', m)
        self.assertEqual(out.returncode, 1)
        self.assertEqual(m.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
