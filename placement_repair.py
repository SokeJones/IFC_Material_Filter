"""Conservative placement repair using documented IfcOpenShell operations.

Rebuild retained products' local placements after spatial reparenting while
requesting exactly the previous global transform. Do not alter the source IFC.
"""
from __future__ import annotations


def _world_placement_si(model, placement):
    """Global transform in metres (supported IfcOpenShell 0.8.5 APIs).

    get_local_placement yields a world matrix in IFC project units; the edit
    API with is_si=True needs only the translation converted to metres.
    """
    import ifcopenshell.util.placement
    import ifcopenshell.util.unit
    matrix = ifcopenshell.util.placement.get_local_placement(placement).copy()
    matrix[:3, 3] *= ifcopenshell.util.unit.calculate_unit_scale(model)
    return matrix


def capture_world_placements(model, elements):
    return [(element, _world_placement_si(model, element.ObjectPlacement))
            for element in elements if getattr(element, 'ObjectPlacement', None) is not None]


def repair_reparented_placements(model, snapshots, tolerance=1e-7, parents=None):
    """Use documented API to rebuild placement against the new container.

    Fail if the global position changes; never silently accept movement.
    Returns the number of updated product placements.
    """
    import numpy as np
    import ifcopenshell.api.geometry
    changed = 0
    parents = parents or {}
    for element, old in snapshots:
        if not element.is_a('IfcProduct'):
            raise ValueError('Only product placements can be repaired')
        ifcopenshell.api.geometry.edit_object_placement(
            model, product=element, matrix=old, is_si=True,
            should_transform_children=False)
        current = _world_placement_si(model, element.ObjectPlacement)
        if not np.allclose(old, current, rtol=0, atol=tolerance):
            raise RuntimeError(f'Placement moved after reassignment: {element.GlobalId}')
        target = parents.get(element.id())
        if target is not None:
            # Spatial membership and ObjectPlacement.PlacementRelTo are distinct.
            # Editing the world transform alone does not prove reparenting.
            parent_placement = getattr(target, 'ObjectPlacement', None)
            placement = getattr(element, 'ObjectPlacement', None)
            # Storeys without a placement are legal: the element's new local
            # placement must then be absolute (PlacementRelTo=None).
            if placement is None or placement.PlacementRelTo != parent_placement:
                raise RuntimeError(
                    f'Placement parent mismatch for {element.GlobalId}: '
                    'expected direct relative placement to ancestor storey; '
                    'export safely aborted.')
        changed += 1
    return changed
