"""Regression checks for the GUI-only v1.5 update, safe on headless CI."""
import ast
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'app.py'


class UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP.read_text(encoding='utf-8')
        cls.tree = ast.parse(cls.source)

    def test_simple_default_engine_and_validation(self):
        self.assertIn("self.enginevar = tk.StringVar(value='batch')", self.source)
        self.assertIn("self.validationvar = tk.StringVar(value='basic')", self.source)

    def test_material_input_hint_and_advanced_verification(self):
        for text in ('One per line or separated by semicolons.',
                     'Advanced options', 'Verify geometry...',
                     'Verify materials...', 'View processing log...'):
            self.assertIn(text, self.source)

    def test_indeterminate_progress_does_not_fabricate_percentage(self):
        self.assertIn("mode='indeterminate'", self.source)
        self.assertIn('self.progress.start(', self.source)
        self.assertIn('self.progress.stop()', self.source)

    def test_log_export_and_realtime_update(self):
        for method in ('_open_log', '_save_log', '_copy_log', '_append_text', '_log'):
            self.assertTrue(any(isinstance(n, ast.FunctionDef) and n.name == method
                                for n in ast.walk(self.tree)))

    def test_engine_dispatch_has_unchanged_arguments(self):
        self.assertIn('result = export_ifc(source, dest, materials, parent_mode=mode, dry_run=dry,', self.source)
        self.assertIn('engine=engine, validation=validation,', self.source)
