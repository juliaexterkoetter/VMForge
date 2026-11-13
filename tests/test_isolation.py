import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_protection import fixture, DISK, PROTECTED_UUID, TEST_PROTECTION
from vmforge.appliance import isolate_new_image, validate_appliance
from vmforge.config import Settings, prepare_image



def setUpModule():
    global protection_patch
    protection_patch = patch(
        "vmforge.protection.load_protection",
        return_value=TEST_PROTECTION,
    )
    protection_patch.start()


def tearDownModule():
    protection_patch.stop()


class IsolationTests(unittest.TestCase):
    def test_only_uuid_bytes_change_in_new_disk(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = fixture(root, identity=PROTECTED_UUID)
            before = (root/'disk.vdi').read_bytes()
            result = isolate_new_image(path, root)
            after = (root/'disk.vdi').read_bytes()
            self.assertNotEqual(result['uuid'], PROTECTED_UUID)
            self.assertNotEqual(result['disk_uuid'], DISK)
            self.assertEqual(before[:392], after[:392])
            self.assertEqual(before[408:], after[408:])
            self.assertNotEqual(before[392:408], after[392:408])
            self.assertEqual(validate_appliance(path), result)
            self.assertIn('xmlns="http://www.virtualbox.org/"', path.read_text())
            self.assertNotIn('ns0:', path.read_text())

    def test_outside_destination_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = fixture(root)
            before = (root/'disk.vdi').read_bytes()
            with self.assertRaises(ValueError):
                isolate_new_image(path, root/'other')
            self.assertEqual((root/'disk.vdi').read_bytes(), before)

    def test_prepare_preserves_archive_and_rejects_second_use(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root/'original.7z'
            archive.write_bytes(b'unchanged original')
            digest = hashlib.sha256(archive.read_bytes()).digest()
            dest = root/'new'
            def extract(image, destination):
                destination.mkdir()
                fixture(destination, identity=PROTECTED_UUID)
            with patch('vmforge.config.extract_archive', side_effect=extract):
                path = prepare_image(Settings(archive, dest))
                self.assertNotEqual(validate_appliance(path)['uuid'], PROTECTED_UUID)
                with self.assertRaises(ValueError):
                    prepare_image(Settings(archive, dest))
            self.assertEqual(hashlib.sha256(archive.read_bytes()).digest(), digest)

    def test_hardlinked_disk_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = fixture(root)
            link = root/'linked.vdi'
            try:
                link.hardlink_to(root/'disk.vdi')
            except OSError as exc:
                self.skipTest(str(exc))
            before = link.read_bytes()
            with self.assertRaises(ValueError):
                isolate_new_image(path, root)
            self.assertEqual(link.read_bytes(), before)

class FullArchiveIntegrationTests(unittest.TestCase):
    def test_original_archive_to_independent_appliance(self):
        from vmforge.extraction import sevenzip_path, find_extractor
        import subprocess
        try:
            binary = sevenzip_path()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        with tempfile.TemporaryDirectory(prefix='vmforge integração ') as td:
            root = Path(td)
            source = root/'origem'
            source.mkdir()
            fixture(source, identity=PROTECTED_UUID)
            original_disk = (source/'disk.vdi').read_bytes()
            archive = root/'original.7z'
            subprocess.run([binary, 'a', '-t7z', str(archive), str(source)], check=True, capture_output=True)
            digest = hashlib.sha256(archive.read_bytes()).digest()
            extractors = [('7zip', binary)]
            native = find_extractor()
            if native[0] == 'tar':
                extractors.append(native)
            for index, extractor in enumerate(extractors):
                with self.subTest(extractor=extractor[0]), patch('vmforge.extraction.find_extractor', return_value=extractor):
                    path = prepare_image(Settings(archive, root/f'dest-{index}'))
                    appliance = validate_appliance(path)
                    self.assertNotEqual(appliance['uuid'], PROTECTED_UUID)
                    self.assertNotEqual(appliance['disk_uuid'], DISK)
                    self.assertEqual((source/'disk.vdi').read_bytes(), original_disk)
                    self.assertEqual(hashlib.sha256(archive.read_bytes()).digest(), digest)
