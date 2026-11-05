"""Runs on GitHub Windows builders with pinned IfcOpenShell installed.
Skipped on local machines without IfcOpenShell.
"""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from batch_export import batch_filter

try:
    import ifcopenshell
    import ifcopenshell.guid
except ImportError:
    ifcopenshell = None

@unittest.skipIf(ifcopenshell is None, 'IfcOpenShell only available on build runner')
class IfcBatchIntegrationTests(unittest.TestCase):
    def test_removes_unselected_wall_keeps_shared_property_set(self):
        f = ifcopenshell.file(schema='IFC4')
        project = f.create_entity('IfcProject', GlobalId=ifcopenshell.guid.new(), Name='Test')
        keep = f.create_entity('IfcWall', GlobalId=ifcopenshell.guid.new(), Name='Keep')
        drop = f.create_entity('IfcWall', GlobalId=ifcopenshell.guid.new(), Name='Drop')
        prop = f.create_entity('IfcPropertySingleValue', Name='Reference', NominalValue=None)
        pset = f.create_entity('IfcPropertySet', GlobalId=ifcopenshell.guid.new(), Name='Shared', HasProperties=[prop])
        f.create_entity('IfcRelDefinesByProperties', GlobalId=ifcopenshell.guid.new(),
                        RelatedObjects=[keep,drop], RelatingPropertyDefinition=pset)
        unused = f.create_entity('IfcCartesianPoint', Coordinates=(1.0,2.0,3.0))
        unused_id = unused.id()
        stats = batch_filter(f,{keep.GlobalId},set(),notify=lambda _: None)
        self.assertEqual(stats['remaining_elements'],1)
        self.assertEqual(len(f.by_type('IfcRelDefinesByProperties')),1)
        self.assertEqual(f.by_type('IfcRelDefinesByProperties')[0].RelatedObjects,(keep,))
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)/'subset.ifc'
            f.write(str(out))
            check = ifcopenshell.open(str(out))
            self.assertEqual([e.GlobalId for e in check.by_type('IfcElement')],[keep.GlobalId])
            self.assertEqual(len(check.by_type('IfcPropertySet')),1)
            self.assertEqual(len(check.by_type('IfcCartesianPoint')),0)

if __name__ == '__main__': unittest.main()
