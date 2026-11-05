# v1.5 user interface

This is a UI-only release based on the v1.4.7 filtering and verification engines.

## Main screen

1. Choose an input IFC file.
2. Enter material names **one per line or separated by semicolons**.
3. Confirm the suggested output filename and select **Filter IFC**.
4. The status line shows the current step. The animated progress indicator is deliberately **indeterminate**, because the engine cannot determine an honest percent-complete while parsing or serializing large IFC files.

The original IFC is never overwritten.

## Advanced options

- **Export settings...**: Batch Cleanup (default), IfcPatch reference or Both benchmark; Standard (basic) validation (default) or Full; retained parent behavior; audit-only export.
- **Verification tools > Verify geometry...**: optional world-space geometry comparison.
- **Verification tools > Verify materials...**: optional direct/type-assignment comparison.
- **Verification tools > View processing log...**: opens a resizable, scrollable log that updates in real time. Save it as UTF-8 `.txt` or copy all text. Log contents remain in memory for the application's current session, including failed runs.

## Compatibility and limits

- Windows portable `.exe` is built via the included GitHub Actions workflow, with no user-side Python installation.
- Output engine code, material matching, parent inclusion, geometry verification and material verification are unchanged.
- Standard validation does not perform full schema checks. For unfamiliar models or consequential engineering deliverables, use Full or the optional verification tools.
- The log records application progress messages and exception tracebacks, but not arbitrary stdout emitted by native third-party libraries.
