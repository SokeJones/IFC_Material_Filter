# v1.5.6.1 — IfcOpenShell 0.8.5 entity-count test compatibility

## Failure addressed

The pinned IfcOpenShell version implements iteration over `ifcopenshell.file`
but not `file.__len__`. The new v1.5.6 integration test failed at
`assert len(model) == ...` before testing the production counter. Production
`count_unreachable_entities()` already handles this case with a safe iterator
fallback.

## Changes

- Updated the real-IFC test to compare the production counter with an
  independent iterator-based expected count, rather than calling `len(model)`.
- Added a deterministic fake-model test for `__len__` raising `TypeError`.
- Corrected the misleading B05 comment and performance documentation.
- Updated the shared application version to `1.5.6.1`.

## Not changed

- Material selection, spatial handling, relationship processing, export,
  STEP pruning, IFC validation, UI defaults, and manual GitHub build trigger.
- Runtime performance on the pinned IfcOpenShell version: B05 still uses the
  existing iterator fallback; there is **no claimed B05 speedup**.

## Acceptance

Run the GitHub Actions workflow manually. All source and real-IFC integration
tests and the frozen EXE smoke test should pass. As no export behavior was
changed in this hotfix, model comparison can remain part of the broader v1.5.6
acceptance process.
