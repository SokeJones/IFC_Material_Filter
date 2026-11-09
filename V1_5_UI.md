# v1.5 user interface

This is a UI-only release based on the v1.4.7 filtering and verification engines.

## Main screen

1. Choose an input IFC file.
2. Enter material names **one per line or separated by semicolons**.
3. Confirm the suggested output filename and select **Filter IFC**.
4. The status line shows the current step. The animated progress indicator is deliberately **indeterminate**, because the engine cannot determine an honest percent-complete while parsing or serializing large IFC files.

The original IFC is never overwritten.

## Advanced options

- **Export settings...**: **Batch Cleanup (recommended/default)**, IfcPatch (optional reference) or Both (benchmark); **Standard (basic) validation (default)** or Full; retained parent behavior; audit-only export. Batch Cleanup is the project default based on the 40 MB/360 MB regression tests, not a universal guarantee for arbitrary IFC files.
- **Verification tools > Verify geometry...**: optional world-space geometry comparison.
- **Verification tools > Verify materials...**: optional direct/type-assignment comparison.
- **Verification tools > View processing log...**: opens a resizable, scrollable log that updates in real time. Save it as UTF-8 `.txt` or copy all text. Log contents remain in memory for the application's current session, including failed runs.

## Compatibility and limits

- Windows portable `.exe` is built via the included GitHub Actions workflow, with no user-side Python installation.
- Output engine code, material matching, parent inclusion, geometry verification and material verification are unchanged.
- Standard validation does not perform full schema checks. For unfamiliar models or consequential engineering deliverables, use Full or the optional verification tools.
- The log records application progress messages and exception tracebacks, but not arbitrary stdout emitted by native third-party libraries.

## v1.5.2 adjustments

The Filter IFC button is centered and bold rather than full width. Selecting a new input IFC resets the progress indicator and status to ready, without clearing historical processing logs. Input selection is locked while an operation is running.

## C2 review clarification

The UI recommendation is intentional: Batch Cleanup remains the default. Standard validation checks structural output requirements but does **not** perform complete schema attribute/cardinality validation. For unfamiliar or critical IFC files, use Full validation and/or optional geometry and material comparisons. No filter behavior changed in this documentation-only update.


## v1.5.4 Phase 1B

No change to the UI controls, output-file defaults or manually triggered GitHub workflow. Structural integrity checks fail safely if reparented placements or support-shell representations are invalid.


## v1.5.6 UI notes

- The material field starts empty; the hint “One per line or separated by semicolons.” remains.
- Audit-only mode shows “Audit completed — no IFC exported” and does not require an output IFC filename.
- Default output is still **only** the filtered IFC. Audits and other diagnostic reports remain opt-in.
- Selecting a different input IFC resets the progress/status; the process log remains available.
