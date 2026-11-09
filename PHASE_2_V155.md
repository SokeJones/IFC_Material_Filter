# Phase 2 — IFC Material Filter v1.5.5

## Scope

M1 unused product-type declaration cleanup, M2 material-property/shape-aspect metadata preservation, M5 support-object audit classifications, M6 explicit Batch retention policy, M9 expanded real-IFC integration tests.

## Unchanged

Batch default, Standard/basic validation, default only the filtered IFC output, GUI controls, fail-closed structural validation, geometry/material verifiers, and manually triggered GitHub Actions (`workflow_dispatch`).

## Acceptance checklist

1. GitHub Windows Python integration tests pass, including IFC2X3, IFC4 and IFC4X3 synthetic test cases.
2. Frozen Windows EXE selftest passes.
3. 40 MB IFC2X3 reference file: 2,415 directly selected material-matching elements; geometry/material comparisons show no mismatches.
4. 360 MB IFC2X3 reference file: 2,417 directly selected elements, 3,337 total retained elements, 350 spaces removed; geometry/material comparisons show no mismatches.
5. Optional Full schema validation should not add errors compared to the corresponding source, and orphan-placement diagnostics are reviewed.
6. With `Save audit CSV` enabled, retained support shells and openings are labeled KEEP_SUPPORT. With both report options disabled, only the filtered IFC is generated.
7. A small IFC4/IFC4X3 model containing unused type declarations should not retain its unused product type or its otherwise-unreferenced material/representation map.
8. IfcMaterialProperties/IfcExtendedMaterialProperties and IfcShapeAspect linked to retained objects are preserved.

The new integration tests are skipped where IfcOpenShell is not installed. A local Python pass is not evidence that the real IFC tests passed.
