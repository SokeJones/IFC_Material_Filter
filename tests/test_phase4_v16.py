"""v1.6 material name case sensitivity and read-only inventory tests."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from filter_engine import parse_materials, find_matching_materials, assess_selection
from material_inventory import scan_model_materials


class Node:
    def __init__(self, eid, kind, name='', refs=(), direct=None, inherited=None):
        self._id = eid
        self._kind = kind
        self.Name = name
        self.refs = tuple(refs)
        self.GlobalId = f'GID{eid:019}'
        self.direct = direct
        self.inherited = inherited
    def id(self):
        return self._id
    def is_a(self):
        return self._kind
    def __iter__(self):
        return iter(self.refs)


class Rel:
    def __init__(self, parent, children):
        self.RelatingObject = parent
        self.RelatedObjects = tuple(children)


class Model:
    schema = 'IFC4'
    def __init__(self, mats, elements, aggregates=(), nests=()):
        self.items = {'IfcMaterial': mats, 'IfcElement': elements,
                      'IfcRelAggregates': aggregates, 'IfcRelNests': nests}
    def by_type(self, typ):
        return self.items[typ]


def fixture():
    concrete = Node(1, 'IfcMaterial', 'Concrete')
    lowercase = Node(2, 'IfcMaterial', 'concrete')
    steel = Node(3, 'IfcMaterial', 'Steel')
    unused = Node(4, 'IfcMaterial', 'Unused')
    e1 = Node(10, 'IfcWall', direct=concrete)
    e2 = Node(11, 'IfcWall', direct=lowercase)
    e3 = Node(12, 'IfcBeam', inherited=steel)
    parent = Node(13, 'IfcElementAssembly', direct=concrete)
    child = Node(14, 'IfcBeam')
    nested_child = Node(15, 'IfcBeam')
    layered = Node(20, 'IfcMaterialLayerSet', refs=(Node(21, 'IfcMaterialLayer',refs=(concrete,)),
                                                       Node(22, 'IfcMaterialLayer', refs=(steel,))))
    e4 = Node(16, 'IfcSlab', direct=layered)
    nested = Node(17, 'IfcElementAssembly', direct=steel)
    model = Model([concrete,lowercase,steel,unused],
                  [e1,e2,e3,parent,child,nested_child,e4,nested],
                  aggregates=[Rel(parent,[child])], nests=[Rel(nested,[nested_child])])
    return model


def getter(node, should_inherit):
    return node.direct or (node.inherited if should_inherit else None)


class CaseSensitiveTests(unittest.TestCase):
    def test_case_variant_names_remain_separate(self):
        self.assertEqual(parse_materials('Concrete; concrete\nCONCRETE;Concrete'),
                         ['Concrete','concrete','CONCRETE'])

    def test_matching_materials_does_not_fold_case(self):
        e = Node(1,'IfcMaterial','Concrete')
        self.assertEqual(find_matching_materials([e], {'Concrete'}), {'Concrete'})
        self.assertEqual(find_matching_materials([e], {'concrete'}), set())

    def test_typo_in_case_only_aborts_with_exact_suggestion(self):
        with self.assertRaisesRegex(ValueError, r'Similar material names:.*concrete.*Concrete'):
            assess_selection(set(), [], ['concrete'], ['Concrete'])

    def test_partial_case_mismatch_is_warned_not_ignored(self):
        messages=[]
        unmatched = assess_selection({10}, [{'matched_materials':'Concrete'}],
                                     ['Concrete','CONCRETE'], ['Concrete'], messages.append)
        self.assertEqual(unmatched, ['CONCRETE'])
        self.assertIn('Concrete', messages[0])


class MaterialScannerTests(unittest.TestCase):
    def run_scan(self, mode):
        return scan_model_materials(fixture(), mode, notify=lambda _: None,
                                    material_getter=getter)

    def test_scan_reports_exact_case_and_unused_names(self):
        result = self.run_scan('aggregates')
        by_name = {d['name']:d for d in result['materials']}
        self.assertEqual(set(by_name), {'Concrete','concrete','Steel','Unused'})
        self.assertEqual(by_name['Concrete'],
                         {'name':'Concrete','matching_elements':4,'direct':3,'type':0,'parent':1})
        self.assertEqual(by_name['concrete']['matching_elements'],1)
        self.assertEqual(by_name['Steel']['matching_elements'],3)
        self.assertEqual(by_name['Steel']['type'],1)
        self.assertEqual(by_name['Unused']['matching_elements'],0)
        self.assertEqual(result['elements_scanned'],8)

    def test_parent_mode_changes_counts_not_material_definitions(self):
        none = {r['name']:r for r in self.run_scan('none')['materials']}
        agg = {r['name']:r for r in self.run_scan('aggregates')['materials']}
        nest = {r['name']:r for r in self.run_scan('aggregates+nests')['materials']}
        self.assertEqual(none['Concrete']['matching_elements'],3)
        self.assertEqual(agg['Concrete']['matching_elements'],4)
        self.assertEqual(none['Steel']['matching_elements'],3)
        self.assertEqual(agg['Steel']['matching_elements'],3)
        self.assertEqual(nest['Steel']['matching_elements'],4)

    def test_scanner_rejects_duplicate_element_globalids(self):
        model=fixture()
        model.items['IfcElement'][0].GlobalId = model.items['IfcElement'][1].GlobalId
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            scan_model_materials(model, material_getter=getter, notify=lambda _: None)

    def test_scanner_rejects_unknown_parent_mode(self):
        with self.assertRaisesRegex(ValueError, 'Invalid parent mode'):
            self.run_scan('invalid')


class UiContractV16(unittest.TestCase):
    def test_scanner_under_advanced_material_tools(self):
        app = (Path(__file__).resolve().parents[1]/'app.py').read_text()
        self.assertIn("label='Material tools'", app)
        self.assertIn("label='Scan IFC materials...'", app)
        self.assertIn("'scan_done'", app)
        self.assertIn('mode=\'indeterminate\'', app)
        self.assertIn('case-sensitive', app)
        self.assertIn('self._invalidate_material_scan()', app)

    def test_manual_workflow_and_build_includes_scanner(self):
        workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/build-windows.yml').read_text()
        self.assertIn('workflow_dispatch:', workflow)
        self.assertNotIn('  push:', workflow)
        self.assertIn('material_inventory', workflow)


try:
    import ifcopenshell
    from test_phase2_v155 import Phase2IfcIntegration
except ImportError:
    ifcopenshell = None


@unittest.skipIf(ifcopenshell is None, 'Requires IfcOpenShell in GitHub Actions')
class ScannerIfcIntegration(unittest.TestCase):
    def test_real_ifc2x3_ifc4_ifc4x3_inventory_and_filter_agree(self):
        from filter_engine import export_ifc
        for schema in ('IFC2X3','IFC4','IFC4X3'):
            with self.subTest(schema=schema):
                model, wall, brick_wall, direct, *_ = Phase2IfcIntegration._source(schema)
                # Two names whose only difference is capitalization must remain
                # distinguishable and return disjoint selection counts.
                brick = next(m for m in model.by_type('IfcMaterial') if m.Name=='Brick')
                brick.Name = 'concrete'
                unused = next(m for m in model.by_type('IfcMaterial') if m.Name=='UnusedTypeMaterial')
                unused.Name = 'CONCRETE'
                report = scan_model_materials(model, notify=lambda _: None)
                counts = {x['name']: x['matching_elements'] for x in report['materials']}
                self.assertEqual(counts['Concrete'], 2)
                self.assertEqual(counts['concrete'], 1)
                self.assertEqual(counts['CONCRETE'], 0)
                with tempfile.TemporaryDirectory() as temp:
                    src = Path(temp)/'source.ifc'
                    dst = Path(temp)/'filtered.ifc'
                    model.write(str(src))
                    result = export_ifc(str(src), str(dst), 'Concrete', save_audit=False,
                                        save_reports=False, notify=lambda _: None)
                    self.assertEqual(result['selected'], counts['Concrete'])
                    self.assertTrue(dst.is_file())
                    self.assertEqual({e.GlobalId for e in ifcopenshell.open(str(dst)).by_type('IfcElement')},
                                     {wall.GlobalId, direct.GlobalId})


if __name__ == '__main__':
    unittest.main()
