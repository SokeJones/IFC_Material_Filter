import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from material_verification import _value_signature, effective_material, compare_materials


class FakeEntity:
    def __init__(self, step, kind, attrs):
        self.step, self.kind, self.attrs = step, kind, attrs
    def id(self): return self.step
    def is_a(self): return self.kind
    def __iter__(self): return iter(self.attrs.values())
    def attribute_name(self, i): return list(self.attrs)[i]


class MaterialSignatureTests(unittest.TestCase):
    def test_step_ids_are_not_part_of_material_signature(self):
        a = FakeEntity(10, 'IfcMaterial', {'Name':'Concrete', 'Description':None})
        b = FakeEntity(900, 'IfcMaterial', {'Name':'Concrete', 'Description':None})
        self.assertEqual(_value_signature(a), _value_signature(b))

    def test_material_layer_dimensions_are_compared(self):
        mat = FakeEntity(1, 'IfcMaterial', {'Name':'Concrete'})
        x = FakeEntity(2, 'IfcMaterialLayer', {'Material':mat, 'LayerThickness':0.25})
        y = FakeEntity(3, 'IfcMaterialLayer', {'Material':mat, 'LayerThickness':0.30})
        self.assertNotEqual(_value_signature(x), _value_signature(y))

    def test_direct_precedes_type(self):
        direct = FakeEntity(1, 'IfcMaterial', {'Name':'Direct'})
        inherited = FakeEntity(2, 'IfcMaterial', {'Name':'Type'})
        def get_material(element, should_inherit):
            return inherited if should_inherit else direct
        self.assertEqual(effective_material(object(), get_material)['material']['attributes']['Name'], 'Direct')
        self.assertEqual(effective_material(object(), get_material)['origin'], 'direct')

    def test_type_inheritance_and_no_material(self):
        inherited = FakeEntity(2, 'IfcMaterial', {'Name':'Type'})
        def inherited_get(e, should_inherit):
            return inherited if should_inherit else None
        self.assertEqual(effective_material(object(), inherited_get)['origin'], 'type')
        self.assertEqual(effective_material(object(), lambda e, should_inherit: None)['origin'], 'none')

    def test_rejects_same_source_path(self):
        with self.assertRaises(ValueError):
            compare_materials('a.ifc', 'a.ifc')

try:
    import ifcopenshell
    import ifcopenshell.guid
except ImportError:
    ifcopenshell = None


@unittest.skipIf(ifcopenshell is None, 'IfcOpenShell available on GitHub build runner')
class MaterialComparisonIntegration(unittest.TestCase):
    def test_roundtrip_direct_type_and_unassigned(self):
        f = ifcopenshell.file(schema='IFC4')
        mat = f.create_entity('IfcMaterial', Name='Stahlbeton Schweiz')
        mat2 = f.create_entity('IfcMaterial', Name='Stahl')
        wall = f.create_entity('IfcWall', GlobalId=ifcopenshell.guid.new())
        beam = f.create_entity('IfcBeam', GlobalId=ifcopenshell.guid.new())
        column = f.create_entity('IfcColumn', GlobalId=ifcopenshell.guid.new())
        walltype = f.create_entity('IfcWallType', GlobalId=ifcopenshell.guid.new(), PredefinedType='NOTDEFINED')
        f.create_entity('IfcRelAssociatesMaterial', GlobalId=ifcopenshell.guid.new(), RelatedObjects=[walltype], RelatingMaterial=mat)
        f.create_entity('IfcRelDefinesByType', GlobalId=ifcopenshell.guid.new(), RelatedObjects=[wall], RelatingType=walltype)
        f.create_entity('IfcRelAssociatesMaterial', GlobalId=ifcopenshell.guid.new(), RelatedObjects=[beam], RelatingMaterial=mat2)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src, out = td/'original.ifc', td/'filtered.ifc'
            f.write(str(src))
            f.write(str(out))
            result = compare_materials(src, out, notify=lambda _: None)
            self.assertTrue(result['passed'], result['differences'])
            self.assertEqual(result['material_equivalent'], 3)
            self.assertEqual(result['both_without_effective_material'], 1)
            changed = ifcopenshell.open(str(out))
            changed.by_type('IfcMaterial')[1].Name = 'Changed'
            changed.write(str(out))
            result = compare_materials(src, out, notify=lambda _: None)
            self.assertFalse(result['passed'])
            self.assertEqual(result['material_mismatches'], 1)

if __name__ == '__main__':
    unittest.main()
