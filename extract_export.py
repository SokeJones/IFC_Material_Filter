"""IfcPatch extraction + conservative structural verification for IFC Material Filter.

No deletion is performed on the source graph. Selection query consists only of
known GlobalIDs; IfcPatch's ExtractElements constructs the new document.
"""
from __future__ import annotations

from pathlib import Path


def selection_query(globalids: set[str]) -> str:
    """IfcOpenShell selector accepts comma-separated 22-character GlobalIDs."""
    if not globalids:
        raise ValueError('No matching elements: refusing to export an empty IFC.')
    invalid = [s for s in globalids if len(s) != 22 or not all(c.isalnum() or c in '_$' for c in s)]
    if invalid:
        raise ValueError(f'Invalid IFC GlobalID: {invalid[0]!r}')
    return ', '.join(sorted(globalids))


def extract_selected(model, input_path: str, requested: set[str], notify=print):
    """Return separate model containing selected GUIDs via documented IfcPatch recipe."""
    import ifcpatch
    query = selection_query(requested)
    notify(f'Extracting {len(requested):,} GlobalIDs with IfcPatch ExtractElements...')
    return ifcpatch.execute({
        'input': input_path,
        'file': model,
        'recipe': 'ExtractElements',
        'arguments': [query, False],  # do not merge assets by name
    })


def strip_unselected_assembly_geometry(output, selected_ids: set[str], notify=print):
    """IfcPatch may retain assembly parents; leave them as hierarchy-only shells.

    Never remove spatial objects or selected products. No graph deletion here.
    """
    cleared = []
    for element in output.by_type('IfcElement'):
        if element.GlobalId not in selected_ids and element.is_a('IfcProduct'):
            # An unselected IfcOpeningElement is handled separately by validation.
            if element.is_a('IfcOpeningElement'):
                continue
            if element.Representation is not None:
                element.Representation = None
                cleared.append(element.GlobalId)
    if cleared:
        notify(f'Removed geometry references from {len(cleared):,} unselected assembly/support elements')
    return cleared


def validate_extraction(output, original_schema: str, expected_ids: set[str],
                        opening_ids: set[str] | None = None):
    """Check preservation and selection isolation; does not prove geometric identity."""
    if output.schema.upper() != original_schema.upper():
        raise RuntimeError(f'IFC schema changed: {original_schema} -> {output.schema}')
    by_gid = {e.GlobalId: e for e in output.by_type('IfcElement')}
    present = set(by_gid)
    missing = expected_ids - present
    if missing:
        raise RuntimeError(f'{len(missing)} required GlobalIDs missing; example: {sorted(missing)[0]}')
    unexpected = present - expected_ids
    for gid in unexpected:
        elem = by_gid[gid]
        if elem.is_a('IfcOpeningElement'):
            # ExtractElements may rebuild needed openings used for voids.
            continue
        if elem.Representation is not None:
            raise RuntimeError(f'Unexpected physical element has geometry: {elem.is_a()} {gid}')
    missing_geometry = [gid for gid in expected_ids if by_gid[gid].Representation is None]
    return {
        'selected_count': len(expected_ids),
        'physical_count': len(by_gid),
        'nonselected_shells_or_openings': len(unexpected),
        'selected_without_representation': missing_geometry,
        'output_geometry_refs': sum(e.Representation is not None for e in by_gid.values()),
    }


def export_and_validate(model, input_path: str, output_path: Path,
                        expected_ids: set[str], opening_ids: set[str], notify=print):
    import ifcopenshell
    import ifcpatch
    dest = Path(output_path)
    temp = dest.with_name(dest.stem + '.incomplete.ifc')
    if temp.exists():
        raise FileExistsError(f'Temporary output exists: {temp}')
    original_schema = model.schema
    # Include openings to preserve voids even if they have no matching material.
    # This avoids relying on recipe-specific implicit opening behaviour.
    extract_ids = expected_ids | opening_ids
    output = extract_selected(model, input_path, extract_ids, notify)
    strip_unselected_assembly_geometry(output, extract_ids, notify)
    notify('Writing new IFC model (not deleting elements from the original)...')
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        ifcpatch.write(output, str(temp))
        notify('Reopening and validating extracted IFC...')
        check = ifcopenshell.open(str(temp))
        if check is None:
            raise RuntimeError('Could not reopen exported IFC')
        report = validate_extraction(check, original_schema, extract_ids, opening_ids)
        # Require selected geometric elements to keep their representation reference.
        source_represented = {
            e.GlobalId for e in model.by_type('IfcElement')
            if e.GlobalId in extract_ids and e.Representation is not None
        }
        lost = source_represented & set(report['selected_without_representation'])
        if lost:
            raise RuntimeError(f'{len(lost)} selected elements lost their geometry. Example: {sorted(lost)[0]}')
        temp.replace(dest)
        return report
    except Exception:
        notify(f'Export was not finalised; partial file (if any) at {temp}')
        raise
