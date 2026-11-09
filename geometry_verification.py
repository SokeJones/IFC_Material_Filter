"""Independent, opt-in geometry/placement comparison using supported IfcOpenShell APIs.

Two IFCs are opened sequentially to avoid keeping the large source graph and the
filtered graph in memory together. A geometry signature is a set of quantized
world-space triangles (including multiplicities), independent of mesh ordering.
Unsupported or failed triangulation is reported as UNVERIFIED, never PASS.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import gc
import hashlib
import json
import math


def _quantize(v, tolerance):
    return tuple(int(round(float(x) / tolerance)) for x in v)


def mesh_signature(vertices, faces, tolerance=0.0001):
    """Hash a triangle multiset with vertices in global project units.

    Unit convention is controlled by IfcOpenShell's geometry engine; callers
    use the same settings for both IFC files. This is a tessellated comparison,
    not a mathematical CAD BREP equality proof.
    """
    pts = [_quantize(vertices[i:i+3], tolerance) for i in range(0, len(vertices), 3)]
    triangles = []
    for i in range(0, len(faces), 3):
        triangle = tuple(sorted((pts[faces[i]], pts[faces[i+1]], pts[faces[i+2]])))
        triangles.append(triangle)
    digest = hashlib.sha256()
    for tri in sorted(triangles):
        digest.update(repr(tri).encode('ascii'))
        digest.update(b'\n')
    return {'triangle_count': len(triangles), 'vertex_count': len(pts),
            'triangle_hash': digest.hexdigest()}


def _placement_signature(product):
    import ifcopenshell.util.placement
    placement = getattr(product, 'ObjectPlacement', None)
    if placement is None:
        return None
    # Preserve the actual matrix: per-element quantization introduces false
    # differences at rounding boundaries. Compare corresponding components
    # numerically using the user-selected project-unit tolerance instead.
    matrix = ifcopenshell.util.placement.get_local_placement(placement)
    return [[float(value) for value in row] for row in matrix]


def _placements_equivalent(a, b, tolerance):
    """Compare world placement without rounding-boundary false mismatches.

    The translation column is measured in project length units, whereas
    orientation/matrix values are dimensionless. Relative tolerance is zero:
    large global coordinates must not conceal a small but real displacement.
    """
    if a is None or b is None:
        return a is None and b is None
    if len(a) != len(b):
        return False
    for row_index, (ra, rb) in enumerate(zip(a, b)):
        if len(ra) != len(rb):
            return False
        for col_index, (va, vb) in enumerate(zip(ra, rb)):
            component_tolerance = tolerance if col_index == 3 and row_index < 3 else 1e-8
            if not math.isclose(float(va), float(vb), rel_tol=0,
                                abs_tol=component_tolerance):
                return False
    return True


def _scan_model(path, guids, tolerance, notify):
    import ifcopenshell
    import ifcopenshell.geom
    model = ifcopenshell.open(str(path))
    if model is None:
        raise RuntimeError(f'Unable to open IFC: {path}')
    settings = ifcopenshell.geom.settings()
    settings.set('use-world-coords', True)
    # Disable opening subtraction only if explicitly requested in a future API.
    # Both source and output always use the same triangulation settings.
    result = {}
    for i, guid in enumerate(sorted(guids), 1):
        try:
            product = model.by_guid(guid)
        except RuntimeError:
            product = None
        if product is None:
            result[guid] = {'status':'MISSING'}
            continue
        rec = {'status':'UNVERIFIED', 'ifc_class':product.is_a(),
               'placement':_placement_signature(product)}
        if getattr(product, 'Representation', None) is None:
            rec['status'] = 'NO_REPRESENTATION'
        else:
            try:
                shape = ifcopenshell.geom.create_shape(settings, product)
                geometry = shape.geometry
                if not geometry.verts or not geometry.faces:
                    rec['reason'] = 'Triangulation returned no triangles'
                else:
                    rec.update(mesh_signature(geometry.verts, geometry.faces, tolerance))
                    rec['status'] = 'OK'
            except Exception as exc:
                rec['reason'] = f'{type(exc).__name__}: {str(exc)[:300]}'
        result[guid] = rec
        if i % 250 == 0:
            notify(f'Geometry check {Path(path).name}: {i:,} / {len(guids):,}')
    del model
    gc.collect()
    return result


def compare_geometry(source, filtered, report_path=None, tolerance=0.0001, notify=print):
    """Compare each output IfcElement against the original IFC by GlobalID.

    Geometry is compared only when BOTH models successfully triangulate.
    Unsupported geometry is explicitly listed as unverified. No output IFC
    is modified. Full precision/identity of CAD surfaces is not asserted.
    """
    source = Path(source)
    filtered = Path(filtered)
    if tolerance <= 0 or not math.isfinite(tolerance):
        raise ValueError('Geometry tolerance must be finite and positive')
    if source.resolve() == filtered.resolve():
        raise ValueError('Source and filtered IFC must be different files')
    import ifcopenshell
    model = ifcopenshell.open(str(filtered))
    selected = {p.GlobalId for p in model.by_type('IfcElement')}
    del model
    gc.collect()
    notify(f'Comparing geometry for {len(selected):,} output elements')
    original = _scan_model(source, selected, tolerance, notify)
    output = _scan_model(filtered, selected, tolerance, notify)
    failures = []
    unverified = []
    verified = 0
    no_repr = 0
    for guid in sorted(selected):
        a, b = original[guid], output[guid]
        if a['status'] == 'MISSING':
            failures.append({'global_id':guid, 'reason':'Missing in source'})
        elif a.get('ifc_class') != b.get('ifc_class'):
            failures.append({'global_id':guid, 'reason':'IFC class changed'})
        elif not _placements_equivalent(a.get('placement'), b.get('placement'), tolerance):
            failures.append({'global_id':guid, 'reason':'Global placement matrix changed', 'source_placement':a.get('placement'), 'output_placement':b.get('placement')})
        elif a['status'] == 'OK' and b['status'] == 'OK':
            if a['triangle_hash'] != b['triangle_hash']:
                failures.append({'global_id':guid, 'reason':'World-space triangles differ',
                                 'source_triangles':a['triangle_count'], 'output_triangles':b['triangle_count']})
            else:
                verified += 1
        elif a['status'] == 'NO_REPRESENTATION' and b['status'] == 'NO_REPRESENTATION':
            no_repr += 1
        else:
            unverified.append({'global_id':guid, 'source_status':a['status'],
                               'output_status':b['status'], 'source_reason':a.get('reason'),
                               'output_reason':b.get('reason')})
    report = {'source':str(source), 'filtered':str(filtered), 'tolerance_project_units':tolerance,
              'elements_checked':len(selected), 'geometry_verified':verified,
              'both_without_representation':no_repr,
              'geometry_unverified':len(unverified), 'mismatches':len(failures),
              'passed':not failures and not unverified,
              'caveat':'World-space tessellation comparison in IFC project length units, not proof of exact BREP equivalence. Translation tolerance uses the requested project units; orientation tolerance is 1e-8 dimensionless. Compare only same project-unit models.',
              'failures':failures, 'unverified':unverified}
    report_path = Path(report_path) if report_path else filtered.with_suffix('.geometry_comparison.json')
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    notify(f'Geometry comparison: {verified:,} verified, {len(failures):,} differences, '
           f'{len(unverified):,} unverified; saved {report_path}')
    return report


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Compare filtered IFC world geometry against source')
    ap.add_argument('source')
    ap.add_argument('filtered')
    ap.add_argument('--tolerance-project-units', type=float, default=0.0001)
    args = ap.parse_args()
    result = compare_geometry(args.source, args.filtered, tolerance=args.tolerance_project_units)
    raise SystemExit(0 if result['passed'] else 2)
