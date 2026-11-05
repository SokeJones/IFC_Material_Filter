"""Tests v1.4.5 space/presentation rules on an actual IFC file when available."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from batch_export import (live_roots, remove_unselected_spaces,
                          restrict_presentation_layers, batch_filter)
from step_prune import prune_serialized_ifc

try:
    import ifcopenshell
    import ifcopenshell.guid
except ImportError:
    ifcopenshell = None


@unittest.skipIf(ifcopenshell is None, 'Requires IfcOpenShell on GitHub Actions Windows runner')
class SpaceLayerIntegration(unittest.TestCase):
    def setUp(self):
        self.f = ifcopenshell.file(schema='IFC4')
        self.p = self.f.create_entity('IfcProject', GlobalId=ifcopenshell.guid.new())
        self.site = self.f.create_entity('IfcSite', GlobalId=ifcopenshell.guid.new())
        self.building = self.f.create_entity('IfcBuilding', GlobalId=ifcopenshell.guid.new())
        self.storey = self.f.create_entity('IfcBuildingStorey', GlobalId=ifcopenshell.guid.new())
        self.space = self.f.create_entity('IfcSpace', GlobalId=ifcopenshell.guid.new())
        for parent, child in [(self.p, self.site), (self.site, self.building),
                              (self.building, self.storey), (self.storey, self.space)]:
            self.f.create_entity('IfcRelAggregates', GlobalId=ifcopenshell.guid.new(),
                                 RelatingObject=parent, RelatedObjects=[child])
        self.keep = self.f.create_entity('IfcWall', GlobalId=ifcopenshell.guid.new())
        self.drop = self.f.create_entity('IfcWall', GlobalId=ifcopenshell.guid.new())

    def add_shape(self, product, x):
        p = self.f.create_entity('IfcCartesianPoint', Coordinates=(float(x),0.,0.))
        line = self.f.create_entity('IfcPolyline', Points=[p, self.f.create_entity('IfcCartesianPoint', Coordinates=(float(x),1.,0.))])
        rep = self.f.create_entity('IfcShapeRepresentation', RepresentationIdentifier='Body',
                                   RepresentationType='Curve2D', Items=[line])
        product.Representation = self.f.create_entity('IfcProductDefinitionShape', Representations=[rep])
        return rep

    def test_unselected_space_removed_and_contained_product_reparented(self):
        self.f.create_entity('IfcRelContainedInSpatialStructure', GlobalId=ifcopenshell.guid.new(),
                             RelatedElements=[self.keep], RelatingStructure=self.space)
        self.add_shape(self.space, 10)
        self.add_shape(self.keep, 1)
        removed, moved = remove_unselected_spaces(self.f, lambda _: None)
        self.assertEqual((removed, moved), (1, 1))
        self.assertEqual(len(self.f.by_type('IfcSpace')), 0)
        contains = self.f.by_type('IfcRelContainedInSpatialStructure')
        self.assertEqual(len(contains), 1)
        self.assertEqual(contains[0].RelatingStructure.id(), self.storey.id())
        self.assertEqual(contains[0].RelatedElements[0].GlobalId, self.keep.GlobalId)
        self.assertFalse(any(e.is_a('IfcSpace') for e in live_roots(self.f, {self.keep.GlobalId})))

    def test_shared_presentation_layer_is_clipped(self):
        keep_rep = self.add_shape(self.keep, 1)
        drop_rep = self.add_shape(self.drop, 20)
        layer = self.f.create_entity('IfcPresentationLayerAssignment', Name='Mixed',
                                      AssignedItems=[keep_rep,drop_rep])
        changed, removed, kept = restrict_presentation_layers(self.f, {self.keep.GlobalId}, lambda _: None)
        self.assertEqual((changed,removed,kept), (1,1,1))
        self.assertEqual([x.id() for x in layer.AssignedItems], [keep_rep.id()])
        self.assertEqual(self.drop.Representation.Representations[0].id(),drop_rep.id())

    def test_filtered_ifc_does_not_retain_space_or_unselected_layer_geometry(self):
        self.add_shape(self.space, 30)
        keep_rep = self.add_shape(self.keep, 1)
        drop_rep = self.add_shape(self.drop, 20)
        self.f.create_entity('IfcPresentationLayerAssignment', Name='Mixed',
                             AssignedItems=[keep_rep,drop_rep])
        self.f.create_entity('IfcRelContainedInSpatialStructure', GlobalId=ifcopenshell.guid.new(),
                             RelatedElements=[self.keep], RelatingStructure=self.space)
        stats = batch_filter(self.f, {self.keep.GlobalId}, set(), notify=lambda _: None)
        self.assertEqual(stats['removed_spaces'], 1)
        self.assertEqual(stats['remaining_elements'], 1)
        with tempfile.TemporaryDirectory() as td:
            raw, subset = Path(td)/'raw.ifc', Path(td)/'subset.ifc'
            self.f.write(str(raw))
            prune_serialized_ifc(raw, subset, stats['reachable_entity_ids'], notify=lambda _: None)
            result = ifcopenshell.open(str(subset))
            self.assertEqual(len(result.by_type('IfcSpace')), 0)
            self.assertEqual([e.GlobalId for e in result.by_type('IfcElement')], [self.keep.GlobalId])
            self.assertEqual(len(result.by_type('IfcPresentationLayerAssignment')), 1)
            layer = result.by_type('IfcPresentationLayerAssignment')[0]
            self.assertEqual(len(layer.AssignedItems), 1)
            self.assertEqual(layer.AssignedItems[0].id(), result.by_type('IfcWall')[0].Representation.Representations[0].id())

if __name__ == '__main__': unittest.main()
