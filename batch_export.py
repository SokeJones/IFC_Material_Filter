"""EXPERIMENTAL: IFC subset by editing source graph and reclaiming orphan subgraphs.

Uses v1.1 relationship-safe removal to avoid the shared property-set crash.
Then computes forward reachability from retained project, elements and live
relationships. Stream-prunes unreachable STEP entities (including geometry)
from a temporary serialization. No per-resource model.remove loop.
Never operate on the same file object as the reference extraction engine.
This engine requires independent comparison before production use.
"""
from __future__ import annotations
from collections import deque
from pathlib import Path


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


def live_roots(model, keep_guids):
    """Select primary roots; relationships resolved by inverse-aware traversal."""
    roots = []
    roots.extend(model.by_type('IfcProject'))
    roots.extend(model.by_type('IfcSpatialStructureElement'))
    roots.extend(e for e in model.by_type('IfcElement') if e.GlobalId in keep_guids)
    return roots


def reachable_ids(roots, model=None):
    """Forward reachability plus relationships attached to live objects/types.

    IFC relationship entities are stored on the inverse side of an element,
    hence a forward-only traversal would drop material/type/pset relationships.
    Conversely, traversing inverses on a shared IfcMaterial can pull in huge
    unrelated portions of the model: never do that.
    """
    seen = set()
    pending = deque(roots)
    while pending:
        obj = pending.pop()
        oid = obj.id()
        if oid in seen:
            continue
        seen.add(oid)
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
                for inverse in model.get_inverse(obj):
                    if any(inverse.is_a(typ) for typ in allowed_inverse):
                        pending.append(inverse)
    return seen

def batch_filter(model, retained_guids: set[str], support_guids: set[str],
                 notify=print, timings=None):
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
    with timed('B04 Build live root and reachability index'):
        roots = live_roots(model, desired)
        reachable = reachable_ids(roots, model)
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
            'remaining_elements': len(model.by_type('IfcElement'))}


def export_batch(model, output_path: Path, expected_ids, opening_ids, source_represented,
                 notify=print, timings=None, validation='full'):
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
    with timed('B00 Filter source graph'):
        stats = batch_filter(model, expected_ids, opening_ids, notify, timings)
    # Important: file.write() creates the STEP serialization without mutating
    # or deleting millions of entity records. The streaming pass copies only
    # records in the live graph, removing unused geometry/resources quickly.
    from step_prune import prune_serialized_ifc
    raw = out.with_name(out.stem + '.unpruned.incomplete.ifc')
    if raw.exists():
        raise FileExistsError(f'Unpruned temporary output already exists: {raw}')
    reachable = stats.pop('reachable_entity_ids')
    try:
        with timed('B06 Serialize edited IFC for streaming cleanup'):
            model.write(str(raw))
        with timed('B07 Stream-prune unreachable STEP records'):
            pruned = prune_serialized_ifc(raw, temp, reachable, notify)
            if timings:
                timings.count('batch_records_written', pruned['records_kept'])
                timings.count('batch_records_pruned', pruned['records_removed'])
                timings.count('batch_unpruned_bytes', pruned['input_bytes'])
                timings.count('batch_pruned_bytes', pruned['output_bytes'])
        raw.unlink(missing_ok=True)
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
        with timed('B11 Finalize batch output'):
            temp.replace(out)
        report.update(stats)
        return report
    except Exception:
        notify(f'Batch export failed: temporary artifact may remain at {temp} or {raw}; final output was not replaced')
        raise
