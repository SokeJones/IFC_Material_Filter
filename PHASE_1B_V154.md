# Phase 1B — v1.5.4 acceptance checklist

## Scope
- M3: plan all nested-space reparenting before any space deletion
- M4: require the previous global placement and new actual placement parent
- m8: fail closed if a non-selected support shell retains direct or type-supplied geometry

## Acceptance on GitHub Actions
1. Trigger `Build Windows portable EXE` manually (`workflow_dispatch`).
2. Confirm Python regression and real-IfcOpenShell integration tests pass, including `NestedSpaceIntegration`.
3. Confirm compiled EXE smoke test passes.
4. Download the portable EXE from the successful workflow.

## Acceptance on production reference models
1. Run 40 MB model and 360 MB model (same material names and default Batch engine as the prior release).
2. Compare selected GlobalIDs and output schema against v1.5.3.
3. Run optional Verify geometry and Verify materials, compare against original IFC: zero mismatches/unverified.
4. Confirm no newly introduced schema errors with Full validation.
5. If the new support-shell guard aborts, capture the processing log; do not disable the guard without identifying the type/representation link.

## Regression constraints
- Batch Cleanup remains default; Standard validation remains default.
- Save only the filtered IFC by default; audit and detailed reports remain opt-in.
- No change to the user-facing progress bar, centered button or log window.
- No automatic GitHub builds on push.

## Scope limits
M1/M2 semantic metadata cleanup, M5 audit classification and M6 engine parity are deliberately deferred to the subsequent phase.

## v1.5.4.1 placement hotfix (following 360 MB IFC2X3 user report)

v1.5.4 introduced a fail-closed assertion requiring direct placement relative
to the ancestor storey. The 360 MB IFC2X3 input demonstrated that calling
`edit_object_placement` alone may not establish that parent. v1.5.4.1 adds a
controlled relative-axis placement reconstruction and checks the original
world transform. See `PLACEMENT_HOTFIX_V1541.md` for test requirements.
