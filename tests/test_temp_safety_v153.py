"""Phase 1A recovery tests using a synthetic model; no IfcOpenShell required."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import batch_export


class FakeModel:
    def write(self, path):
        Path(path).write_text('HEADER;\nDATA;\nENDSEC;\n', encoding='ascii')


class TemporarySafetyTests(unittest.TestCase):
    def test_existing_unpruned_temp_fails_before_filtering(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result.ifc'
            raw = Path(folder) / 'result.unpruned.incomplete.ifc'
            raw.write_text('belonging to another run')
            with patch.object(batch_export, 'batch_filter') as filter_mock, \
                 patch.dict(sys.modules, {'ifcopenshell': __import__('types').ModuleType('ifcopenshell')}):
                with self.assertRaises(FileExistsError):
                    batch_export.export_batch(FakeModel(), out, {'x'}, set(), set())
                filter_mock.assert_not_called()
            self.assertEqual(raw.read_text(), 'belonging to another run')

    def test_own_temp_removed_on_failure_during_pruning(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result.ifc'
            raw = Path(folder) / 'result.unpruned.incomplete.ifc'
            temp = Path(folder) / 'result.incomplete.ifc'
            def failing_prune(*args, **kwargs):
                temp.write_text('partial')
                raise RuntimeError('synthetic failure')
            with patch.object(batch_export, 'batch_filter', return_value={
                'reachable_entity_ids': {1}, 'remaining_elements': 1,
            }), patch('step_prune.prune_serialized_ifc', side_effect=failing_prune), \
                patch.dict(sys.modules, {'ifcopenshell': __import__('types').ModuleType('ifcopenshell')}):
                with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
                    batch_export.export_batch(FakeModel(), out, {'x'}, set(), set(),
                                              save_reports=False, notify=lambda _:None)
            self.assertFalse(raw.exists())
            self.assertFalse(temp.exists())
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
