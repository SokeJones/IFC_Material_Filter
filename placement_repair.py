"""Conservative placement repair using documented IfcOpenShell operations.

Rebuild retained products' local placements after spatial reparenting while
requesting exactly the previous global transform. Do not alter the source IFC.
"""
from __future__ import annotations


def capture_world_placements(elements):
    import ifcopenshell.util.placement
    return [(element, ifcopenshell.util.placement.get_placement(
        element.ObjectPlacement, should_return_si=True).copy())
        for element in elements if getattr(element, 'ObjectPlacement', None) is not None]


def repair_reparented_placements(model, snapshots, tolerance=1e-7):
    """Use documented API to rebuild placement against the new container.

    Fail if the global position changes; never silently accept movement.
    Returns the number of updated product placements.
    """
    import numpy as np
    import ifcopenshell.api.geometry
    import ifcopenshell.util.placement
    changed = 0
    for element, old in snapshots:
        if not element.is_a('IfcProduct'):
            raise ValueError('Only product placements can be repaired')
        ifcopenshell.api.geometry.edit_object_placement(
            model, product=element, matrix=old, is_si=True,
            should_transform_children=False)
        current = ifcopenshell.util.placement.get_placement(
            element.ObjectPlacement, should_return_si=True)
        if not np.allclose(old, current, rtol=0, atol=tolerance):
            raise RuntimeError(f'Placement moved after reassignment: {element.GlobalId}')
        changed += 1
    return changed
