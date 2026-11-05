import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geometry_verification import mesh_signature, compare_geometry
from validation_v146 import orphan_placement_diagnostics

class GeometrySignatureTests(unittest.TestCase):
    def test_mesh_order_and_face_winding_do_not_affect_signature(self):
        verts_a = [0,0,0, 1,0,0, 0,1,0, 1,1,0]
        faces_a = [0,1,2, 1,3,2]
        verts_b = [1,1,0, 0,1,0, 1,0,0, 0,0,0]
        faces_b = [1,2,3, 0,1,2]
        self.assertEqual(mesh_signature(verts_a, faces_a)['triangle_hash'],
                         mesh_signature(verts_b, faces_b)['triangle_hash'])
    def test_modified_triangle_fails(self):
        a = mesh_signature([0,0,0, 1,0,0, 0,1,0], [0,1,2])
        b = mesh_signature([0,0,0, 2,0,0, 0,1,0], [0,1,2])
        self.assertNotEqual(a['triangle_hash'], b['triangle_hash'])
    def test_zero_tolerance_rejected_before_import(self):
        with self.assertRaises(ValueError):
            compare_geometry('a.ifc','b.ifc',tolerance=0)
    def test_same_filename_rejected_before_import(self):
        with self.assertRaises(ValueError):
            compare_geometry('a.ifc','a.ifc')

class OrphanDiagnosticTests(unittest.TestCase):
    def test_orphan_count_is_bounded(self):
        class MockPlacement:
            def id(self): return 10
            PlacesObject = ()
            ReferencedByPlacements = ()
            PlacementRelTo = None
        class MockModel:
            def by_type(self, cls): return [MockPlacement(), MockPlacement()]
        result = orphan_placement_diagnostics(MockModel(), limit=1)
        self.assertEqual(result['total_orphan_placements'], 2)
        self.assertEqual(len(result['orphan_placements']), 1)
        self.assertTrue(result['truncated'])

if __name__ == '__main__': unittest.main()
