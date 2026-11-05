import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from batch_export import reachable_ids, forward_refs, detach_and_remove_product
from filter_engine import output_paths
from performance import PerformanceLog

class Node:
    def __init__(self, ident, refs=(), name='IfcShapeRepresentation'):
        self._id=ident
        self._refs=tuple(refs)
        self._name=name
    def id(self):return self._id
    def is_a(self, cls=None):
        return self._name if cls is None else cls == self._name
    def __iter__(self):return iter(self._refs)

class BatchTests(unittest.TestCase):
    def test_reachability_preserves_shared_nodes(self):
        geom=Node(5)
        one=Node(1,(geom,))
        two=Node(2,(geom,))
        unused=Node(9)
        self.assertEqual(reachable_ids([one,two]), {1,2,5})
        self.assertNotIn(unused.id(),reachable_ids([one,two]))
    def test_forward_relationship_refs_are_discovered(self):
        item=Node(2)
        root=Node(1,((item,),))
        self.assertEqual(list(forward_refs(root)),[item])
    def test_output_names_for_both_engines(self):
        p=Path('filtered.ifc')
        paths=output_paths(p,'both')
        self.assertEqual(paths['ifcpatch'].name,'filtered_ifcpatch.ifc')
        self.assertEqual(paths['batch'].name,'filtered_batch.ifc')
        self.assertEqual(output_paths(p,'batch'), {'batch':p})
    def test_stage_records_memory_columns_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=PerformanceLog(lambda _:None,label='batch')
            log.count('output_bytes',123)
            with log.stage('batch test'):
                pass
            output=Path(tmp)/'timing.csv'
            summary=log.save(output)
            self.assertIn('peak_rss_mib',output.read_text(encoding='utf-8-sig'))
            self.assertTrue(output.with_suffix('.metrics.csv').is_file())
            self.assertEqual(summary['output_bytes'],123)

if __name__=='__main__': unittest.main()
