"""Filesystem safety and externally terminated run recovery; no IFC dependency."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_workspace import LocalWorkspace, recover_abandoned
from version import __version__

class WorkspaceTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, '1.6.2')

    def test_success_publishes_and_cleans(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'scratch'
            out = Path(d) / 'share' / 'result.ifc'
            with LocalWorkspace(out, root=root, notify=lambda _: None) as w:
                self.assertNotEqual(w.directory.parent, out.parent)
                w.raw.write_bytes(b'unpruned')
                w.pruned.write_bytes(b'valid-ifc')
                w.publish(w.pruned)
                self.assertEqual(out.read_bytes(), b'valid-ifc')
            self.assertEqual(list(root.glob('run-*')), [])
            self.assertEqual(list(out.parent.glob('*.publishing.incomplete.ifc')), [])

    def test_existing_final_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'out.ifc'
            out.write_bytes(b'existing')
            with LocalWorkspace(out, root=Path(d) / 'scratch', notify=lambda _: None) as w:
                w.pruned.write_bytes(b'new')
                with self.assertRaises(FileExistsError):
                    w.publish(w.pruned)
            self.assertEqual(out.read_bytes(), b'existing')

    def test_failed_copy_removes_partial_and_preserves_final(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'out.ifc'
            with LocalWorkspace(out, root=Path(d) / 'scratch', notify=lambda _: None) as w:
                w.pruned.write_bytes(b'valid')
                def fail_copy(source, target, length):
                    target.write(b'partial')
                    raise OSError('network disconnected')
                with patch('local_workspace.shutil.copyfileobj', side_effect=fail_copy):
                    with self.assertRaisesRegex(OSError, 'network disconnected'):
                        w.publish(w.pruned)
                self.assertFalse(out.exists())
                self.assertFalse(w.staging.exists())

    def test_active_workspace_not_removed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'scratch'
            out = Path(d) / 'result.ifc'
            with LocalWorkspace(out, root=root, notify=lambda _: None) as w:
                w.raw.write_bytes(b'live')
                self.assertEqual(recover_abandoned(root, notify=lambda _:None), 0)
                self.assertTrue(w.raw.is_file())
            self.assertEqual(list(root.iterdir()), [])

    def test_abandoned_process_is_recovered(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'scratch'
            out = Path(d) / 'destination' / 'result.ifc'
            code = '''import sys
from pathlib import Path
from local_workspace import LocalWorkspace
w=LocalWorkspace(Path(sys.argv[2]),root=Path(sys.argv[1]),notify=lambda _:None)
w.__enter__()
w.raw.write_bytes(b'partly written')
w.staging.parent.mkdir(parents=True,exist_ok=True)
w.staging.write_bytes(b'partial network transfer')
import os
os._exit(9)
'''
            script = Path(d) / 'child.py'
            script.write_text(code)
            result = subprocess.run([sys.executable, str(script), str(root), str(out)],
                                    env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])},
                                    check=False, timeout=10)
            self.assertEqual(result.returncode, 9)
            self.assertEqual(len(list(root.glob('run-*'))), 1)
            self.assertEqual(len(list(out.parent.glob('*.publishing.incomplete.ifc'))), 1)
            self.assertEqual(recover_abandoned(root, notify=lambda _:None), 1)
            self.assertEqual(list(root.glob('run-*')), [])
            self.assertEqual(list(out.parent.glob('*.publishing.incomplete.ifc')), [])
            self.assertFalse(out.exists())

if __name__ == '__main__':
    unittest.main()
