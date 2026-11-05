import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from step_prune import prune_serialized_ifc

class StepPruneTests(unittest.TestCase):
    def test_preserves_header_kept_entities_and_footer(self):
        text=(b'ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n'
              b'#1=IFCWALL(\'a\');\n'
              b'#2=IFCWALL(\'b\');\n'
              b'#3=IFCMATERIAL(\'Name with ; inside\');\n'
              b'ENDSEC;\nEND-ISO-10303-21;\n')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'in.ifc';q=Path(td)/'out.ifc'
            p.write_bytes(text)
            stats=prune_serialized_ifc(p,q,{1,3},notify=lambda _:None,report_every_bytes=12)
            actual=q.read_bytes()
            self.assertIn(b'#1=',actual)
            self.assertIn(b'#3=',actual)
            self.assertNotIn(b'#2=',actual)
            self.assertIn(b'END-ISO-10303-21;',actual)
            self.assertEqual(stats['records_kept'],2)
            self.assertEqual(stats['records_removed'],1)
    def test_multiline_record(self):
        text=b'ISO-10303-21;\nDATA;\n#1=IFCFOO(\n  #3,\n  $);\n#2=IFCBAR($);\n#3=IFCMATERIAL(\'Name\');\nENDSEC;\n'
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a.ifc';q=Path(td)/'b.ifc'
            p.write_bytes(text)
            prune_serialized_ifc(p,q,{1,3},notify=lambda _:None)
            out=q.read_bytes()
            self.assertIn(b'#1=IFCFOO(\n  #3,\n  $);',out)
            self.assertNotIn(b'#2=IFCBAR',out)
    def test_missing_selected_id_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a.ifc';q=Path(td)/'b.ifc'
            p.write_bytes(b'DATA;\n#1=IFCFOO($);\nENDSEC;\n')
            with self.assertRaisesRegex(RuntimeError,'expected'):
                prune_serialized_ifc(p,q,{1,9},notify=lambda _:None)
            self.assertFalse(q.exists())
    def test_truncated_record_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a.ifc';q=Path(td)/'b.ifc'
            p.write_bytes(b'DATA;\n#1=IFCFOO(\n')
            with self.assertRaisesRegex(ValueError,'Truncated'):
                prune_serialized_ifc(p,q,{1},notify=lambda _:None)
            self.assertFalse(q.exists())

if __name__=='__main__':unittest.main()
