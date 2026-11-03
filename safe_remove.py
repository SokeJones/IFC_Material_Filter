"""Remove unwanted IFC products without IfcOpenShell's cascading pset deletion.

This intentionally leaves orphaned representations/property definitions in the STEP
file (they are not visible as products), prioritising stable entity references.
Relation memberships are repaired before deleting the product. If a non-relationship
entity points to the product, fail explicitly rather than writing a broken IFC.
"""


def _same_entity(value, target_id):
    return hasattr(value, 'id') and value.id() == target_id


def detach_and_remove_product(model, product):
    """Remove one product and repair its direct IfcRelationship inverses.

    Unlike api.root.remove_product, does not recursively remove property sets,
    geometry, styles or placements which may be shared by surviving elements.
    """
    pid = product.id()
    inverses = list(model.get_inverse(product))
    for inverse in inverses:
        # We are not allowed to introduce a null in a mandatory non-relationship
        # attribute. The input must be investigated instead.
        if not inverse.is_a('IfcRelationship'):
            raise RuntimeError(
                f'Cannot safely delete #{pid} ({product.is_a()}): '
                f'non-relationship #{inverse.id()} ({inverse.is_a()}) references it.'
            )

        changes = []
        delete_relation = False
        for index, value in enumerate(inverse):
            if _same_entity(value, pid):
                # Single-valued mandatory links such as RelatingObject or
                # RelatingBuildingElement: the relationship has no meaning.
                delete_relation = True
                break
            if isinstance(value, (tuple, list)):
                filtered = [v for v in value if not _same_entity(v, pid)]
                if len(filtered) != len(value):
                    if not filtered:
                        delete_relation = True
                        break
                    changes.append((index, tuple(filtered)))
        if delete_relation:
            model.remove(inverse)
        else:
            for index, filtered in changes:
                inverse[index] = filtered

    # Verify no unexpected inverse references remain. This prevents broken STEP
    # references and catches any unhandled IFC relationship structures.
    remaining = list(model.get_inverse(product))
    if remaining:
        examples = ', '.join(f'#{x.id()} {x.is_a()}' for x in remaining[:4])
        raise RuntimeError(f'Cannot safely delete product #{pid}: inverse references remain: {examples}')
    model.remove(product)
