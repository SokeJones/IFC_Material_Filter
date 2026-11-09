"""Phase 1B: order-independent space removal and support-shell geometry rules."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from batch_export import assert_support_shells_geometry_free, remove_unselected_spaces

try:
    import ifcopenshell
    import ifcopenshell.guid
except ImportError:
    ifcopenshell = None


class FakeElement:
    def __init__(self, guid, representation=None, opening=False, types=()):
        self.GlobalId = guid
        self.Representation = representation
        self.opening = opening
        self.IsTypedBy = types

    def is_a(self, ifc_class):
        return ifc_class == 'IfcOpeningElement' and self.opening


class FakeFile:
    def __init__(self, elements):
        self.elements = elements

    def by_type(self, name):
        assert name == 'IfcElement'
        return self.elements


class ShellInvariantTests(unittest.TestCase):
    def test_shell_representation_is_rejected(self):
        model = FakeFile([FakeElement('KEEP', object()), FakeElement('SHELL', object())])
        with self.assertRaisesRegex(RuntimeError, 'support shell'):
            assert_support_shells_geometry_free(model, {'KEEP'}, {'SHELL'})

    def test_shell_type_mapped_representation_is_rejected(self):
        class Type:
            RepresentationMaps = [object()]
        class Rel:
            RelatingType = Type()
        model = FakeFile([FakeElement('SHELL', types=[Rel()])])
        with self.assertRaisesRegex(RuntimeError, 'support shell'):
            assert_support_shells_geometry_free(model, set(), {'SHELL'})

    def test_geometry_free_shell_and_represented_opening_are_allowed(self):
        model = FakeFile([FakeElement('KEEP', object()), FakeElement('SHELL'),
                          FakeElement('OPENING', object(), opening=True)])
        self.assertEqual(assert_support_shells_geometry_free(
            model, {'KEEP'}, {'SHELL', 'OPENING'}), 2)


@unittest.skipIf(ifcopenshell is None, 'Requires real IfcOpenShell on Windows runner')
class NestedSpaceIntegration(unittest.TestCase):
    def test_parent_space_first_child_space_keeps_storey_and_world_coordinates(self):
        import numpy as np
        import ifcopenshell.util.placement
        f = ifcopenshell.file(schema='IFC4')
        guid = ifcopenshell.guid.new
        project = f.create_entity('IfcProject', GlobalId=guid())
        unit = f.create_entity('IfcSIUnit', UnitType='LENGTHUNIT', Name='METRE')
        project.UnitsInContext = f.create_entity('IfcUnitAssignment', Units=[unit])
        storey = f.create_entity('IfcBuildingStorey', GlobalId=guid())
        parent = f.create_entity('IfcSpace', GlobalId=guid())
        child = f.create_entity('IfcSpace', GlobalId=guid())
        column = f.create_entity('IfcColumn', GlobalId=guid())
        # Insertion order ensures parent is removed before child in old code.
        for a, b in ((project, storey), (storey, parent), (parent, child)):
            f.create_entity('IfcRelAggregates', GlobalId=guid(), RelatingObject=a,
                            RelatedObjects=[b])
        f.create_entity('IfcRelContainedInSpatialStructure', GlobalId=guid(),
                        RelatingStructure=child, RelatedElements=[column])
        def placement(parent_placement, x):
            point = f.create_entity('IfcCartesianPoint', Coordinates=(float(x), 0., 0.))
            axis = f.create_entity('IfcAxis2Placement3D', Location=point)
            return f.create_entity('IfcLocalPlacement', PlacementRelTo=parent_placement,
                                   RelativePlacement=axis)
        storey.ObjectPlacement = placement(None, 100.)
        parent.ObjectPlacement = placement(storey.ObjectPlacement, 10.)
        child.ObjectPlacement = placement(parent.ObjectPlacement, 5.)
        column.ObjectPlacement = placement(child.ObjectPlacement, 3.)
        before = ifcopenshell.util.placement.get_local_placement(column.ObjectPlacement)
        removed, moved = remove_unselected_spaces(f, notify=lambda _: None)
        after = ifcopenshell.util.placement.get_local_placement(column.ObjectPlacement)
        self.assertEqual((removed, moved), (2, 1))
        self.assertEqual(len(f.by_type('IfcSpace')), 0)
        self.assertTrue(np.allclose(before, after, atol=1e-7, rtol=0))
        self.assertEqual(column.ObjectPlacement.PlacementRelTo, storey.ObjectPlacement)
        self.assertEqual(f.by_type('IfcRelContainedInSpatialStructure')[0].RelatingStructure, storey)


if __name__ == '__main__':
    unittest.main()
