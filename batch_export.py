"""EXPERIMENTAL: IFC subset by editing source graph and reclaiming orphan subgraphs.

Uses v1.1 relationship-safe removal to avoid the shared property-set crash.
Then computes forward reachability from retained project, elements and live
relationships. Stream-prunes unreachable STEP entities (including geometry)
from a temporary serialization. No per-resource model.remove loop.
Never operate on the same file object as the reference extraction engine.
This engine requires independent comparison before production use.
"""
from __future__ import annotations
from collections import deque, Counter
from reachability_diagnostics import ReachabilityDiagnostics
from pathlib import Path
import json


def _same_entity(value, target):
    return hasattr(value, 'id') and value.id() == target


def detach_and_remove_product(model, product):
    """Adapted from proven v1.1: repair relationships without deleting shared assets."""
    pid = product.id()
    for inverse in list(model.get_inverse(product)):
        if not inverse.is_a('IfcRelationship'):
            raise RuntimeError(
                f'Unexpected inverse from #{inverse.id()} {inverse.is_a()} to '
                f'#{pid} {product.is_a()} ({getattr(product, "GlobalId", "")}); '
                'batch engine aborted safely.')
        remove_relation = False
        changes = []
        for index, value in enumerate(inverse):
            if _same_entity(value, pid):
                remove_relation = True
                break
            if isinstance(value, (tuple, list)):
                filtered = tuple(x for x in value if not _same_entity(x, pid))
                if len(filtered) != len(value):
                    if not filtered:
                        remove_relation = True
                        break
                    changes.append((index, filtered))
        if remove_relation:
            model.remove(inverse)
        else:
            for index, val in changes:
                inverse[index] = val
    if list(model.get_inverse(product)):
        raise RuntimeError(f'Unexpected remaining inverses for #{pid}')
    model.remove(product)


def forward_refs(entity):
    """IFC entity references in forward attributes, not inverse attributes."""
    for value in entity:
        if hasattr(value, 'is_a'):
            yield value
        elif isinstance(value, (list, tuple)):
            for child in value:
                if hasattr(child, 'is_a'):
                    yield child



def _space_ancestor_storey(space):
    """Find an existing storey in the spatial decomposition chain, never guess one."""
    pending = [space]
    seen = set()
    while pending:
        current = pending.pop()
        if current.id() in seen:
            continue
        seen.add(current.id())
        if current.is_a('IfcBuildingStorey'):
            return current
        for rel in getattr(current, 'Decomposes', ()) or ():
            parent = getattr(rel, 'RelatingObject', None)
            if parent is not None:
                pending.append(parent)
    return None


def remove_unselected_spaces(model, notify=print):
    """Discard material-unselected IfcSpace objects, keeping retained contents located.

    Selected elements spatially contained in a space are reattached to the
    actual ancestor storey; a missing storey aborts rather than inventing one.
    Space boundaries/room metadata are intentionally discarded.
    """
    spaces = list(model.by_type('IfcSpace'))
    moved = 0
    repaired = 0
    for space in spaces:
        containing = [r for r in model.get_inverse(space)
                      if r.is_a('IfcRelContainedInSpatialStructure')
                      and getattr(r, 'RelatingStructure', None) == space]
        if containing:
            storey = _space_ancestor_storey(space)
            if storey is None:
                raise RuntimeError(
                    f'Cannot remove IfcSpace {space.GlobalId}: contains elements '
                    'but has no ancestor IfcBuildingStorey. Export safely aborted.')
            from placement_repair import capture_world_placements, repair_reparented_placements
            # Capture the actual global placement *before* the space is removed.
            # Merely changing containment retains possibly invalid PlacementRelTo
            # references to the discarded space's IfcLocalPlacement.
            affected = {e.id(): e for rel in containing for e in rel.RelatedElements}
            snapshots = capture_world_placements(model, affected.values())
            for rel in containing:
                rel.RelatingStructure = storey
                moved += len(rel.RelatedElements)
            repaired += repair_reparented_placements(model, snapshots)
        detach_and_remove_product(model, space)
    if spaces:
        notify(f'Discarded {len(spaces):,} unselected IfcSpace objects; '
               f'reparented {moved:,} spatially contained element references; '
               f'rebuilt {repaired:,} placement(s)')
    return len(spaces), moved


def _geometry_roots_of_retained(model, keep_guids):
    """Direct product geometry plus type geometry, excluding other products."""
    roots = []
    for element in model.by_type('IfcElement'):
        if element.GlobalId not in keep_guids:
            continue
        shape = element.Representation
        if shape is not None:
            roots.append(shape)
        for rel in getattr(element, 'IsTypedBy', ()) or ():
            typ = getattr(rel, 'RelatingType', None)
            if typ is not None:
                roots.extend(getattr(typ, 'RepresentationMaps', ()) or ())
        # IFC2X3 type association may use IsDefinedBy instead of IsTypedBy.
        for rel in getattr(element, 'IsDefinedBy', ()) or ():
            if rel.is_a('IfcRelDefinesByType'):
                typ = rel.RelatingType
                roots.extend(getattr(typ, 'RepresentationMaps', ()) or ())
    return roots


def restrict_presentation_layers(model, keep_guids, notify=print):
    """Prevent shared presentation layers reconnecting removed geometry.

    Only layer assignments to geometric objects in retained element/type
    representation trees remain. Original geometry objects are not modified.
    """
    permitted = reachable_ids(_geometry_roots_of_retained(model, keep_guids))
    changed = removed_items = kept_items = 0
    for layer in model.by_type('IfcPresentationLayerAssignment'):
        items = tuple(layer.AssignedItems or ())
        selected = tuple(item for item in items if item.id() in permitted)
        removed_items += len(items) - len(selected)
        kept_items += len(selected)
        if len(selected) != len(items):
            # IFC layer AssignedItems is SET [1:?], so an empty assignment
            # must not be serialized. Delete empty layers; the STREAM prune
            # will remove any orphaned style resources.
            if selected:
                layer.AssignedItems = selected
            else:
                refs = list(model.get_inverse(layer))
                if refs:
                    raise RuntimeError(
                        f'Cannot discard empty presentation layer #{layer.id()}: '
                        f'it is referenced by {len(refs)} other IFC records')
                model.remove(layer)
            changed += 1
    notify(f'Presentation layer clipping: {changed:,} modified/removed layers, '
           f'{removed_items:,} discarded assignments, {kept_items:,} retained assignments')
    return changed, removed_items, kept_items

def live_roots(model, keep_guids):
    """Select primary roots; relationships resolved by inverse-aware traversal."""
    roots = []
    roots.extend(model.by_type('IfcProject'))
    roots.extend(e for e in model.by_type('IfcSpatialStructureElement')
                 if not e.is_a('IfcSpace'))
    roots.extend(e for e in model.by_type('IfcElement') if e.GlobalId in keep_guids)
    return roots


def reachable_ids(roots, model=None, diagnostics=None, notify=None):
    """Preserve v1.4.3 reachability semantics, optionally record bounded diagnostics.

    A diagnostic edge records how an object was FIRST discovered, not all
    the possible paths to it. No material/resource inverse traversal is added.
    """
    seen = set()
    tracing = diagnostics is not None and diagnostics.enabled
    if tracing:
        roots = list(roots)
        for obj in roots:
            diagnostics.root(obj)
        pending = deque((obj, 'root', '') for obj in roots)
    else:
        pending = deque(roots)
    while pending:
        if tracing:
            obj, inbound, source_class = pending.pop()
        else:
            obj = pending.pop()
        oid = obj.id()
        if oid <= 0:
            if tracing:
                diagnostics.transient_entity()
                pending.extend((child, 'forward_transient', obj.is_a()) for child in forward_refs(obj))
            else:
                pending.extend(forward_refs(obj))
            continue
        if oid in seen:
            continue
        seen.add(oid)
        if tracing:
            diagnostics.visited_entity(obj, inbound, source_class)
            if notify is not None and len(seen) % 500000 == 0:
                notify(f'Reachability scanned {len(seen):,} STEP entities; '
                       f'inverse-discovered {diagnostics.ingress["inverse_relationship"]:,}')
            cls = obj.is_a()
            pending.extend((child, 'forward_reference', cls) for child in forward_refs(obj))
        else:
            pending.extend(forward_refs(obj))
        if model is not None:
            if obj.is_a('IfcObjectDefinition') or obj.is_a('IfcTypeObject'):
                allowed_inverse = ('IfcRelationship',)
            elif obj.is_a('IfcRepresentationItem') or obj.is_a('IfcRepresentation'):
                allowed_inverse = ('IfcStyledItem', 'IfcPresentationLayerAssignment',
                                   'IfcPresentationLayerWithStyle')
            elif obj.is_a('IfcMaterial'):
                allowed_inverse = ('IfcMaterialDefinitionRepresentation',)
            else:
                allowed_inverse = ()
            if allowed_inverse:
                by_class = Counter() if tracing else None
                count = 0
                for inverse in model.get_inverse(obj):
                    if any(inverse.is_a(typ) for typ in allowed_inverse):
                        if tracing:
                            pending.append((inverse, 'inverse_relationship', obj.is_a()))
                            by_class[inverse.is_a()] += 1
                            count += 1
                        else:
                            pending.append(inverse)
                if tracing:
                    diagnostics.inverse_traversal(obj, count, by_class)
    return seen

def batch_filter(model, retained_guids: set[str], support_guids: set[str],
                 notify=print, timings=None, diagnostics=None):
    from contextlib import nullcontext
    def timed(label):
        return timings.stage(label) if timings else nullcontext()
    desired = retained_guids | support_guids
    with timed('B01 Invert selection and snapshot products'):
        elements = list(model.by_type('IfcElement'))
        to_remove_ids = [e.id() for e in elements if e.GlobalId not in desired]
        removed_count = len(to_remove_ids)
        if timings: timings.count('batch_elements_to_remove', removed_count)
    with timed('B02 Remove products / repair relationship membership'):
        for i, eid in enumerate(to_remove_ids, 1):
            try:
                product = model.by_id(eid)
            except RuntimeError:
                continue
            if product is not None:
                detach_and_remove_product(model, product)
            if i % 5000 == 0:
                notify(f'Batch engine detached {i:,} / {removed_count:,} elements')
    with timed('B03 Clear nonselected assembly geometries'):
        cleared = 0
        for obj in model.by_type('IfcElement'):
            if obj.GlobalId not in retained_guids and not obj.is_a('IfcOpeningElement'):
                if obj.Representation is not None:
                    obj.Representation = None
                    cleared += 1
        if timings: timings.count('batch_assembly_representations_cleared', cleared)
    with timed('B03a Remove non-matching spaces / preserve containment'):
        removed_spaces, moved_contents = remove_unselected_spaces(model, notify)
        if timings:
            timings.count('batch_spaces_removed', removed_spaces)
            timings.count('batch_space_contents_reparented', moved_contents)
    with timed('B03b Clip presentation layers to surviving geometry'):
        layers_changed, assignments_dropped, assignments_kept = restrict_presentation_layers(
            model, desired, notify)
        if timings:
            timings.count('batch_layers_clipped', layers_changed)
            timings.count('batch_layer_assignments_removed', assignments_dropped)
            timings.count('batch_layer_assignments_kept', assignments_kept)
    with timed('B04 Build live root and reachability index'):
        roots = live_roots(model, desired)
        reachable = reachable_ids(roots, model, diagnostics=diagnostics, notify=notify)
        if 0 in reachable:
            raise AssertionError("Non-serialized STEP #0 entered reachability set")
        if timings:
            timings.count('batch_live_roots', len(roots))
            timings.count('batch_reachable_step_entities', len(reachable))
    with timed('B05 Count unreachable resources'):
        # Do NOT create millions of entity wrappers or call remove() for each.
        # We instead serialize the edited model and stream-prune the remaining
        # unreachable STEP records. This also avoids model.unbatch() rewriting
        # millions of records without any progress events.
        unreach_count = sum(1 for entity in model if entity.id() not in reachable)
        if timings: timings.count('batch_orphan_step_entities', unreach_count)
        notify(f'Unreachable STEP records: {unreach_count:,}')
    return {'removed_products': removed_count, 'orphan_records': unreach_count,
            'reachable_entity_ids': reachable,
            'remaining_elements': len(model.by_type('IfcElement')),
            'removed_spaces': removed_spaces,
            'reparented_spatial_contents': moved_contents,
            'layer_assignments_removed': assignments_dropped}


def export_batch(model, output_path: Path, expected_ids, opening_ids, source_represented,
                 notify=print, timings=None, validation='full', reachability_diagnostics=True, save_reports=True):
    import ifcopenshell
    from extract_export import validate_extraction
    from validation_v14 import full_validate
    from contextlib import nullcontext
    out = Path(output_path)
    temp = out.with_name(out.stem + '.incomplete.ifc')
    if temp.exists():
        raise FileExistsError(f'Temporary output already exists: {temp}')
    def timed(label):
        return timings.stage(label) if timings else nullcontext()
    reachability_diagnostics = bool(reachability_diagnostics and save_reports)
    reach_diag = ReachabilityDiagnostics(enabled=reachability_diagnostics)
    with timed('B00 Filter source graph'):
        stats = batch_filter(model, expected_ids, opening_ids, notify, timings, reach_diag)
    # Important: file.write() creates the STEP serialization without mutating
    # or deleting millions of entity records. The streaming pass copies only
    # records in the live graph, removing unused geometry/resources quickly.
    from step_prune import prune_serialized_ifc
    raw = out.with_name(out.stem + '.unpruned.incomplete.ifc')
    if raw.exists():
        raise FileExistsError(f'Unpruned temporary output already exists: {raw}')
    reachable = stats.pop('reachable_entity_ids')
    if reachability_diagnostics:
        diagnostic_path = out.with_suffix('.reachability.json')
        reach_diag.save(diagnostic_path)
        notify(f'Reachability diagnostic: {diagnostic_path}')
        stats['reachability_diagnostics'] = str(diagnostic_path)
    try:
        with timed('B06 Serialize edited IFC for streaming cleanup'):
            model.write(str(raw))
        with timed('B07 Stream-prune unreachable STEP records'):
            try:
                pruned = prune_serialized_ifc(raw, temp, reachable, notify,
                                              class_report=out.with_suffix('.step_classes.csv') if save_reports else None)
            except RuntimeError:
                # Diagnose the missing ID against the actual edited IFC graph.
                diag = temp.with_suffix('.step_prune_diagnostics.json')
                if diag.exists():
                    data = json.loads(diag.read_text(encoding='utf-8'))
                    descriptions = []
                    for eid in data.get('missing_ids', []):
                        try:
                            entity = model.by_id(int(eid))
                            descriptions.append({
                                'step_id': eid,
                                'ifc_class': entity.is_a(),
                                'global_id': getattr(entity, 'GlobalId', None),
                                'inverse_references': len(model.get_inverse(entity)),
                            })
                        except (RuntimeError, TypeError, ValueError) as exc:
                            descriptions.append({'step_id': eid, 'lookup_error': str(exc)})
                    data['missing_entity_details'] = descriptions
                    diag.write_text(json.dumps(data, indent=2), encoding='utf-8')
                    notify(f'STEP pruning diagnostic: {diag}')
                    notify(f'Missing entity details: {descriptions[:5]}')
                raise
            if timings:
                timings.count('batch_records_written', pruned['records_kept'])
                timings.count('batch_records_pruned', pruned['records_removed'])
                timings.count('batch_unpruned_bytes', pruned['input_bytes'])
                timings.count('batch_pruned_bytes', pruned['output_bytes'])
        raw.unlink(missing_ok=True)
        if save_reports:
            stats['step_class_report'] = str(out.with_suffix('.step_classes.csv'))
        with timed('B08 Reopen batch output'):
            reopened = ifcopenshell.open(str(temp))
        with timed('B09 Validate selected IDs, schema, geometry references'):
            report = validate_extraction(reopened, model.schema, expected_ids | opening_ids, opening_ids)
            lost = source_represented & set(report['selected_without_representation'])
            if lost:
                raise RuntimeError(f'{len(lost)} retained elements lost representations; e.g. {sorted(lost)[0]}')
        if validation == 'full':
            with timed('B10 IFC schema validation'):
                report.update(full_validate(reopened, notify))
            # Record exact problematic placements and references. We do not
            # claim source/output error parity solely from error counts.
            from validation_v146 import orphan_placement_diagnostics
            details = orphan_placement_diagnostics(reopened)
            report['orphan_local_placements'] = len(details['orphan_placements'])
            if save_reports:
                details_path = out.with_suffix('.placement_diagnostics.json')
                details_path.write_text(json.dumps(details, indent=2), encoding='utf-8')
                report['placement_diagnostics'] = str(details_path)
            notify(f'Orphan placement diagnostics: {len(details["orphan_placements"]):,} findings')
        with timed('B11 Finalize batch output'):
            temp.replace(out)
        report.update(stats)
        return report
    except Exception:
        notify(f'Batch export failed: temporary artifact may remain at {temp} or {raw}; final output was not replaced')
        raise
