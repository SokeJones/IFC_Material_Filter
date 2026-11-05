"""Targeted validation evidence for orphan local placements."""

def orphan_placement_diagnostics(model, limit=500):
    errors = []
    total = 0
    for placement in model.by_type('IfcLocalPlacement'):
        # IFC2X3/IFC4 inverse cardinality is PlacesObject SET [1:1].
        products = tuple(getattr(placement, 'PlacesObject', ()) or ())
        if products:
            continue
        total += 1
        if len(errors) >= limit:
            continue
        children = list(getattr(placement, 'ReferencedByPlacements', ()) or ())
        errors.append({
            'step_id':placement.id(), 'places_object':0,
            'referenced_by_placements':[p.id() for p in children[:30]],
            'placement_rel_to':getattr(getattr(placement, 'PlacementRelTo', None), 'id', lambda:None)(),
        })
    return {'total_orphan_placements':total, 'truncated':total>limit,
            'orphan_placements':errors,
            'note':'Diagnostics only: orphan placements can occur in source IFCs; compare source and output before asserting introduced errors.'}
