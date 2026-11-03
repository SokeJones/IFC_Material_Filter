"""Material-based IFC subset export using IfcOpenShell.

Material names: case-insensitive exact matches (trimmed), OR across requested names.
Parent aggregation/nesting material is a heuristic, not normative IFC inheritance.
"""
from __future__ import annotations

import csv
from collections import Counter, deque
from pathlib import Path
from typing import Callable


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
    from safe_remove import detach_and_remove_product
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
    notify(f'Loading model: {src.name}')
    model = ifcopenshell.open(str(src))
    if model is None:
        raise ValueError('IfcOpenShell could not read this IFC file')
    notify(f'IFC schema: {model.schema}')
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

    matched_cache = {}
    def matches(e):
        eid = e.id()
        if eid not in matched_cache:
            root, source = material_state(e)
            matched_cache[eid] = find_matching_materials([root], wanted) if root is not None else set()
        return matched_cache[eid]

    composition_parents = {}
    all_parents = {}
    permitted = {'IfcRelAggregates'} if parent_mode != 'none' else set()
    if parent_mode == 'aggregates+nests':
        permitted.add('IfcRelNests')
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
    counts = Counter()
    rows = []
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

    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [
            'global_id','ifc_class','name','decision','reason','matched_materials','parent_global_id','parent_distance'])
        writer.writeheader()
        writer.writerows(rows)
    notify(f'Audit CSV: {audit}')
    if dry_run:
        notify('Dry run finished; no IFC was written.')
        return {'selected': len(selected), 'total': len(elements), 'counts': dict(counts), 'audit': str(audit)}

    # Snapshot expected element GUIDs BEFORE the output write. Do not access
    # entity handles from elements that have already been deleted.
    expected_ids = {r['global_id'] for r in rows if r['decision'] == 'KEEP'}
    allowed_ids = expected_ids | {e.GlobalId for e in elements if e.id() in (shells | opening_ids)}

    # Avoid api.root.remove_product on large models: recursive pset deletion can
    # dereference already-removed/shared property sets. Safely detach the
    # product from IFC relationships, then delete ONLY the product entity.
    # Orphaned non-product resources may remain, but other products' shared
    # properties and representations are untouched.
    unwanted = [e.id() for e in elements if e.id() not in keep_ids]
    notify(f'Removing {len(unwanted):,} unselected elements...')
    for index, eid in enumerate(unwanted, 1):
        try:
            e = model.by_id(eid)
        except RuntimeError:
            continue
        if e is not None:
            try:
                detach_and_remove_product(model, e)
            except Exception as exc:
                raise RuntimeError(
                    f'Failed while removing IFC product #{eid} '
                    f'({e.is_a()}, GlobalId={e.GlobalId}): {exc}'
                ) from exc
        if index % 2000 == 0:
            notify(f'Removed {index:,} / {len(unwanted):,}')
    for sid in shells:
        try:
            shell = model.by_id(sid)
        except RuntimeError:
            continue
        if shell and shell.is_a('IfcProduct'):
            shell.Representation = None
    # Output write to a temporary path to avoid presenting a partially written file.
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.with_name(dst.stem + '.incomplete.ifc')
    if temp.exists():
        raise FileExistsError(f'Temporary file already exists: {temp}')
    notify('Writing filtered IFC...')
    try:
        model.write(str(temp))
        notify('Reopening export for validation...')
        verified = ifcopenshell.open(str(temp))
        actual = {e.GlobalId for e in verified.by_type('IfcElement')}
        missing = expected_ids - actual
        if missing:
            raise RuntimeError(f'Export validation failed: {len(missing)} selected elements missing. Example: {next(iter(missing))}')
        unexpected = actual - allowed_ids
        if unexpected:
            raise RuntimeError(f'Export validation failed: {len(unexpected)} unexpected physical elements remain')
        temp.replace(dst)
    except Exception:
        notify(f'Output was not finalised; diagnostic temp file (if present): {temp}')
        raise
    notify(f'Success. Filtered IFC: {dst}')
    notify(f'Output physical elements: {len(actual):,}; selected: {len(selected):,}; parent shells: {len(shells):,}; support openings: {len(opening_ids):,}')
    notify('NOTE: This checks relationships and presence of entities, not rendered geometry.')
    return {'selected':len(selected), 'total':len(elements), 'counts':dict(counts), 'output':str(dst), 'audit':str(audit)}
