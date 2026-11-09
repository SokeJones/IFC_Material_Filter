"""Phase 2 semantic preservation tests (M1, M2, M5, M6, M9).

Pure graph tests run everywhere. Synthetic IFC2X3, IFC4, IFC4X3 fixtures
run with pinned IfcOpenShell on GitHub's Windows runner.
"""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from batch_export import (
    prune_unused_type_declarations, reachable_ids, retained_context_product_counts,
)

try:
    import ifcopenshell
    import ifcopenshell.guid
except ImportError:
    ifcopenshell = None


class MockNode:
    def __init__(self, step_id, cls, refs=(), supers=()):
        self._id, self._cls, self._refs = step_id, cls, refs
        self.supers = set(supers)
    def id(self):
        return self._id
    def is_a(self, name=None):
        return self._cls if name is None else name in {self._cls} | self.supers
    def __iter__(self):
        return iter(self._refs)


class MockGraph:
    schema = 'IFC4'
    def __init__(self, relations=None, types=None, inverse=None):
        self.relations = relations or []
        self.types = types or []
        self.inverse = inverse or {}
        self.removed = []
    def by_type(self, name):
        if name == 'IfcRelDeclares':
            return self.relations
        if name == 'IfcRelDefinesByType':
            return self.types
        if name == 'IfcProduct':
            return []
        raise AssertionError(name)
    def remove(self, entity):
        self.removed.append(entity)
    def get_inverse(self, entity):
        return self.inverse.get(entity.id(), [])


class MockDeclares:
    def __init__(self, definitions):
        self.RelatedDefinitions = tuple(definitions)


class MockTypeRelation:
    def __init__(self, typ, objects):
        self.RelatingType = typ
        self.RelatedObjects = tuple(objects)


class Phase2GraphTests(unittest.TestCase):
    def test_m1_unused_product_type_removed_but_other_declarations_preserved(self):
        used = MockNode(1, 'IfcWallType', supers={'IfcTypeProduct'})
        unused = MockNode(2, 'IfcWallType', supers={'IfcTypeProduct'})
        template = MockNode(3, 'IfcPropertySetTemplate')
        rel = MockDeclares([used, unused, template])
        graph = MockGraph([rel], [MockTypeRelation(used, [MockNode(5, 'IfcWall')])])
        self.assertEqual(prune_unused_type_declarations(graph, lambda _: None), (1, 0))
        self.assertEqual(rel.RelatedDefinitions, (used, template))

    def test_m1_empty_ifc4_type_declaration_is_deleted(self):
        orphan = MockNode(1, 'IfcWallType', supers={'IfcTypeProduct'})
        rel = MockDeclares([orphan])
        graph = MockGraph([rel])
        self.assertEqual(prune_unused_type_declarations(graph, lambda _: None), (1, 1))
        self.assertEqual(graph.removed, [rel])

    def test_m1_ifc2x3_never_reads_nonexistent_declarations(self):
        graph = MockGraph()
        graph.schema = 'IFC2X3'
        self.assertEqual(prune_unused_type_declarations(graph), (0, 0))

    def test_m2_preserves_material_properties_and_shape_aspects_only_for_roots(self):
        mat = MockNode(1, 'IfcMaterial')
        prop = MockNode(2, 'IfcMaterialProperties', refs=(mat,))
        unused = MockNode(99, 'IfcMaterialProperties')
        shape = MockNode(3, 'IfcProductDefinitionShape')
        aspect = MockNode(4, 'IfcShapeAspect', refs=(shape,))
        layer_set = MockNode(5, 'IfcMaterialLayerSet')
        layer_prop = MockNode(6, 'IfcMaterialProperties', refs=(layer_set,))
        graph = MockGraph(inverse={1: [prop, unused], 3: [aspect], 5: [layer_prop]})
        # This isolated graph includes both properties as inverse references;
        # in real IFC the wrong-material association is not an inverse of mat.
        graph.inverse[1] = [prop]
        live = reachable_ids([mat, shape, layer_set], graph)
        self.assertEqual(live, {1, 2, 3, 4, 5, 6})
        self.assertNotIn(99, live)

    def test_m6_context_class_reporting_ignores_spatial_and_elements(self):
        items = [MockNode(1, 'IfcWall', supers={'IfcElement'}),
                 MockNode(2, 'IfcBuildingStorey', supers={'IfcSpatialStructureElement'}),
                 MockNode(3, 'IfcGrid'), MockNode(4, 'IfcAnnotation')]
        class Graph(MockGraph):
            def by_type(self, name):
                return items if name == 'IfcProduct' else super().by_type(name)
        self.assertEqual(retained_context_product_counts(Graph()),
                         {'IfcAnnotation': 1, 'IfcGrid': 1})


@unittest.skipIf(ifcopenshell is None, 'Requires pinned IfcOpenShell on Windows runner')
class Phase2IfcIntegration(unittest.TestCase):
    @staticmethod
    def _source(schema):
        f = ifcopenshell.file(schema=schema)
        new = ifcopenshell.guid.new
        project = f.create_entity('IfcProject', GlobalId=new(), Name='Phase 2 fixture')
        storey = f.create_entity('IfcBuildingStorey', GlobalId=new(), Name='Test level')
        f.create_entity('IfcRelAggregates', GlobalId=new(),
                        RelatingObject=project, RelatedObjects=[storey])
        wall = f.create_entity('IfcWall', GlobalId=new(), Name='Keep by inherited Concrete')
        brick_wall = f.create_entity('IfcWall', GlobalId=new(), Name='Drop: direct Brick overrides type')
        direct_wall = f.create_entity('IfcWall', GlobalId=new(), Name='Keep direct Concrete')
        f.create_entity('IfcRelContainedInSpatialStructure', GlobalId=new(),
                        RelatingStructure=storey,
                        RelatedElements=[wall, brick_wall, direct_wall])
        concrete = f.create_entity('IfcMaterial', Name='Concrete')
        brick = f.create_entity('IfcMaterial', Name='Brick')
        unused_material = f.create_entity('IfcMaterial', Name='UnusedTypeMaterial')
        good_type = f.create_entity('IfcWallType', GlobalId=new(), PredefinedType='NOTDEFINED')
        unused_type = f.create_entity('IfcWallType', GlobalId=new(), PredefinedType='NOTDEFINED')
        f.create_entity('IfcRelDefinesByType', GlobalId=new(),
                        RelatedObjects=[wall, brick_wall], RelatingType=good_type)
        for objs, material in (([good_type], concrete), ([brick_wall], brick),
                               ([direct_wall], concrete), ([unused_type], unused_material)):
            f.create_entity('IfcRelAssociatesMaterial', GlobalId=new(),
                            RelatedObjects=objs, RelatingMaterial=material)
        if schema != 'IFC2X3':
            f.create_entity('IfcRelDeclares', GlobalId=new(), RelatingContext=project,
                            RelatedDefinitions=[good_type, unused_type])
        strength = f.create_entity('IfcPropertySingleValue', Name='Density',
                                   NominalValue=f.create_entity('IfcReal', 2400.0))
        if schema == 'IFC2X3':
            f.create_entity('IfcExtendedMaterialProperties', Material=concrete,
                            ExtendedProperties=[strength], Name='MaterialDetails')
        else:
            f.create_entity('IfcMaterialProperties', Material=concrete,
                            Properties=[strength], Name='MaterialDetails')
        box = f.create_entity('IfcBoundingBox',
                              Corner=f.create_entity('IfcCartesianPoint', Coordinates=(0., 0., 0.)),
                              XDim=1., YDim=1., ZDim=1.)
        frame = f.create_entity('IfcAxis2Placement3D',
                                Location=f.create_entity('IfcCartesianPoint', Coordinates=(0., 0., 0.)))
        context = f.create_entity('IfcGeometricRepresentationContext',
                                  ContextType='Model', CoordinateSpaceDimension=3,
                                  WorldCoordinateSystem=frame)
        project.RepresentationContexts = [context]
        # An orphan type has its own mapped geometry. For IFC4+ M1 this
        # resource must disappear with the unused type declaration.
        unused_box = f.create_entity('IfcBoundingBox',
                                      Corner=f.create_entity('IfcCartesianPoint',
                                          Coordinates=(0., 0., 0.)),
                                      XDim=2., YDim=2., ZDim=2.)
        unused_rep = f.create_entity('IfcShapeRepresentation',
                                     ContextOfItems=context,
                                     RepresentationIdentifier='Body',
                                     RepresentationType='BoundingBox', Items=[unused_box])
        unused_type.RepresentationMaps = [f.create_entity(
            'IfcRepresentationMap', MappingOrigin=frame,
            MappedRepresentation=unused_rep)]
        shape = f.create_entity('IfcShapeRepresentation',
                                ContextOfItems=context, RepresentationIdentifier='Body',
                                RepresentationType='BoundingBox', Items=[box])
        owner_shape = f.create_entity('IfcProductDefinitionShape', Representations=[shape])
        direct_wall.Representation = owner_shape
        f.create_entity('IfcShapeAspect', ShapeRepresentations=[shape], Name='PartOfConcrete',
                        ProductDefinitional=True, PartOfProductDefinitionShape=owner_shape)
        return f, wall, brick_wall, direct_wall, good_type, unused_type

    def test_m1_m2_across_supported_schemas(self):
        from batch_export import batch_filter
        from step_prune import prune_serialized_ifc
        for schema in ('IFC2X3', 'IFC4', 'IFC4X3'):
            with self.subTest(schema=schema):
                f, wall, drop, direct, good_type, unused_type = self._source(schema)
                keep_guids = {wall.GlobalId, direct.GlobalId}
                used_guid = good_type.GlobalId
                unused_guid = unused_type.GlobalId
                stats = batch_filter(f, keep_guids, set(), notify=lambda _: None)
                with tempfile.TemporaryDirectory() as folder:
                    raw = Path(folder) / 'raw.ifc'
                    result = Path(folder) / 'filtered.ifc'
                    f.write(str(raw))
                    prune_serialized_ifc(raw, result, stats['reachable_entity_ids'],
                                         notify=lambda _: None)
                    reread = ifcopenshell.open(str(result))
                    self.assertEqual(reread.schema.upper(), schema)
                    self.assertEqual({e.GlobalId for e in reread.by_type('IfcElement')},
                                     keep_guids)
                    self.assertIsNotNone(reread.by_guid(used_guid))
                    if schema != 'IFC2X3':
                        self.assertNotIn(unused_guid,
                            {t.GlobalId for t in reread.by_type('IfcTypeProduct')})
                        declared = [t for rel in reread.by_type('IfcRelDeclares')
                                    for t in rel.RelatedDefinitions if t.is_a('IfcTypeProduct')]
                        self.assertEqual({t.GlobalId for t in declared}, {used_guid})
                        self.assertEqual(len(reread.by_type('IfcRepresentationMap')), 0)
                        self.assertEqual([m.Name for m in reread.by_type('IfcMaterial')],
                                         ['Concrete'])
                    self.assertEqual(len(reread.by_type('IfcExtendedMaterialProperties'
                                                          if schema == 'IFC2X3'
                                                          else 'IfcMaterialProperties')), 1)
                    self.assertEqual(len(reread.by_type('IfcShapeAspect')), 1)

    def test_m5_audit_reflects_retained_support_shell_and_opening(self):
        import csv
        from filter_engine import export_ifc
        f, wall, _, direct, *_ = self._source('IFC4')
        new = ifcopenshell.guid.new
        shell = f.create_entity('IfcElementAssembly', GlobalId=new(),
                                Name='Geometry-free assembly shell',
                                PredefinedType='NOTDEFINED')
        opening = f.create_entity('IfcOpeningElement', GlobalId=new(), Name='Support void')
        f.create_entity('IfcRelAggregates', GlobalId=new(),
                        RelatingObject=shell, RelatedObjects=[direct])
        f.create_entity('IfcRelVoidsElement', GlobalId=new(),
                        RelatingBuildingElement=direct,
                        RelatedOpeningElement=opening)
        with tempfile.TemporaryDirectory() as folder:
            src, out = Path(folder)/'original.ifc', Path(folder)/'subset.ifc'
            f.write(str(src))
            result = export_ifc(str(src), str(out), 'Concrete', engine='batch',
                                validation='basic', save_audit=True, save_reports=False,
                                notify=lambda _: None)
            self.assertEqual(result['selected'], 2)
            self.assertTrue(out.is_file())
            with out.with_suffix('.audit.csv').open(encoding='utf-8-sig', newline='') as h:
                rows = {row['global_id']: row for row in csv.DictReader(h)}
            self.assertEqual((rows[shell.GlobalId]['decision'], rows[shell.GlobalId]['reason']),
                             ('KEEP_SUPPORT', 'support_shell'))
            self.assertEqual((rows[opening.GlobalId]['decision'], rows[opening.GlobalId]['reason']),
                             ('KEEP_SUPPORT', 'support_opening'))
            self.assertEqual(rows[direct.GlobalId]['decision'], 'KEEP')
            self.assertEqual({e.GlobalId for e in ifcopenshell.open(str(out)).by_type('IfcElement')},
                             {wall.GlobalId, direct.GlobalId, shell.GlobalId, opening.GlobalId})

    def test_m9_end_to_end_extraction_preserves_metadata_for_three_schemas(self):
        from filter_engine import export_ifc
        for schema in ('IFC2X3', 'IFC4', 'IFC4X3'):
            with self.subTest(schema=schema):
                f, wall, drop, direct, used_type, unused_type = self._source(schema)
                # M6: retain nonphysical context via an existing spatial
                # containment relationship without treating it as material.
                annotation = f.create_entity('IfcAnnotation',
                                            GlobalId=ifcopenshell.guid.new(),
                                            Name='Plan reference')
                f.create_entity('IfcRelContainedInSpatialStructure',
                                GlobalId=ifcopenshell.guid.new(),
                                RelatingStructure=f.by_type('IfcBuildingStorey')[0],
                                RelatedElements=[annotation])
                with tempfile.TemporaryDirectory() as folder:
                    source = Path(folder)/'source.ifc'
                    dest = Path(folder)/'filtered.ifc'
                    f.write(str(source))
                    result = export_ifc(str(source), str(dest), 'Concrete',
                                        engine='batch', validation='basic',
                                        save_audit=False, save_reports=False,
                                        notify=lambda _: None)
                    out = ifcopenshell.open(str(dest))
                    self.assertEqual(result['selected'], 2)
                    self.assertEqual({e.GlobalId for e in out.by_type('IfcElement')},
                                     {wall.GlobalId, direct.GlobalId})
                    self.assertEqual(len(out.by_type('IfcShapeAspect')), 1)
                    self.assertEqual(result['engines']['batch']['validation']
                                     ['retained_non_element_products'].get('IfcAnnotation'), 1)
                    self.assertEqual(len(out.by_type('IfcExtendedMaterialProperties'
                                                      if schema == 'IFC2X3'
                                                      else 'IfcMaterialProperties')), 1)
                    if schema != 'IFC2X3':
                        self.assertNotIn(unused_type.GlobalId,
                                         {typ.GlobalId for typ in out.by_type('IfcTypeProduct')})


if __name__ == '__main__':
    unittest.main()
