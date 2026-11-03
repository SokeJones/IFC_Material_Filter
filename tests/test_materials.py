import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from filter_engine import parse_materials, find_matching_materials

class FakeEntity:
    def __init__(self, eid, kind, name=None, fields=()):
        self._eid, self._kind, self.Name, self.fields = eid, kind, name, fields
    def id(self): return self._eid
    def is_a(self): return self._kind
    def __iter__(self): return iter(self.fields)

class TestMaterialSelection(unittest.TestCase):
    def test_multiple_names_and_dedupe(self):
        self.assertEqual(parse_materials('  Stahlbeton Schweiz;Beton C30/37\nSTAHLBETON SCHWEIZ'),
                         ['Stahlbeton Schweiz', 'Beton C30/37'])
    def test_exact_matching_case_insensitive(self):
        a = FakeEntity(1, 'IfcMaterial', 'Stahlbeton Schweiz')
        self.assertEqual(find_matching_materials([a], {'stahlbeton schweiz'}), {'Stahlbeton Schweiz'})
        self.assertFalse(find_matching_materials([a], {'stahlbeton'}))
    def test_composite_material_or(self):
        m1 = FakeEntity(1, 'IfcMaterial', 'Stahlbeton Schweiz')
        m2 = FakeEntity(2, 'IfcMaterial', 'Abdichtung')
        layer1 = FakeEntity(3, 'IfcMaterialLayer', fields=(m1, 0.4))
        layer2 = FakeEntity(4, 'IfcMaterialLayer', fields=(m2, 0.01))
        layers = FakeEntity(5, 'IfcMaterialLayerSet', fields=((layer1, layer2),))
        self.assertEqual(find_matching_materials([layers], {'abdichtung'}), {'Abdichtung'})
        self.assertEqual(find_matching_materials([layers], {'abdichtung','stahlbeton schweiz'}), {'Abdichtung','Stahlbeton Schweiz'})
    def test_cycle(self):
        obj = FakeEntity(4,'IfcMaterialLayerSet')
        obj.fields = (obj,)
        self.assertFalse(find_matching_materials([obj], {'a'}))

if __name__ == '__main__': unittest.main()
