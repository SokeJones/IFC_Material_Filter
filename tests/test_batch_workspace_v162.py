"""Verify B06/B07/B08/B11 path routing without requiring native IFC."""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import batch_export

class FakeModel:
    schema = 'IFC2X3'
    def write(self, path):
        Path(path).write_bytes(b'unpruned IFC content')

class BatchWorkspaceTests(unittest.TestCase):
    def test_batch_serializes_and_validates_locally_before_publish(self):
        with tempfile.TemporaryDirectory() as d:
            destination = Path(d) / 'share' / 'filtered.ifc'
            events = []
            def prune(raw, temp, reachable, notify, class_report=None):
                self.assertTrue(raw.is_file())
                self.assertNotEqual(raw.parent, destination.parent)
                self.assertEqual(reachable, {1})
                temp.write_bytes(b'validated IFC bytes')
                events.append('prune')
                return {'records_kept':1, 'records_removed':2,'input_bytes':20,'output_bytes':19}
            fake_ifc = types.ModuleType('ifcopenshell')
            def open_ifc(path):
                self.assertTrue(Path(path).is_file())
                self.assertNotEqual(Path(path).parent, destination.parent)
                self.assertFalse(destination.exists())
                events.append('reopen')
                return FakeModel()
            fake_ifc.open = open_ifc
            with patch.object(batch_export, 'batch_filter',return_value={
                'reachable_entity_ids': {1}, 'remaining_elements': 1}), \
                 patch.object(batch_export, 'assert_support_shells_geometry_free'), \
                 patch.object(batch_export, 'retained_context_product_counts',return_value={}), \
                 patch('extract_export.validate_extraction',return_value={
                     'selected_without_representation':[], 'physical_count':1}), \
                 patch('step_prune.prune_serialized_ifc',side_effect=prune), \
                 patch.dict(sys.modules, {'ifcopenshell': fake_ifc}):
                report = batch_export.export_batch(FakeModel(), destination, {'GUID'}, set(),
                                                   set(), validation='basic',
                                                   save_reports=False, notify=lambda _:None)
            self.assertEqual(events,['prune','reopen'])
            self.assertEqual(destination.read_bytes(), b'validated IFC bytes')
            self.assertEqual(report['physical_count'],1)
            self.assertEqual(list(destination.parent.glob('*.publishing.incomplete.ifc')), [])

if __name__ == '__main__':
    unittest.main()
