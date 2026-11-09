"""Conservative placement repair after spatial containment reparenting.

World-space transformations are captured before removing spaces. When a new
storey parent is specified, the relative axis placement is rebuilt directly:
this avoids an IFC2X3 owner-history requirement in the geometry API and makes
the intended PlacementRelTo explicit. The original global matrix is verified.
"""
from __future__ import annotations


def _world_placement_si(model, placement):
    """Global transform in metres using IfcOpenShell 0.8.5 APIs."""
    import ifcopenshell.util.placement
    import ifcopenshell.util.unit
    matrix = ifcopenshell.util.placement.get_local_placement(placement).copy()
    matrix[:3, 3] *= ifcopenshell.util.unit.calculate_unit_scale(model)
    return matrix


def capture_world_placements(model, elements):
    return [(element, _world_placement_si(model, element.ObjectPlacement))
            for element in elements if getattr(element, 'ObjectPlacement', None) is not None]


def _explicitly_reparent(model, element, original_world_si, parent_placement):
    """Rebuild a local placement relative to parent_placement, preserving world pose.

    IfcLocalPlacement.PlacementRelTo and RelativePlacement are an independent
    graph from IfcRelContainedInSpatialStructure; editing containment alone
    does not guarantee the former is updated. Use standard IFC2X3/IFC4
    IfcAxis2Placement3D and a matrix computed in *project units*.
    """
    import numpy as np
    import ifcopenshell.util.placement
    import ifcopenshell.util.unit

    placement = element.ObjectPlacement
    if placement is None or not placement.is_a('IfcLocalPlacement'):
        raise RuntimeError(f'Unsupported placement while reparenting {element.GlobalId}')

    # A shared placement must not be mutated because this would move objects
    # that were not part of the reparenting plan.
    shared = [obj for obj in model.get_inverse(placement)
              if obj.is_a('IfcProduct') and obj.id() != element.id()
              and getattr(obj, 'ObjectPlacement', None) == placement]
    if shared:
        raise RuntimeError(f'Shared local placement for {element.GlobalId}; '
                           'cannot safely reparent without affecting other products.')

    scale = ifcopenshell.util.unit.calculate_unit_scale(model)
    original_project = original_world_si.copy()
    original_project[:3, 3] /= scale
    parent_world = (ifcopenshell.util.placement.get_local_placement(parent_placement)
                    if parent_placement is not None else np.eye(4))
    relative = np.linalg.solve(parent_world, original_project)

    origin = tuple(float(v) for v in relative[:3, 3])
    x = np.array(relative[:3, 0], dtype=float)
    z = np.array(relative[:3, 2], dtype=float)
    if np.linalg.norm(x) < 1e-12 or np.linalg.norm(z) < 1e-12:
        raise RuntimeError(f'Degenerate placement axes for {element.GlobalId}')
    x /= np.linalg.norm(x)
    z /= np.linalg.norm(z)
    z /= np.linalg.norm(z)
    x -= np.dot(x, z) * z
    if np.linalg.norm(x) < 1e-12:
        raise RuntimeError(f'Invalid placement orientation for {element.GlobalId}')
    x /= np.linalg.norm(x)

    axis = model.createIfcAxis2Placement3D(
        model.createIfcCartesianPoint(origin),
        model.createIfcDirection(tuple(float(v) for v in z)),
        model.createIfcDirection(tuple(float(v) for v in x)))
    placement.PlacementRelTo = parent_placement
    placement.RelativePlacement = axis


def repair_reparented_placements(model, snapshots, tolerance=1e-7, parents=None):
    """Reparent placements and verify world transform and placement parent.

    An actual placement-parent mismatch is repaired, not just detected.
    Unhandled placements and numerically changed placements fail closed.
    """
    import numpy as np
    import ifcopenshell.api.geometry

    changed = 0
    parents = parents or {}
    for element, old in snapshots:
        if not element.is_a('IfcProduct'):
            raise ValueError('Only product placements can be repaired')
        target = parents.get(element.id())
        if target is not None:
            # A containment change does not update the independent placement
            # hierarchy. Reconstruct the relative placement directly: the
            # geometry API may require an IFC2X3 owner user/history and may
            # retain the previous PlacementRelTo even when it succeeds.
            parent_placement = getattr(target, 'ObjectPlacement', None)
            _explicitly_reparent(model, element, old, parent_placement)
            placement = element.ObjectPlacement
            if placement is None or placement.PlacementRelTo != parent_placement:
                raise RuntimeError(f'Placement parent mismatch for {element.GlobalId}; '
                                   'export safely aborted.')
        else:
            # Preserve the previous behavior for callers not specifying a
            # new spatial parent; it is not part of the space-removal path.
            ifcopenshell.api.geometry.edit_object_placement(
                model, product=element, matrix=old, is_si=True,
                should_transform_children=False)
        current = _world_placement_si(model, element.ObjectPlacement)
        if not np.allclose(old, current, rtol=0, atol=tolerance):
            raise RuntimeError(f'Placement moved after reassignment: {element.GlobalId}')
        changed += 1
    return changed
