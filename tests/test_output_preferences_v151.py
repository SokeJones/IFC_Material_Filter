"""Confirm routine output defaults and optional report-writing paths."""
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from performance import PerformanceLog

ROOT = Path(__file__).resolve().parents[1]


class OutputPreferencesTests(unittest.TestCase):
    def test_gui_defaults_disabled(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn('self.saveauditvar = tk.BooleanVar(value=False)', source)
        self.assertIn('self.savereportsvar = tk.BooleanVar(value=False)', source)
        self.assertIn('Save audit CSV', source)
        self.assertIn('Save detailed reports', source)
        self.assertIn('save_audit=save_audit, save_reports=save_reports', source)

    def test_reportless_performance_does_not_write_files(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('os.getcwd', return_value=directory):
                perf = PerformanceLog(lambda _s: None)
                perf.count('selected_elements', 5)
                result = perf.finish()
            self.assertEqual(result['selected_elements'], 5)
            self.assertNotIn('timing_csv', result)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_saved_performance_creates_both_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'example.timing.csv'
            perf = PerformanceLog(lambda _s: None)
            result = perf.save(output)
            self.assertTrue(output.exists())
            self.assertTrue(output.with_suffix('.metrics.csv').exists())
            self.assertEqual(result['timing_csv'], str(output))

    def test_batch_optional_reports_are_conditional(self):
        source = (ROOT / 'batch_export.py').read_text(encoding='utf-8')
        self.assertIn('if save_reports:', source)
        self.assertIn('if save_reports else None', source)
        ast.parse(source)
