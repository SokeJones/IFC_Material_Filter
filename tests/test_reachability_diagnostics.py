import csv
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from batch_export import reachable_ids
from reachability_diagnostics import ReachabilityDiagnostics
from step_prune import prune_serialized_ifc

class Node:
    def __init__(self, eid, name='IfcCartesianPoint', forward=()):
        self._eid = eid
        self._name = name
        self._forward = forward
    def id(self): return self._eid
    def is_a(self, target=None):
        return self._name if target is None else self._name == target
    def __iter__(self): return iter(self._forward)

class DiagnosticTests(unittest.TestCase):
    def test_reachability_diagnostics_do_not_change_selection(self):
        child = Node(2)
        inline = Node(0, forward=(child,))
        root = Node(1, 'IfcWall', (inline,))
        d = ReachabilityDiagnostics()
        self.assertEqual(reachable_ids([root]), reachable_ids([root], diagnostics=d))
        self.assertEqual(d.report()['visited_serialized_entities'], 2)
        self.assertEqual(d.report()['transient_inline_visits'], 1)
        self.assertEqual(d.report()['first_discovery_path'][0]['name'], 'root')
    def test_inverse_discovery_reports_source_and_relationship_class(self):
        inverse = Node(3, 'IfcRelDefinesByProperties')
        owner = Node(1, 'IfcWall')
        class FakeModel:
            def get_inverse(self, obj):
                return [inverse] if obj.id() == 1 else []
        # Unit test's Node is_a implements exact identity, but the algorithm
        # uses polymorphic IfcObjectDefinition checks. Use a simple subclass.
        class Owner(Node):
            def is_a(self, target=None):
                if target in ('IfcObjectDefinition','IfcTypeObject'):
                    return target == 'IfcObjectDefinition'
                return super().is_a(target)
        owner = Owner(1, 'IfcWall')
        class Relationship(Node):
            def is_a(self, target=None):
                if target == 'IfcRelationship':
                    return True
                return super().is_a(target)
        inverse = Relationship(3, 'IfcRelDefinesByProperties')
        diag = ReachabilityDiagnostics()
        self.assertEqual(reachable_ids([owner], FakeModel(), diag), {1,3})
        r=diag.report()
        self.assertEqual(r['newly_discovered_inverse_relationship_classes'][0]['name'], 'IfcRelDefinesByProperties')
        self.assertEqual(r['largest_inverse_fanout_sources'][0]['source_step'], 1)
        self.assertEqual(r['first_discovery_path'][0]['count'], 1)

    def test_serialized_bytes_by_class(self):
        data = (b'ISO-10303-21;\nDATA;\n#1=IFCCARTESIANPOINT((1.,2.));\n'
                b'#2=IFCCARTESIANPOINT((3.,4.));\n#3=IFCWALL(\n$);\nENDSEC;\nEND-ISO-10303-21;\n')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = root/'a.ifc'; src.write_bytes(data)
            out = root/'b.ifc'; report = root/'classes.csv'
            stats = prune_serialized_ifc(src, out, {1, 3}, lambda _:None, class_report=report)
            self.assertEqual(stats['records_kept'], 2)
            with report.open(encoding='utf-8-sig', newline='') as f:
                rows = {r['ifc_class']:r for r in csv.DictReader(f)}
            self.assertEqual(rows['IFCCARTESIANPOINT']['retained_records'], '1')
            self.assertEqual(rows['IFCCARTESIANPOINT']['pruned_records'], '1')
            self.assertEqual(rows['IFCWALL']['retained_records'], '1')
            self.assertNotIn(b'#2=',out.read_bytes())

if __name__ == '__main__': unittest.main()
