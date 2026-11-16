"""Destination-side leftovers from old versions must never be deleted implicitly."""
import sys
import tempfile
import unittest
import types
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import batch_export
from local_workspace import LocalWorkspace

class FakeModel:
    def write(self, path):
        Path(path).write_text('HEADER;\nDATA;\nENDSEC;\n', encoding='ascii')

class TemporarySafetyTests(unittest.TestCase):
    def test_old_destination_partial_is_not_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result.ifc'
            legacy = out.with_name(out.stem + '.unpruned.incomplete.ifc')
            legacy.write_text('belonging to another run')
            # B00 is reached; prior temp file is not a preflight blocker.
            with patch.object(batch_export, 'batch_filter', side_effect=RuntimeError('stop')), \
                 patch.dict(sys.modules, {'ifcopenshell': types.ModuleType('ifcopenshell')}):
                with self.assertRaisesRegex(RuntimeError, 'stop'):
                    batch_export.export_batch(FakeModel(), out, {'x'}, set(), set(),
                                              save_reports=False, notify=lambda _: None)
            self.assertEqual(legacy.read_text(), 'belonging to another run')
            self.assertFalse(out.exists())

    def test_workspace_cleanup_after_exception(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result.ifc'
            root = Path(folder) / 'workspace'
            with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
                with LocalWorkspace(out, root=root, notify=lambda _: None) as workspace:
                    workspace.raw.write_text('source')
                    workspace.pruned.write_text('partial')
                    raise RuntimeError('synthetic failure')
            self.assertEqual(list(root.glob('run-*')), [])
            self.assertFalse(out.exists())

if __name__ == '__main__':
    unittest.main()
