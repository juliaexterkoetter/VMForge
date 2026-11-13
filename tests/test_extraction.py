import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

from vmforge.extraction import (safe_path, parse_manifest, inspect_archive,
    find_extractor, sevenzip_path, extract_archive, stream_entry)


def manifest(name='pasta/kali.vdi', size=3, extra=''):
    return f'Type = 7z\n\n----------\nPath = {name}\nSize = {size}\nAttributes = A\n{extra}'


class PathTests(unittest.TestCase):
    def test_reject_unsafe_names(self):
        for name in ('../a', '/a', 'C:/a', 'C:a', '//host/share', '\\\\host\\share',
                     'a/../../b', 'a\\..\\..\\b', 'a//b', './a', 'a:stream', 'a\nb',
                     'CON.vdi', 'a./b', 'a /b', 'a?.vdi'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_path(name)

    def test_unicode_and_spaces(self):
        self.assertEqual(safe_path('máquina nova/disco.vdi'), 'máquina nova/disco.vdi')

    def test_manifest(self):
        self.assertEqual(parse_manifest(manifest()), [('pasta/kali.vdi', 3, False)])

    def test_invalid_manifest(self):
        for text in ('', manifest('../a.vdi'), manifest(size=-1), manifest(size=129*1024**3),
                     manifest(extra='Symbolic Link = /tmp\n'), manifest(extra='Encrypted = +\n'),
                     manifest('program.exe'), manifest(extra='Path = other.vdi\n'),
                     manifest().replace('Type = 7z', 'Type = zip'),
                     manifest() + '\nPath = pasta/kali.vdi\nSize = 3\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_manifest(text)

    def test_file_parent_conflict(self):
        with self.assertRaises(ValueError):
            parse_manifest(manifest('a.vdi') + '\nPath = a.vdi/b.vdi\nSize = 1\n')

    def test_signature_rejected_before_subprocess(self):
        with tempfile.TemporaryDirectory() as td:
            image = Path(td)/'image.7z'
            image.write_bytes(b'not 7z')
            with patch('vmforge.extraction.subprocess.run') as run:
                with self.assertRaises(ValueError):
                    inspect_archive(image)
                run.assert_not_called()

    def test_manifest_process_failure_and_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            image = Path(td)/'image.7z'
            image.write_bytes(b'7z\xbc\xaf\x27\x1c')
            with patch('vmforge.extraction.sevenzip_path', return_value='7z'):
                with patch('vmforge.extraction.subprocess.run', return_value=Mock(returncode=2)):
                    with self.assertRaises(ValueError):
                        inspect_archive(image)
                with patch('vmforge.extraction.subprocess.run', side_effect=subprocess.TimeoutExpired('7z', 60)):
                    with self.assertRaisesRegex(RuntimeError, 'timeout'):
                        inspect_archive(image)


class DetectionTests(unittest.TestCase):
    def test_missing_tools(self):
        with patch('vmforge.extraction.shutil.which', return_value=None), patch('pathlib.Path.is_file', return_value=False):
            with self.assertRaises(RuntimeError):
                sevenzip_path()

    def test_sevenzip_verified(self):
        with patch('vmforge.extraction.shutil.which', return_value='/fake/7z'), patch('pathlib.Path.is_file', return_value=True), patch('vmforge.extraction.subprocess.run', return_value=Mock(returncode=0, stdout='7z')):
            self.assertTrue(sevenzip_path())

    @unittest.skipUnless(os.name == 'nt', 'Windows')
    def test_native_tar_preferred(self):
        with patch('pathlib.Path.is_file', return_value=True), patch('vmforge.extraction.subprocess.run', return_value=Mock(returncode=0, stdout='bsdtar')), patch('vmforge.extraction.shutil.which', return_value=r'C:\Program Files\Git\usr\bin\tar.exe'):
            kind, path = find_extractor()
            self.assertEqual(kind, 'tar')
            self.assertIn('system32', path.lower())

    def test_bad_executable_rejected(self):
        with patch('pathlib.Path.is_file', return_value=True), patch('vmforge.extraction.subprocess.run', return_value=Mock(returncode=0, stdout='unknown')):
            with self.assertRaises(RuntimeError):
                sevenzip_path()


class StreamTests(unittest.TestCase):
    def test_stream_limit(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, 'excedeu'):
                stream_entry([sys.executable, '-c', "print('too much')"], Path(td)/'out', 1)

    def test_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, 'incompleta'):
                stream_entry([sys.executable, '-c', 'pass'], Path(td)/'out', 10)

    def test_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(subprocess.TimeoutExpired):
                stream_entry([sys.executable, '-c', 'import time; time.sleep(10)'], Path(td)/'out', 0, timeout=.1)

    def test_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)/'out'
            out.write_bytes(b'preserve')
            with self.assertRaises(FileExistsError):
                stream_entry(['unused'], out, 0)
            self.assertEqual(out.read_bytes(), b'preserve')

    def test_failure_cleans_new_destination(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td)/'new'
            with patch('vmforge.extraction.inspect_archive', return_value=[('kali.vdi', 3, False)]), patch('vmforge.extraction.find_extractor', return_value=('7zip', 'fake')), patch('vmforge.extraction.stream_entry', side_effect=RuntimeError('failed')):
                with self.assertRaises(RuntimeError):
                    extract_archive(Path(td)/'image.7z', dest)
                self.assertFalse(dest.exists())

    def test_insufficient_space(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td)/'new'
            with patch('vmforge.extraction.inspect_archive', return_value=[('kali.vdi', 3, False)]), patch('vmforge.extraction.find_extractor', return_value=('7zip', 'fake')), patch('vmforge.extraction.shutil.disk_usage', return_value=Mock(free=0)):
                with self.assertRaisesRegex(ValueError, 'Espaço'):
                    extract_archive(Path(td)/'image.7z', dest)
                self.assertFalse(dest.exists())


class ArchiveIntegrationTests(unittest.TestCase):
    def test_small_archive_both_extractors_preserve_source(self):
        try:
            binary = sevenzip_path()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        with tempfile.TemporaryDirectory(prefix='vmforge teste ') as td:
            root = Path(td)
            source = root/'máquina nova'
            source.mkdir()
            (source/'kali.vbox').write_bytes(b'<VirtualBox/>')
            (source/'kali.vdi').write_bytes(b'disposable fixture')
            archive = root/'imagem original.7z'
            subprocess.run([binary, 'a', '-t7z', str(archive), str(source)], check=True, capture_output=True)
            digest = hashlib.sha256(archive.read_bytes()).digest()
            extractors = [('7zip', binary)]
            native = find_extractor()
            if native[0] == 'tar':
                extractors.append(native)
            for index, extractor in enumerate(extractors):
                dest = root/f'dest {index}'
                with self.subTest(extractor=extractor[0]), patch('vmforge.extraction.find_extractor', return_value=extractor):
                    extract_archive(archive, dest)
                    self.assertEqual((dest/source.name/'kali.vdi').read_bytes(), b'disposable fixture')
                    with self.assertRaises(ValueError):
                        extract_archive(archive, dest)
                self.assertEqual(hashlib.sha256(archive.read_bytes()).digest(), digest)
