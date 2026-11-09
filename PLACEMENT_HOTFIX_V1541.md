# IFC Material Filter v1.5.4.1 — placement-parent hotfix

## Reported failure

The v1.5.4 Batch Cleanup engine failed on the large IFC2X3 source at B03a:
`Placement parent mismatch for 2fzrV9IpvDFxmDDY6GqPOZ`.

The new M4 assertion correctly prevented output but was too strict without a
repair fallback. Changing `IfcRelContainedInSpatialStructure.RelatingStructure`
does not necessarily change `IfcLocalPlacement.PlacementRelTo`. The standard
IfcOpenShell `edit_object_placement` call sometimes preserves a different
placement parent. This is not evidence that the original source has a defect.

## Correction

`placement_repair.py` first calls the existing `geometry.edit_object_placement`
API to preserve the original world transform. If the resulting placement is
not relative to the ancestor storey, the code explicitly computes the
storey-relative transform in IFC project units and rebuilds the occurrence's
`IfcAxis2Placement3D`, updating the local placement parent. An identical
world matrix is required after the repair; otherwise the export aborts.

To avoid editing other products inadvertently, shared local placements are
not modified by the fallback. Unsupported/degenerate placements also abort.

## Acceptance

1. Trigger `.github/workflows/build-windows.yml` manually and verify all real
   IfcOpenShell integration tests and frozen EXE smoke test pass.
2. Retry the full source IFC2X3 export with material `Stahlbeton Schweiz`.
3. Verify selected element count 2,417 and run geometry/material verification.
4. Check zero mismatches, no newly introduced schema errors, and no orphan
   local placements compared with the accepted reference.
5. Verify the small source still exports with its former 2,415 selected elements.

This change is a proposed correction, not validated against the original
360 MB IFC (not included with the build kit).
