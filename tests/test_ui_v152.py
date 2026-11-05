"""Static UI regression checks for the v1.5.2 polish release."""
import ast
import unittest
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8')


class UiPolishTests(unittest.TestCase):
    def test_primary_button_is_centered_and_bold(self):
        self.assertIn("style='Primary.TButton'", SOURCE)
        self.assertIn("font=('Segoe UI', 11, 'bold')", SOURCE)
        self.assertIn("self.runbutton.pack(anchor='center')", SOURCE)
        self.assertNotIn("self.runbutton.pack(fill='x'", SOURCE)

    def test_input_change_resets_progress_and_status(self):
        self.assertIn("self.filevar.trace_add('write', self._input_changed)", SOURCE)
        self.assertIn("self.progress.configure(value=0)", SOURCE)
        self.assertIn("self.stagevar.set('')", SOURCE)
        self.assertIn("self.statusvar.set('Ready to filter an IFC model.')", SOURCE)
        self.assertIn("if not self._busy():", SOURCE)

    def test_source_field_disabled_during_work(self):
        self.assertIn("self.source_entry.configure(state='disabled')", SOURCE)
        self.assertIn("self.source_entry.configure(state='normal')", SOURCE)

    def test_existing_advanced_options_remain(self):
        self.assertIn('Save audit CSV', SOURCE)
        self.assertIn('Save detailed reports', SOURCE)
        self.assertIn('View processing log...', SOURCE)
