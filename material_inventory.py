"""Read-only IFC material inventory for v1.6.

Use the same IfcMaterial graph walker and effective-material precedence as
filter_engine. Counts reflect filtering with *one* material name at a time:
direct assignment, type inheritance, or material-free descendants of
matching aggregate/nest parents. They exclude support shells and openings.

Never create geometry, modify IFC relationships, or write a file.
"""

from collections import Counter, deque
from pathlib import Path
from typing import Callable

from filter_engine import ensure_unique_element_globalids, find_matching_materials


PARENT_MODES = ('none', 'aggregates', 'aggregates+nests')


def scan_model_materials(model, parent_mode='aggregates', notify: Callable[[str], None] = print,
                         material_getter=None):
    """Scan a loaded IFC model without mutating it.

    ``material_getter`` is injectable for library-independent unit tests.
    Default is IfcOpenShell's get_material(element, should_inherit=...).
    """
    if parent_mode not in PARENT_MODES:
        raise ValueError('Invalid parent mode')
    if material_getter is None:
        import ifcopenshell.util.element
        material_getter = ifcopenshell.util.element.get_material

    elements = list(model.by_type('IfcElement'))
    ensure_unique_element_globalids(elements)
    declared_names = sorted({(mat.Name or '').strip()
                             for mat in model.by_type('IfcMaterial') if (mat.Name or '').strip()},
                            key=lambda s: (s.casefold(), s))
    wanted = set(declared_names)
    by_name = {name: Counter() for name in declared_names}
    material_states = {}
    root_names = {}

    def material_state(obj):
        oid = obj.id()
        if oid not in material_states:
            direct = material_getter(obj, should_inherit=False)
            if direct is not None:
                material_states[oid] = (direct, 'direct')
            else:
                inherited = material_getter(obj, should_inherit=True)
                material_states[oid] = (inherited, 'type' if inherited is not None else 'none')
        return material_states[oid]

    def names_of(root):
        if root is None:
            return set()
        rid = root.id()
        if rid not in root_names:
            root_names[rid] = find_matching_materials([root], wanted)
        return root_names[rid]

    permitted = set()
    if parent_mode != 'none':
        permitted.add('IfcRelAggregates')
    if parent_mode == 'aggregates+nests':
        permitted.add('IfcRelNests')
    parents = {}
    for relation_class in ('IfcRelAggregates', 'IfcRelNests'):
        if relation_class not in permitted:
            continue
        for relationship in model.by_type(relation_class):
            parent = relationship.RelatingObject
            for child in relationship.RelatedObjects:
                parents.setdefault(child.id(), []).append(parent)

    def parent_names(element):
        # Mirrors filter_engine.matching_parent: stop climbing a branch when
        # an ancestor has an effective material, even if its name is blank.
        pending = deque([element.id()])
        seen = {element.id()}
        matches = set()
        while pending:
            current_id = pending.popleft()
            for parent in parents.get(current_id, ()):
                pid = parent.id()
                if pid in seen:
                    continue
                seen.add(pid)
                material_root, _ = material_state(parent)
                if material_root is not None:
                    matches.update(names_of(material_root))
                else:
                    pending.append(pid)
        return matches

    notify(f'Material inventory: {len(declared_names)} distinct names; '
           f'{len(elements):,} physical elements to inspect.')
    for i, element in enumerate(elements, 1):
        root, origin = material_state(element)
        if root is not None:
            matching_names = names_of(root)
            reason = origin
        elif permitted:
            matching_names = parent_names(element)
            reason = 'parent'
        else:
            matching_names = set()
            reason = 'none'
        for name in matching_names:
            by_name[name][reason] += 1
        if i % 2000 == 0:
            notify(f'Material inventory: examined {i:,} / {len(elements):,} elements')

    materials = []
    for name in declared_names:
        counts = by_name[name]
        materials.append({
            'name': name,
            'matching_elements': counts['direct'] + counts['type'] + counts['parent'],
            'direct': counts['direct'],
            'type': counts['type'],
            'parent': counts['parent'],
        })
    notify(f'Material inventory completed: {len(materials)} material names; '
           f'{sum(entry["matching_elements"] > 0 for entry in materials)} used by the filter.')
    return {'schema': model.schema, 'elements_scanned': len(elements),
            'parent_mode': parent_mode, 'materials': materials}


def scan_ifc_materials(input_path, parent_mode='aggregates', notify=print):
    """Open and inspect one source IFC. No output files are created."""
    import ifcopenshell

    src = Path(input_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    notify('Opening input IFC for material scan: ' + src.name)
    model = ifcopenshell.open(str(src))
    if model is None:
        raise ValueError('IfcOpenShell could not read the input IFC')
    notify('Material scan: IFC schema ' + model.schema)
    return scan_model_materials(model, parent_mode=parent_mode, notify=notify)
