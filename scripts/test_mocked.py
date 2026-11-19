"""Run tests without external processes; retain legacy integration tests separately."""
from pathlib import Path
import ast
import datetime
import json
import platform
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# These existing tests deliberately launch real extractors or Python children.
EXTERNAL = {
    'test_extraction.ArchiveIntegrationTests',
    'test_isolation.FullArchiveIntegrationTests',
    'test_extraction.StreamTests.test_stream_limit',
    'test_extraction.StreamTests.test_incomplete',
    'test_extraction.StreamTests.test_timeout',
}


def mocked_suite(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from mocked_suite(test)
        elif any(test.id() == key or test.id().startswith(key + '.') for key in EXTERNAL):
            def omitted():
                raise unittest.SkipTest('Integração com processo real excluída do modo mocks/fakes')
            yield unittest.FunctionTestCase(omitted, description=test.id())
        else:
            yield test


if __name__ == '__main__':
    temporary = ROOT / 'work' / 'test-tmp'
    temporary.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temporary)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    # Any unmocked subprocess is a test failure, including VBoxManage discovery.
    with patch('subprocess.Popen', side_effect=AssertionError('Processo real bloqueado nos testes')):
        result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(mocked_suite(suite)))
    syntax_errors = []
    for source in (ROOT / 'vmforge').rglob('*.py'):
        try:
            ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
        except (SyntaxError, UnicodeError) as exc:
            syntax_errors.append(str(exc))
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, capture_output=True, check=False)
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, text=True, capture_output=True, check=False)
    code = int(not result.wasSuccessful() or bool(syntax_errors))
    evidence = dict(command=[sys.executable, '-B', 'scripts/test_mocked.py'], exit_code=code,
                    tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                    skipped=len(result.skipped), skipped_tests=[reason for _, reason in result.skipped],
                    python=sys.version, environment=platform.platform(), commit=commit.stdout.strip(),
                    dirty=bool(dirty.stdout.strip()), date=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    syntax_errors=syntax_errors, real_virtualbox='not run', nvda='not run')
    output = ROOT / 'work' / 'quality.json'
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Evidência: {output}')
    sys.exit(code)
