"""Material-based IFC extraction using IfcOpenShell and IfcPatch.

Material names: case-insensitive exact matches (trimmed), OR across requested names.
Parent aggregation/nesting material is a heuristic, not normative IFC inheritance.
"""
from __future__ import annotations

import csv
from collections import Counter, deque
from pathlib import Path
from typing import Callable
from performance import PerformanceLog


def parse_materials(value: str | list[str]) -> list[str]:
    """Accept newline/semicolon-delimited names; commas remain legal within names."""
    if isinstance(value, str):
        chunks = value.replace(';', '\n').splitlines()
    else:
        chunks = value
    result, seen = [], set()
    for item in chunks:
        name = item.strip()
        if name and name.casefold() not in seen:
            result.append(name)
            seen.add(name.casefold())
    return result


def find_matching_materials(roots, wanted: set[str]):
    """Walk forward material subgraph; return all matching IfcMaterial names.

    A material layer set can hold multiple actual materials.
    """
    stack = list(roots)
    seen = set()
    found = set()
    while stack:
        entity = stack.pop()
        if entity is None or not hasattr(entity, 'is_a'):
            continue
        eid = entity.id()
        if eid in seen:
            continue
        seen.add(eid)
        kind = entity.is_a()
        if kind == 'IfcMaterial':
            name = (entity.Name or '').strip()
            if name.casefold() in wanted:
                found.add(name)
            continue
        if not kind.startswith('IfcMaterial'):
            continue
        for field in entity:
            if hasattr(field, 'is_a') and field.is_a().startswith('IfcMaterial'):
                stack.append(field)
            elif isinstance(field, (tuple, list)):
                stack.extend(x for x in field if hasattr(x, 'is_a') and x.is_a().startswith('IfcMaterial'))
    return found


def export_ifc(input_path: str, output_path: str, materials: str | list[str],
               parent_mode: str = 'aggregates', audit_path: str | None = None,
               dry_run: bool = False, notify: Callable[[str], None] = print):
    import ifcopenshell
    from extract_export import export_and_validate
    import ifcopenshell.util.element

    wanted_names = parse_materials(materials)
    if not wanted_names:
        raise ValueError('Enter at least one material name.')
    wanted = {name.casefold() for name in wanted_names}
    if parent_mode not in ('none', 'aggregates', 'aggregates+nests'):
        raise ValueError('Invalid parent mode')

    src = Path(input_path).resolve()
    dst = Path(output_path).resolve()
    audit = Path(audit_path).resolve() if audit_path else dst.with_suffix('.audit.csv')
    if not src.is_file():
        raise FileNotFoundError(str(src))
    if len({src, dst, audit}) != 3:
        raise ValueError('Input, output, and audit must be different paths.')
    if dst.exists() and not dry_run:
        raise FileExistsError(f'The output already exists: {dst}')
    perf = PerformanceLog(notify)
    notify(f'Loading model: {src.name}')
    with perf.stage('01 Open source IFC'):
        model = ifcopenshell.open(str(src))
    if model is None:
        raise ValueError('IfcOpenShell could not read this IFC file')
    notify(f'IFC schema: {model.schema}')
    with perf.stage('02 Index physical elements'):
        elements = list(model.by_type('IfcElement'))
        elem_by_id = {e.id(): e for e in elements}
    notify(f'Physical elements to evaluate: {len(elements):,}')

    # Retrieve effective material: occurrence-level association takes precedence over type.
    # IfcOpenShell's get_material() handles IFC2X3 and IFC4 type relationships.
    material_cache = {}
    def material_state(e):
        eid = e.id()
        if eid not in material_cache:
            direct = ifcopenshell.util.element.get_material(e, should_inherit=False)
            if direct is not None:
                root, source = direct, 'direct'
            else:
                root = ifcopenshell.util.element.get_material(e, should_inherit=True)
                source = 'type' if root is not None else 'none'
            material_cache[eid] = (root, source)
        return material_cache[eid]

    # Multiple occurrences often share a single material layer set or type material.
    # Cache by the material root entity rather than the occurrence to avoid
    # repeatedly traversing the same material subgraph thousands of times.
    material_root_matches = {}
    def matches(e):
        root, _ = material_state(e)
        if root is None:
            return set()
        rid = root.id()
        if rid not in material_root_matches:
            material_root_matches[rid] = find_matching_materials([root], wanted)
        return material_root_matches[rid]

    composition_parents = {}
    all_parents = {}
    permitted = {'IfcRelAggregates'} if parent_mode != 'none' else set()
    if parent_mode == 'aggregates+nests':
        permitted.add('IfcRelNests')
    with perf.stage('03 Build parent relationship index'):
        for relkind in ('IfcRelAggregates', 'IfcRelNests'):
            for rel in model.by_type(relkind):
                p = rel.RelatingObject
                for child in rel.RelatedObjects:
                    all_parents.setdefault(child.id(), []).append((p, relkind))
                    if relkind in permitted:
                        composition_parents.setdefault(child.id(), []).append((p, relkind))

    def matching_parent(e):
        queue = deque([(e.id(), 0)])
        seen = {e.id()}
        while queue:
            child_id, depth = queue.popleft()
            for parent, kind in composition_parents.get(child_id, ()):
                pid = parent.id()
                if pid in seen:
                    continue
                seen.add(pid)
                pmatches = matches(parent)
                if pmatches:
                    return parent, kind, depth + 1, pmatches
                # Conflicting parent assignment is a boundary, don't skip past it.
                if material_state(parent)[1] == 'none':
                    queue.append((pid, depth + 1))
        return None

    selected = set()
    source_represented = set()
    counts = Counter()
    rows = []
    with perf.stage('04 Material selection and audit rows'):
        for i, element in enumerate(elements, 1):
            root, source = material_state(element)
            own_match = matches(element)
            parent = None
            if own_match:
                reason = source
                matching_names = own_match
            elif root is not None:
                reason, matching_names = 'excluded_other_material', set()
            else:
                parent = matching_parent(element) if permitted else None
                if parent:
                    ancestor, kind, depth, matching_names = parent
                    reason = 'parent_aggregate' if kind == 'IfcRelAggregates' else 'parent_nest'
                else:
                    reason, matching_names = 'excluded_no_material', set()
            keep = not reason.startswith('excluded_')
            if keep:
                selected.add(element.id())
                if element.Representation is not None:
                    source_represented.add(element.GlobalId)
            counts[reason] += 1
            rows.append({
                'global_id': element.GlobalId,
                'ifc_class': element.is_a(),
                'name': element.Name or '',
                'decision': 'KEEP' if keep else 'REMOVE',
                'reason': reason,
                'matched_materials': '; '.join(sorted(matching_names)),
                'parent_global_id': parent[0].GlobalId if parent and hasattr(parent[0], 'GlobalId') else '',
                'parent_distance': parent[2] if parent else '',
            })
            if i % 20000 == 0:
                notify(f'Checked {i:,} / {len(elements):,} elements')
    notify('Selected: {:,} / {:,}'.format(len(selected), len(elements)))
    for key, count in sorted(counts.items()):
        notify(f'  {key}: {count:,}')

    # Parent shells preserve composition and placement for included descendants.
    # Structural supporting openings are also preserved to avoid filling holes.
    with perf.stage('05 Supporting assemblies and openings'):
        shells = set()
        for sid in list(selected):
            queue = deque([sid])
            seen = {sid}
            while queue:
                eid = queue.popleft()
                for ancestor, _ in all_parents.get(eid, ()):
                    aid = ancestor.id()
                    if aid in seen:
                        continue
                    seen.add(aid)
                    if aid in elem_by_id and aid not in selected:
                        shells.add(aid)
                    queue.append(aid)
        opening_ids = set()
        for rel in model.by_type('IfcRelVoidsElement'):
            if rel.RelatingBuildingElement.id() in selected or rel.RelatingBuildingElement.id() in shells:
                opening_ids.add(rel.RelatedOpeningElement.id())
        # Retain openings but never count them as selected physical-material elements.
        keep_ids = selected | shells | opening_ids

    with perf.stage('06 Write audit CSV'):
        audit.parent.mkdir(parents=True, exist_ok=True)
        with audit.open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [
                'global_id','ifc_class','name','decision','reason','matched_materials','parent_global_id','parent_distance'])
            writer.writeheader()
            writer.writerows(rows)
    notify(f'Audit CSV: {audit}')
    timing_path = dst.with_suffix('.timing.csv')
    if dry_run:
        perf.save(timing_path)
        notify('Dry run finished; no IFC was written.')
        return {'selected': len(selected), 'total': len(elements), 'counts': dict(counts), 'audit': str(audit), 'timing': str(timing_path)}

    # IfcPatch constructs a fresh IFC model from requested GlobalIDs. This avoids
    # the orphaned geometry and property assets left behind in v1.1's deletion approach.
    expected_ids = {r['global_id'] for r in rows if r['decision'] == 'KEEP'}
    support_openings = {elem_by_id[i].GlobalId for i in opening_ids if i in elem_by_id}
    source_represented.update(elem_by_id[i].GlobalId for i in opening_ids if i in elem_by_id and elem_by_id[i].Representation is not None)
    try:
        validation = export_and_validate(model, str(src), dst, expected_ids, support_openings, notify,
                                         timings=perf, source_represented=source_represented)
    finally:
        perf.save(timing_path)
    notify(f'Success. Extracted IFC: {dst} ({dst.stat().st_size / (1024**2):.2f} MiB)')
    notify(f'Validated selected elements: {validation["selected_count"]:,}')
    notify(f'Extra assembly shells/openings: {validation["nonselected_shells_or_openings"]:,}')
    notify('NOTE: Geometry references checked; full visual and geometry equivalence still requires viewer verification.')
    return {'selected':len(selected), 'total':len(elements), 'counts':dict(counts),
            'output':str(dst), 'audit':str(audit), 'timing':str(timing_path), 'validation':validation}
