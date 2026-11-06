"""Headless frozen-executable smoke test for the Windows GitHub Actions runner."""
from pathlib import Path
from tempfile import TemporaryDirectory


def run_selftest():
    import ifcopenshell
    import ifcopenshell.guid
    from filter_engine import export_ifc

    with TemporaryDirectory(prefix='ifc_filter_selftest_') as tmp:
        src = Path(tmp) / 'source.ifc'
        dst = Path(tmp) / 'result.ifc'
        f = ifcopenshell.file(schema='IFC4')
        f.create_entity('IfcProject', GlobalId=ifcopenshell.guid.new(), Name='Smoke test')
        concrete = f.create_entity('IfcMaterial', Name='Concrete')
        steel = f.create_entity('IfcMaterial', Name='Steel')
        wall_keep = f.create_entity('IfcWall', GlobalId=ifcopenshell.guid.new(), Name='Keep')
        wall_drop = f.create_entity('IfcWall', GlobalId=ifcopenshell.guid.new(), Name='Drop')
        f.create_entity('IfcRelAssociatesMaterial', GlobalId=ifcopenshell.guid.new(),
                        RelatedObjects=[wall_keep], RelatingMaterial=concrete)
        f.create_entity('IfcRelAssociatesMaterial', GlobalId=ifcopenshell.guid.new(),
                        RelatedObjects=[wall_drop], RelatingMaterial=steel)
        f.write(str(src))
        report = export_ifc(str(src), str(dst), 'Concrete', engine='batch',
                            validation='basic', save_audit=False, save_reports=False,
                            notify=lambda message: None)
        assert dst.is_file() and dst.stat().st_size > 0, 'No filtered IFC produced'
        result = ifcopenshell.open(str(dst))
        ids = {e.GlobalId for e in result.by_type('IfcElement')}
        assert ids == {wall_keep.GlobalId}, f'Wrong filtered IDs: {ids}'
        assert report['selected'] == 1, 'Wrong selection count'
        artifacts = sorted(path.name for path in Path(tmp).iterdir() if path.name != src.name)
        assert artifacts == [dst.name], f'Unexpected artifacts: {artifacts}'

    # Visible on CI console for a normal Python run; windowed EXE uses exit code.
    return True
