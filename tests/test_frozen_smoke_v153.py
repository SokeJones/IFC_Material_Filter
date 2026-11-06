"""Frozen executable smoke-test report behavior (without native IFC dependencies)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class FrozenSmokeContractTests(unittest.TestCase):
    def test_selftest_writes_pass_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp)/'result.txt'
            with patch('selftest.run_selftest', return_value=True):
                self.assertEqual(app.main(['--selftest', '--selftest-report', str(report)]), 0)
            self.assertTrue(report.read_text(encoding='utf-8').startswith('PASS\n'))

    def test_selftest_failure_is_reported_and_has_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp)/'result.txt'
            with patch('selftest.run_selftest', side_effect=RuntimeError('forced failure')):
                self.assertEqual(app.main(['--selftest', '--selftest-report', str(report)]), 1)
            self.assertIn('RuntimeError: forced failure', report.read_text(encoding='utf-8'))
