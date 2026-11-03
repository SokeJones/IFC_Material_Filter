import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_export import selection_query, validate_extraction, strip_unselected_assembly_geometry

class FakeElement:
    def __init__(self, guid, klass='IfcSlab', representation=object()):
        self.GlobalId = guid
        self.klass = klass
        self.Representation = representation
    def is_a(self, klass=None):
        if klass is None:
            return self.klass
        return self.klass == klass or (klass == 'IfcProduct' and self.klass.startswith('Ifc'))

class FakeModel:
    def __init__(self, elements, schema='IFC2X3'):
        self.elements = elements
        self.schema = schema
    def by_type(self, typ):
        assert typ == 'IfcElement'
        return self.elements

class ExtractionTests(unittest.TestCase):
    def test_guid_selection_query_is_stable(self):
        a, b = '1s3nqZvn1Bg82rZ1NhRmr9', '2QT4ig4lTBLRESJdLECLqQ'
        self.assertEqual(selection_query({b,a}), f'{a}, {b}')
    def test_empty_and_bad_ids_rejected(self):
        with self.assertRaises(ValueError): selection_query(set())
        with self.assertRaises(ValueError): selection_query({'bad'})
    def test_preserves_selected_and_strips_extra_parent_geometry(self):
        keep = FakeElement('A')
        parent = FakeElement('B', 'IfcRoof')
        model = FakeModel([keep, parent])
        cleared = strip_unselected_assembly_geometry(model, {'A'}, notify=lambda _: None)
        self.assertEqual(cleared, ['B'])
        self.assertIsNotNone(keep.Representation)
        self.assertIsNone(parent.Representation)
        self.assertEqual(validate_extraction(model,'IFC2X3',{'A'})['nonselected_shells_or_openings'],1)
    def test_rejects_extra_geometry(self):
        model=FakeModel([FakeElement('A'),FakeElement('B')])
        with self.assertRaisesRegex(RuntimeError,'Unexpected'):
            validate_extraction(model,'IFC2X3',{'A'})
    def test_rejects_missing_and_schema(self):
        model=FakeModel([FakeElement('A')])
        with self.assertRaisesRegex(RuntimeError,'missing'):
            validate_extraction(model,'IFC2X3',{'A','B'})
        with self.assertRaisesRegex(RuntimeError,'schema changed'):
            validate_extraction(model,'IFC4',{'A'})
    def test_support_openings_allowed(self):
        model = FakeModel([FakeElement('A'), FakeElement('OPEN', 'IfcOpeningElement')])
        self.assertEqual(validate_extraction(model,'IFC2X3',{'A'})['nonselected_shells_or_openings'],1)

if __name__ == '__main__': unittest.main()
