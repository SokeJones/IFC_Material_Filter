# v1.5.4.2 — IFC2X3 placement smoke-test correction

## Evidence

The uploaded GitHub `tests.txt` reports 73 tests, 1 error in
`NestedSpaceIntegration.test_repair_existing_containment_without_changing_world_coordinates`.
The exception arises in `ifcopenshell.api.owner.update_owner_history`: `Please create a user to continue`. All other tests passed.

## Change

When a spatial storey target is provided, `repair_reparented_placements`
reconstructs the local `IfcAxis2Placement3D` in IFC project units directly
from the captured world matrix and storey placement. It does not call
`edit_object_placement`, which on IFC2X3 may demand configured owner history.
The implementation checks that `PlacementRelTo` points to the intended
parent and that the world-space transform is unchanged. Unsupported or shared
product placements still fail closed. No changes to filtering/selection.

## Verification

Local source tests: 73 run, 9 IfcOpenShell-dependent integration tests skipped.
**GitHub Actions and real IFC integration tests still required.** Trigger
`Build Windows portable EXE` manually; all tests and frozen selftest must pass.
Then repeat the 40 MB and 360 MB model geometry/material validations.
