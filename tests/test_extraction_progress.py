import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from vmforge.extraction import extract_archive


class ExtractionProgressTests(unittest.TestCase):
    def test_progress_messages_and_content(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / 'new'
            def fake_stream(command, target, expected, timeout=900, created_files=None):
                with target.open('xb') as handle:
                    created_files.append(target)
                    handle.write(b'abc')
            with patch('vmforge.extraction.inspect_archive', return_value=[('disk.vdi', 3, False)]), \
                 patch('vmforge.extraction.find_extractor', return_value=('7zip', 'fake')), \
                 patch('vmforge.extraction.stream_entry', side_effect=fake_stream), \
                 redirect_stdout(io.StringIO()) as output:
                extract_archive(root / 'image.7z', dest)
            self.assertEqual((dest / 'disk.vdi').read_bytes(), b'abc')
            log = output.getvalue()
            self.assertIn('Extraindo: disk.vdi', log)
            self.assertIn('Arquivo concluído: disk.vdi', log)
            self.assertIn('Extração concluída: 100%', log)

    def test_failure_does_not_claim_completion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / 'new'
            def fake_stream(command, target, expected, timeout=900, created_files=None):
                with target.open('xb') as handle:
                    created_files.append(target)
                    handle.write(b'x')
                raise RuntimeError('simulated failure')
            with patch('vmforge.extraction.inspect_archive', return_value=[('disk.vdi', 3, False)]), \
                 patch('vmforge.extraction.find_extractor', return_value=('7zip', 'fake')), \
                 patch('vmforge.extraction.stream_entry', side_effect=fake_stream), \
                 redirect_stdout(io.StringIO()) as output:
                with self.assertRaisesRegex(RuntimeError, 'simulated failure'):
                    extract_archive(root / 'image.7z', dest)
            self.assertFalse(dest.exists())
            self.assertNotIn('Extração concluída: 100%', output.getvalue())

    def test_preexisting_empty_destination_preserved_on_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / 'existing'
            dest.mkdir()
            def fake_stream(command, target, expected, timeout=900, created_files=None):
                with target.open('xb') as handle:
                    created_files.append(target)
                    handle.write(b'x')
                raise RuntimeError('simulated failure')
            with patch('vmforge.extraction.inspect_archive', return_value=[('disk.vdi', 3, False)]), \
                 patch('vmforge.extraction.find_extractor', return_value=('7zip', 'fake')), \
                 patch('vmforge.extraction.stream_entry', side_effect=fake_stream), \
                 redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    extract_archive(root / 'image.7z', dest)
            self.assertTrue(dest.is_dir())
            self.assertEqual(list(dest.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
