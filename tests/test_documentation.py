"""Check local documentation targets and packaged version without network access."""
from pathlib import Path
import re
import tomllib
import unittest

import vmforge


class DocumentationTests(unittest.TestCase):
    def test_local_markdown_targets_exist(self):
        root = Path(__file__).resolve().parents[1]
        for path in [root / 'README.md', root / 'CHANGELOG.md', *(root / 'docs').glob('*.md')]:
            text = path.read_text(encoding='utf-8')
            for target in re.findall(r'\]\(([^\s)]+)\)', text):
                if '://' in target or target.startswith(('#', 'mailto:')):
                    continue
                with self.subTest(document=path.name, target=target):
                    self.assertTrue((path.parent / target.split('#')[0]).exists())

    def test_package_version_matches_module(self):
        root = Path(__file__).resolve().parents[1]
        data = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
        self.assertEqual(data['project']['version'], vmforge.__version__)
