import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vmforge.config import Settings, validate
from vmforge.extraction import extract_archive, validate_destination


class ExistingEmptyDestinationTests(unittest.TestCase):
    def test_empty_existing_directory_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / 'image.7z'
            image.touch()
            dest = root / 'empty'
            dest.mkdir()
            validate(Settings(image, dest))
            self.assertTrue(dest.is_dir())
            self.assertEqual(list(dest.iterdir()), [])

    def test_nonempty_directory_rejected_and_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / 'image.7z'
            image.touch()
            dest = root / 'existing'
            dest.mkdir()
            original = dest / '.hidden'
            original.write_text('preserve', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'não está vazia'):
                validate(Settings(image, dest))
            self.assertEqual(original.read_text(encoding='utf-8'), 'preserve')

    def test_existing_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'file'
            file.write_text('preserve')
            with self.assertRaises(ValueError):
                validate_destination(file)
            self.assertEqual(file.read_text(), 'preserve')

    def test_symlink_directory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'real'
            target.mkdir()
            link = root / 'linked'
            try:
                link.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(str(exc))
            with self.assertRaises(ValueError):
                validate_destination(link)

    def test_extract_into_empty_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / 'existing-empty'
            dest.mkdir()
            def fake_stream(command, target, expected, timeout=900, created_files=None):
                with target.open('xb') as file:
                    if created_files is not None:
                        created_files.append(target)
                    file.write(b'abc')
            with patch('vmforge.extraction.inspect_archive', return_value=[('nested/disk.vdi', 3, False)]), \
                 patch('vmforge.extraction.find_extractor', return_value=('7zip', 'fake')), \
                 patch('vmforge.extraction.stream_entry', side_effect=fake_stream):
                extract_archive(root / 'image.7z', dest)
            self.assertEqual((dest / 'nested' / 'disk.vdi').read_bytes(), b'abc')

    def test_failed_extraction_preserves_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / 'existing-empty'
            dest.mkdir()
            def failing_stream(command, target, expected, timeout=900, created_files=None):
                with target.open('xb') as file:
                    created_files.append(target)
                    file.write(b'partial')
                raise RuntimeError('simulated failure')
            with patch('vmforge.extraction.inspect_archive', return_value=[('nested/disk.vdi', 3, False)]), \
                 patch('vmforge.extraction.find_extractor', return_value=('7zip', 'fake')), \
                 patch('vmforge.extraction.stream_entry', side_effect=failing_stream):
                with self.assertRaisesRegex(RuntimeError, 'simulated failure'):
                    extract_archive(root / 'image.7z', dest)
            self.assertTrue(dest.is_dir())
            self.assertEqual(list(dest.iterdir()), [])

    def test_failure_does_not_remove_other_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / 'existing-empty'
            dest.mkdir()
            other = dest / 'user-created.txt'
            def failing_stream(command, target, expected, timeout=900, created_files=None):
                other.write_text('preserve')
                raise RuntimeError('simulated failure')
            with patch('vmforge.extraction.inspect_archive', return_value=[('disk.vdi', 3, False)]), \
                 patch('vmforge.extraction.find_extractor', return_value=('7zip', 'fake')), \
                 patch('vmforge.extraction.stream_entry', side_effect=failing_stream):
                with self.assertRaisesRegex(RuntimeError, 'simulated failure'):
                    extract_archive(root / 'image.7z', dest)
            self.assertEqual(other.read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
