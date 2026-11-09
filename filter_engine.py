"""Material-based IFC extraction using IfcOpenShell and IfcPatch.

Material names: case-sensitive exact matches (trimmed), OR across requested names.
Parent aggregation/nesting material is a heuristic, not normative IFC inheritance.
"""
from __future__ import annotations

import csv
import json
import traceback
from difflib import get_close_matches
from collections import Counter, deque
from pathlib import Path
from typing import Callable
from performance import PerformanceLog
from validation_v14 import full_validate
from version import __version__


def parse_materials(value: str | list[str]) -> list[str]:
    """Accept newline/semicolon-delimited names; commas remain legal within names."""
    if isinstance(value, str):
        chunks = value.replace(';', '\n').splitlines()
    else:
        # CLI argparse action="append" produces a list. Split each entry
        # just like the multiline GUI input, preserving OR semantics.
        chunks = [part for item in value for part in item.replace(';', '\n').splitlines()]
    result, seen = [], set()
    for item in chunks:
        name = item.strip()
        if name and name not in seen:
            result.append(name)
            seen.add(name)
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
            if name in wanted:
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


def ensure_unique_element_globalids(elements):
    """Require unambiguous IFC element identity before any export."""
    seen = set()
    for element in elements:
        gid = element.GlobalId
        if gid in seen:
            raise ValueError(
                f'Duplicate IfcElement.GlobalId {gid!r} in source IFC. '
                'Filtering aborted; correct duplicate element identifiers in the source model.')
        seen.add(gid)


def _material_suggestions(requested, available_names):
    """Exact-case suggestions first; case-insensitive fuzzy lookup second.

    Suggestions are advisory only: they never broaden material selection.
    """
    available = sorted({(name or '').strip() for name in available_names if (name or '').strip()},
                       key=lambda name: (name.casefold(), name))
    casing = [name for name in available if name.casefold() == requested.casefold() and name != requested]
    if casing:
        return casing[:3]
    folded = {name.casefold() for name in available}
    nearby = set(get_close_matches(requested.casefold(), sorted(folded), n=3, cutoff=0.6))
    return [name for name in available if name.casefold() in nearby][:3]


def assess_selection(selected, rows, wanted_names, available_names, notify=print):
    """Fail on no matches; warn about partial *case-sensitive* mismatches."""
    available = list(available_names)
    if not selected:
        examples = []
        for requested in wanted_names:
            suggestions = _material_suggestions(requested, available)
            if suggestions:
                examples.append(f'{requested!r}: {", ".join(suggestions)}')
        raise ValueError('No IFC elements match any requested material (case-sensitive). '
                         'No filtered IFC was written. Check spelling and capitalization.'
                         + (f' Similar material names: {"; ".join(examples)}' if examples else ''))
    matched = {name for row in rows
               for name in row['matched_materials'].split('; ') if name}
    unmatched = [name for name in wanted_names if name not in matched]
    if unmatched:
        details = []
        for requested in unmatched:
            suggestions = _material_suggestions(requested, available)
            details.append(requested + (f' (possible match: {", ".join(suggestions)})' if suggestions else ''))
        notify('WARNING: The following requested materials did not select any elements '
               '(case-sensitive): ' + '; '.join(details)
               + '. Export will include only the matching materials.')
    return unmatched


def export_ifc(input_path: str, output_path: str, materials: str | list[str],
               parent_mode: str = 'aggregates', audit_path: str | None = None,
               dry_run: bool = False, notify: Callable[[str], None] = print,
               engine: str = 'batch', validation: str = 'basic',
               save_audit: bool = False, save_reports: bool = False):
    import ifcopenshell
    from extract_export import export_and_validate
    from batch_export import export_batch
    import ifcopenshell.util.element

    wanted_names = parse_materials(materials)
    if not wanted_names:
        raise ValueError('Enter at least one material name.')
    wanted = set(wanted_names)
    if engine not in ('both', 'ifcpatch', 'batch'):
        raise ValueError('Invalid engine mode')
    if validation not in ('full', 'basic'):
        raise ValueError('Invalid validation mode')
    if parent_mode not in ('none', 'aggregates', 'aggregates+nests'):
        raise ValueError('Invalid parent mode')

    src = Path(input_path).resolve()
    dst = Path(output_path).resolve()
    audit = Path(audit_path).resolve() if audit_path else dst.with_suffix('.audit.csv')
    if not src.is_file():
        raise FileNotFoundError(str(src))
    if len({src, dst, audit}) != 3:
        raise ValueError('Input, output, and audit must be different paths.')
    outputs = output_paths(dst, engine)
    if not dry_run:
        existing = [path for path in outputs.values() if path.exists()]
        if existing:
            raise FileExistsError(f'Output already exists: {existing[0]}')
        # Check stale temporary files before loading an expensive model.
        temporary = [temporary_path for engine_name, path in outputs.items()
                     for temporary_path in ((path.with_name(path.stem + '.incomplete.ifc'),)
                         + ((path.with_name(path.stem + '.unpruned.incomplete.ifc'),)
                            if engine_name == 'batch' else ()))
                     if temporary_path.exists()]
        if temporary:
            raise FileExistsError('Stale temporary IFC exists: ' + str(temporary[0])
                                  + '. Move or delete it before filtering.')
    perf = PerformanceLog(notify, label='selection')
    try:
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
        ensure_unique_element_globalids(elements)
        perf.count('source_file_bytes', src.stat().st_size)
        source_element_count = len(elements)
        perf.count('source_elements', source_element_count)
        source_validation = None
        if validation == 'full' and not dry_run:
            with perf.stage('02b Validate original IFC baseline'):
                source_validation = full_validate(model, notify)

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
        unmatched_materials = assess_selection(selected, rows, wanted_names,
                          ((m.Name or '') for m in model.by_type('IfcMaterial')), notify)
        perf.count('selected_elements', len(selected))
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

        # M5: The optional audit must describe the final retained IFC elements,
        # not just the material-selection stage. A support shell/opening is
        # retained even if it would not independently match the materials.
        # Keep the original selection counts and KEEP-only expected_ids intact.
        row_by_guid = {row['global_id']: row for row in rows}
        for eid in shells - selected:
            row = row_by_guid[elem_by_id[eid].GlobalId]
            row['decision'], row['reason'] = 'KEEP_SUPPORT', 'support_shell'
        for eid in opening_ids - selected:
            row = row_by_guid[elem_by_id[eid].GlobalId]
            row['decision'], row['reason'] = 'KEEP_SUPPORT', 'support_opening'

        if save_audit or dry_run:
            with perf.stage('06 Write audit CSV'):
                audit.parent.mkdir(parents=True, exist_ok=True)
                with audit.open('w', newline='', encoding='utf-8-sig') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [
                        'global_id','ifc_class','name','decision','reason','matched_materials','parent_global_id','parent_distance'])
                    writer.writeheader()
                    writer.writerows(rows)
            notify(f'Audit CSV: {audit}')
        # Keep the selection/baseline-validation timings separate from the
        # engine timings in single-engine mode (m3). Neither CSV overwrites
        # another; reporting remains entirely opt-in.
        timing_path = dst.with_suffix('.selection.timing.csv')
        if dry_run:
            perf.finish(timing_path if save_reports else None)
            notify('Audit completed; no IFC was exported.')
            return {'selected': len(selected), 'total': source_element_count,
                    'counts': dict(counts), 'unmatched_materials': unmatched_materials,
                'audit': str(audit), 'timing': str(timing_path) if save_reports else None,
                'dry_run': True}

        # Common selection shared between both engines. Each engine has an isolated
        # output file and timing log. Batch reads a separate IFC instance.
        expected_ids = {r['global_id'] for r in rows if r['decision'] == 'KEEP'}
        support_openings = {elem_by_id[i].GlobalId for i in opening_ids if i in elem_by_id}
        support_shells = {elem_by_id[i].GlobalId for i in shells if i in elem_by_id}
        source_represented.update(elem_by_id[i].GlobalId for i in opening_ids
                                  if i in elem_by_id and elem_by_id[i].Representation is not None)
        perf.count('support_openings', len(support_openings))
        perf.count('support_shells', len(support_shells))
        perf.finish(timing_path if save_reports else None)
        results = {}
        errors = {}
        comparison_file = dst.with_suffix('.comparison.json')
        for name, target_path in outputs.items():
            eng_perf = PerformanceLog(notify, label=name)
            eng_perf.count('selected_elements', len(expected_ids))
            eng_perf.count('input_bytes', src.stat().st_size)
            notify(f'==== {name.upper()} ENGINE ====')
            try:
                if name == 'ifcpatch':
                    report = export_and_validate(model, str(src), target_path,
                                                 expected_ids, support_openings, notify,
                                                 timings=eng_perf, source_represented=source_represented,
                                                 validation=validation)
                else:
                    with eng_perf.stage('B-0 Release reference/selection model memory'):
                        import gc
                        material_cache.clear()
                        material_root_matches.clear()
                        composition_parents.clear()
                        all_parents.clear()
                        elem_by_id.clear()
                        elements.clear()
                        del model
                        gc.collect()
                    with eng_perf.stage('B-1 Reopen independent source IFC'):
                        batch_model = ifcopenshell.open(str(src))
                        if batch_model is None:
                            raise RuntimeError('Unable to open independent IFC instance for batch engine')
                    report = export_batch(batch_model, target_path, expected_ids,
                                          support_openings | support_shells,
                                          source_represented, notify, timings=eng_perf,
                                          validation=validation, save_reports=save_reports)
                    del batch_model
                eng_perf.count('output_bytes', target_path.stat().st_size)
                eng_perf.count('output_elements', report['physical_count'])
                results[name] = {'path': str(target_path), 'bytes': target_path.stat().st_size,
                                 'validation': report}
            except Exception as exc:
                errors[name] = traceback.format_exc()
                notify(f'{name} engine FAILED: {exc}')
                # Do not suppress error in single-engine mode.
            finally:
                results.setdefault(name, {})['timing'] = eng_perf.finish(
                    target_path.with_suffix('.timing.csv') if save_reports else None)
        # Write even on partial failure to keep successful reference output usable.
        comparison = {
            'application_version': __version__, 'engine_mode': engine,
            'validation_mode': validation, 'input': str(src),
            'materials': wanted_names, 'parent_mode': parent_mode,
            'selected_elements': len(expected_ids), 'support_shells': len(support_shells),
            'support_openings': len(support_openings), 'engines': results,
            'errors': errors,
            'source_validation': source_validation,
            'selection_timing': str(timing_path) if save_reports else None,
            }
        if engine == 'both' and all('path' in results.get(k, {}) for k in ('ifcpatch', 'batch')):
            ratio = results['batch']['bytes'] / max(results['ifcpatch']['bytes'], 1)
            comparison['batch_to_reference_size_ratio'] = ratio
            comparison['batch_size_warning'] = ratio > 1.5
            if ratio > 1.5:
                notify(f'WARNING: Batch output is {ratio:.2f}x IfcPatch size, not comparably compact.')
            with perf.stage('14 Compare engine outputs'):
                comparison['parity'] = compare_outputs(results['ifcpatch']['path'],
                                                        results['batch']['path'], expected_ids,
                                                        source_represented)
        if source_validation is not None:
            for engine_name, details in results.items():
                val = details.get('validation')
                if isinstance(val, dict) and 'schema_validation_errors' in val:
                    val['schema_errors_vs_source'] = (
                        val['schema_validation_errors'] - source_validation['schema_validation_errors'])
                    val['schema_validation_comparison_note'] = (
                        'Counts are not directly equivalent for different-sized IFC graphs. '
                        'Positive difference is a concern; a negative difference does not prove correctness. '
                        'Review error categories and examples separately.')
        if save_reports:
            comparison_file.parent.mkdir(parents=True, exist_ok=True)
            with comparison_file.open('w', encoding='utf-8') as f:
                json.dump(comparison, f, indent=2, ensure_ascii=False)
            notify(f'Comparison: {comparison_file}')
        if errors:
            details = f'Details in {comparison_file}' if save_reports else 'See processing log.'
            # Surface the actual engine exception rather than only 'engine failed'.
            engine_name, tb = next(iter(errors.items()))
            error_line = tb.strip().splitlines()[-1] if tb.strip() else 'Unknown error'
            raise RuntimeError(f'{engine_name} engine failed: {error_line}. {details}')
        if comparison.get('parity', {}).get('equivalent') is False:
            details = f'Inspect {comparison_file}' if save_reports else 'See processing log.'
            raise RuntimeError(f'Engine output mismatch; do not use Batch output without further review. {details}')
        return {'selected': len(selected), 'total': source_element_count, 'counts': dict(counts),
                'unmatched_materials': unmatched_materials,
                'audit': str(audit) if (save_audit or dry_run) else None,
                'comparison': str(comparison_file) if save_reports else None,
                'selection_timing': str(timing_path) if save_reports else None,
                'engines': results}

    finally:
        # Failure before the normal finish() must not leave the RSS sampler running.
        perf.stop_sampling()


def output_paths(path: Path, engine: str) -> dict[str, Path]:
    if engine == 'both':
        return {'ifcpatch': path.with_name(path.stem + '_ifcpatch.ifc'),
                'batch': path.with_name(path.stem + '_batch.ifc')}
    return {engine: path}


def compare_outputs(ref_path, trial_path, selected_ids, source_represented):
    """Structural parity check; geometric solids still require external comparison."""
    import ifcopenshell
    a = ifcopenshell.open(ref_path)
    b = ifcopenshell.open(trial_path)
    def snap(f):
        return {e.GlobalId: (e.is_a(), e.Representation is not None)
                for e in f.by_type('IfcElement')}
    sa, sb = snap(a), snap(b)
    differences = [gid for gid in selected_ids if sa.get(gid) != sb.get(gid)]
    extra_a = {gid for gid in sa if gid not in selected_ids and not a.by_guid(gid).is_a('IfcOpeningElement')}
    extra_b = {gid for gid in sb if gid not in selected_ids and not b.by_guid(gid).is_a('IfcOpeningElement')}
    # Support shells may differ as long as they have no geometry.
    invalid_extra_b = [g for g in extra_b if sb[g][1]]
    invalid_extra_a = [g for g in extra_a if sa[g][1]]
    good = not (differences or invalid_extra_a or invalid_extra_b)
    return {'equivalent': good, 'selected_class_representation_mismatches': differences[:30],
            'ifcpatch_extra_nonopening_count':len(extra_a),
            'batch_extra_nonopening_count':len(extra_b),
            'batch_unselected_with_geometry':invalid_extra_b[:30],
            'note':'Structural parity only; does not prove equal geometry solids or placements'}
