"""Optional, read-only material-equivalence check for retained IFC elements.

Uses IfcOpenShell's supported util.element.get_material(should_inherit=...) to
resolve occurrence and type materials. Material-root graphs are compared by
attribute values, not volatile STEP entity IDs. Source and output are opened
sequentially to limit peak memory. No source or filtered IFC is modified.
"""
from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path


def _value_signature(value, active=None):
    """Normalize material definitions and their constituent settings deterministically.

    Cycles are marked rather than recursively expanded. STEP IDs are omitted.
    IFC attribute names and values remain significant; references to type,
    profile and material definition objects are compared structurally too.
    """
    if active is None:
        active = set()
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return {'nonfinite_float': str(value)}
        return value
    if isinstance(value, (tuple, list)):
        return [_value_signature(item, active) for item in value]
    if hasattr(value, 'is_a'):
        # IFC simple/defined typed values may have is_a but no numeric STEP id.
        try:
            step = value.id()
        except (AttributeError, TypeError, RuntimeError):
            step = None
        if step and step in active:
            return {'cyclic_reference': value.is_a()}
        if step:
            active.add(step)
        try:
            attributes = {}
            for i, member in enumerate(value):
                try:
                    attr = value.attribute_name(i)
                except (AttributeError, RuntimeError):
                    attr = str(i)
                attributes[attr] = _value_signature(member, active)
            return {'ifc_class': value.is_a(), 'attributes': attributes}
        finally:
            if step:
                active.discard(step)
    return str(value)


def effective_material(element, get_material, cache=None):
    """Return effective direct/type material with canonical, ID-independent data."""
    direct = get_material(element, should_inherit=False)
    if direct is not None:
        root, origin = direct, 'direct'
    else:
        root = get_material(element, should_inherit=True)
        origin = 'type' if root is not None else 'none'
    if root is None:
        return {'origin': origin, 'material': None}
    # Repeated elements commonly share the same root; no need to normalize again.
    key = (root.is_a(), root.id())
    if cache is not None and key in cache:
        signature = cache[key]
    else:
        signature = _value_signature(root)
        if cache is not None:
            cache[key] = signature
    return {'origin': origin, 'material': signature}


def _scan(path, guids, notify):
    import ifcopenshell
    import ifcopenshell.util.element
    model = ifcopenshell.open(str(path))
    if model is None:
        raise RuntimeError(f'Cannot open IFC: {path}')
    material_cache = {}
    records = {}
    for index, guid in enumerate(sorted(guids), 1):
        try:
            element = model.by_guid(guid)
        except RuntimeError:
            element = None
        if element is None or not element.is_a('IfcElement'):
            records[guid] = {'status': 'MISSING_OR_NOT_ELEMENT'}
        else:
            try:
                state = effective_material(element, ifcopenshell.util.element.get_material, material_cache)
                records[guid] = {'status': 'OK', 'ifc_class': element.is_a(), **state}
            except Exception as error:
                records[guid] = {'status': 'UNVERIFIED', 'reason': f'{type(error).__name__}: {error}'}
        if index % 1000 == 0:
            notify(f'Material check {Path(path).name}: {index:,} / {len(guids):,}')
    del model
    gc.collect()
    return records


def compare_materials(source, filtered, report_path=None, notify=print):
    """Compare material definitions of every output IfcElement with source.

    The subset is intentionally output elements only. Selection correctness is
    established separately by the filtering audit and structural parity check.
    """
    source = Path(source)
    filtered = Path(filtered)
    if source.resolve() == filtered.resolve():
        raise ValueError('Original and filtered IFC must be different files')
    if not source.is_file() or not filtered.is_file():
        raise FileNotFoundError('Both IFC files must exist')
    import ifcopenshell
    model = ifcopenshell.open(str(filtered))
    if model is None:
        raise RuntimeError('Filtered IFC could not be opened')
    output_elements = model.by_type('IfcElement')
    guids = {element.GlobalId for element in output_elements}
    if len(guids) != len(output_elements):
        raise ValueError('Output contains duplicate IfcElement GlobalIDs')
    del model, output_elements
    gc.collect()
    notify(f'Comparing material assignments for {len(guids):,} retained elements')
    original = _scan(source, guids, notify)
    result = _scan(filtered, guids, notify)
    differences = []
    unverified = []
    matching = 0
    no_material_both = 0
    for guid in sorted(guids):
        a, b = original[guid], result[guid]
        if a['status'] != 'OK' or b['status'] != 'OK':
            unverified.append({'global_id': guid, 'source': a, 'output': b})
        elif a['ifc_class'] != b['ifc_class']:
            differences.append({'global_id': guid, 'reason': 'IFC class differs',
                                'source_class': a['ifc_class'], 'output_class': b['ifc_class']})
        elif a['origin'] != b['origin'] or a['material'] != b['material']:
            differences.append({'global_id': guid, 'reason': 'Effective material differs',
                                'source': {'origin': a['origin'], 'material': a['material']},
                                'output': {'origin': b['origin'], 'material': b['material']}})
        else:
            matching += 1
            if a['material'] is None:
                no_material_both += 1
    report = {
        'source': str(source), 'filtered': str(filtered),
        'elements_checked': len(guids), 'material_equivalent': matching,
        'both_without_effective_material': no_material_both,
        'material_mismatches': len(differences), 'material_unverified': len(unverified),
        'passed': not differences and not unverified,
        'scope': 'All retained IfcElement GlobalIDs; effective direct/type material and nested definition attributes. No assertion about removed elements, material style inverses, or composition-parent selection reasons.',
        'caveat': 'Compares effective IfcOpenShell material definitions and assignment origin; STEP IDs ignored. Does not prove complete IFC semantic equivalence.',
        'differences': differences, 'unverified': unverified,
    }
    dest = Path(report_path) if report_path else filtered.with_suffix('.material_comparison.json')
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    notify(f'Material comparison: {matching:,} equivalent; {len(differences):,} mismatches; '
           f'{len(unverified):,} unverified. Report: {dest}')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Optional IFC material assignment comparison')
    parser.add_argument('source')
    parser.add_argument('filtered')
    args = parser.parse_args()
    summary = compare_materials(args.source, args.filtered)
    raise SystemExit(0 if summary['passed'] else 2)
