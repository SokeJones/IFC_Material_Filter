"""Phase 3 m1/m2/m3/m5/m6/m7/m9/m11 contract and regression tests."""
import csv
import contextlib
import io
import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cli
from filter_engine import parse_materials, export_ifc
from extract_export import validate_extraction
from geometry_verification import _placements_equivalent
from performance import PerformanceLog
from version import __version__


class Phase3Tests(unittest.TestCase):
    def test_m1_cli_lists_split_using_gui_rules(self):
        self.assertEqual(parse_materials([' Concrete;Steel ', 'Brick\nCONCRETE', ' Insulation ; steel']),
                         ['Concrete', 'Steel', 'Brick', 'Insulation'])

    def test_public_api_defaults_match_gui_one_ifc_output(self):
        params = inspect.signature(export_ifc).parameters
        self.assertEqual(params['engine'].default, 'batch')
        self.assertEqual(params['validation'].default, 'basic')
        self.assertIs(params['save_audit'].default, False)
        self.assertIs(params['save_reports'].default, False)

    def test_cli_defaults_match_gui_one_ifc_output(self):
        parser = cli.build_parser()
        args = parser.parse_args(['source.ifc', 'result.ifc', '--material', 'A;B'])
        self.assertEqual(args.engine, 'batch')
        self.assertEqual(args.validation, 'basic')
        self.assertFalse(args.save_audit)
        self.assertFalse(args.save_reports)
        with patch.object(cli, 'export_ifc', return_value={'ok':True}) as exported:
            self.assertEqual(cli.main(['source.ifc','result.ifc','--material','A;B']), {'ok':True})
        self.assertEqual(exported.call_args.kwargs['engine'], 'batch')
        self.assertEqual(exported.call_args.kwargs['validation'], 'basic')
        self.assertFalse(exported.call_args.kwargs['save_audit'])
        self.assertFalse(exported.call_args.kwargs['save_reports'])
        self.assertEqual(parse_materials(exported.call_args.args[2]), ['A','B'])

    def test_cli_opt_in_flags_and_legacy_no_flags(self):
        p = cli.build_parser()
        enabled = p.parse_args(['a.ifc','b.ifc','--material','X','--save-audit','--save-reports'])
        self.assertTrue(enabled.save_audit and enabled.save_reports)
        disabled = p.parse_args(['a.ifc','b.ifc','--material','X','--no-audit','--no-reports'])
        self.assertTrue(disabled.no_audit and disabled.no_reports)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            p.parse_args(['a.ifc','b.ifc','--material','X','--save-audit','--no-audit'])

    def test_audit_only_cli_does_not_require_output_filename(self):
        with patch.object(cli, 'export_ifc', return_value={'dry_run':True}) as exported:
            result = cli.main(['source.ifc','--material','Concrete','--dry-run'])
        self.assertEqual(result, {'dry_run':True})
        self.assertEqual(exported.call_args.args[1], 'source_filtered.ifc')
        self.assertTrue(exported.call_args.kwargs['dry_run'])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(['source.ifc','--material','Concrete'])

    def test_m2_version_centralized(self):
        self.assertEqual(__version__, '1.5.6.1')
        engine = (ROOT / 'filter_engine.py').read_text(encoding='utf-8')
        app = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn("'application_version': __version__", engine)
        self.assertIn("self.title(f'IFC Material Filter v{__version__}')", app)

    def test_m3_selection_and_engine_reports_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            stem = Path(tmp) / 'model_filtered'
            select_csv = stem.with_suffix('.selection.timing.csv')
            engine_csv = stem.with_suffix('.timing.csv')
            sel = PerformanceLog(lambda _: None, label='selection')
            with sel.stage('02b Validate original IFC baseline'):
                pass
            sel.finish(select_csv)
            eng = PerformanceLog(lambda _: None, label='batch')
            with eng.stage('B02 Remove products'):
                pass
            eng.finish(engine_csv)
            self.assertNotEqual(select_csv, engine_csv)
            self.assertTrue(select_csv.with_suffix('.metrics.csv').exists())
            self.assertTrue(engine_csv.with_suffix('.metrics.csv').exists())
            with select_csv.open(encoding='utf-8-sig') as f:
                stages = [r['stage'] for r in csv.DictReader(f)]
            self.assertIn('02b Validate original IFC baseline', stages)
            with engine_csv.open(encoding='utf-8-sig') as f:
                stages = [r['stage'] for r in csv.DictReader(f)]
            self.assertIn('B02 Remove products', stages)
            self.assertNotIn('02b Validate original IFC baseline', stages)
            self.assertIn("dst.with_suffix('.selection.timing.csv')",
                          (ROOT/'filter_engine.py').read_text(encoding='utf-8'))

    def test_m5_gui_distinguishes_audit_only(self):
        app = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn("Audit completed — no IFC exported.", app)
        self.assertIn("if not outfile and self.dryvar.get():", app)
        self.assertIn("if audit_only:", app)

    def test_m6_unused_validation_parameter_removed(self):
        self.assertNotIn('opening_ids', inspect.signature(validate_extraction).parameters)

    def test_m6_placement_translation_uses_project_unit_tolerance(self):
        base = [[1,0,0,0.0],[0,1,0,0.0],[0,0,1,0.0],[0,0,0,1]]
        close = [[1,0,0,0.00009],[0,1,0,0.0],[0,0,1,0.0],[0,0,0,1]]
        far = [[1,0,0,0.00011],[0,1,0,0.0],[0,0,1,0.0],[0,0,0,1]]
        self.assertTrue(_placements_equivalent(base, close, 0.0001))
        self.assertFalse(_placements_equivalent(base, far, 0.0001))
        self.assertFalse(_placements_equivalent(base, close, 0.00001))
        self.assertTrue(_placements_equivalent(None, None, 0.0001))
        self.assertFalse(_placements_equivalent(None, base, 0.0001))

    def test_m6_orientation_not_measured_in_length_units(self):
        base = [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
        changed = [[1,0.000001,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
        self.assertFalse(_placements_equivalent(base, changed, 0.1))

    def test_m9_and_m11_gui_and_manual_workflow(self):
        app = (ROOT/'app.py').read_text(encoding='utf-8')
        self.assertNotIn("self.materials.insert('1.0', 'Stahlbeton Schweiz", app)
        self.assertIn('One per line or separated by semicolons.', app)
        workflow = (ROOT/'.github/workflows/build-windows.yml').read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch:', workflow)
        self.assertNotIn('  push:', workflow)


if __name__ == '__main__':
    unittest.main()

class CountingTests(unittest.TestCase):
    def test_m7_uses_model_length_without_iterating(self):
        from batch_export import count_unreachable_entities
        class Model:
            def __len__(self):
                return 10
            def __iter__(self):
                raise AssertionError('Should not iterate six million entities')
        self.assertEqual(count_unreachable_entities(Model(), {1,2,3}), 7)

    def test_m7_falls_back_on_iterable_without_len(self):
        from batch_export import count_unreachable_entities
        class Entity:
            def __init__(self, eid): self.eid = eid
            def id(self): return self.eid
        class Model:
            def __iter__(self):
                return iter([Entity(1),Entity(2),Entity(3)])
        self.assertEqual(count_unreachable_entities(Model(), {1,3}), 1)

    def test_m7_len_raises_typeerror_and_iteration_fallback_succeeds(self):
        from batch_export import count_unreachable_entities
        class Entity:
            def __init__(self, eid): self.eid = eid
            def id(self): return self.eid
        class Model:
            def __len__(self):
                raise TypeError('object of type file has no len()')
            def __iter__(self):
                return iter((Entity(11), Entity(22), Entity(33)))
        self.assertEqual(count_unreachable_entities(Model(), {11, 33}), 1)

    @unittest.skipUnless(__import__('importlib').util.find_spec('ifcopenshell'),
                         'Requires IfcOpenShell on GitHub Windows runner')
    def test_m7_ifcopenshell_fallback_matches_actual_step_records(self):
        import ifcopenshell
        from batch_export import count_unreachable_entities
        model = ifcopenshell.file(schema='IFC4')
        a = model.create_entity('IfcCartesianPoint', Coordinates=(0.0, 0.0, 0.0))
        model.create_entity('IfcCartesianPoint', Coordinates=(2.0, 0.0, 0.0))
        # IfcOpenShell 0.8.5 file objects are iterable but have no __len__.
        # Check the actual diagnostic count instead of assuming a length API.
        reachable = {a.id()}
        expected = sum(1 for entity in model if entity.id() not in reachable)
        self.assertEqual(expected, 1)
        self.assertEqual(count_unreachable_entities(model, reachable), expected)
