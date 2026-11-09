# IFC Material Filter v1.6.1 — Release and acceptance notes

## Scope

Both planned v1.6 usability changes are included in this single build kit:

1. **Case-sensitive exact material names**: `Stahlbeton Schweiz` is not the same as `stahlbeton schweiz`. Material names are trimmed, separated by semicolons/newlines and OR-combined. Distinct case variants are no longer deduplicated. Zero/partial-match warnings can suggest exact capitalization; no automatic correction occurs.
2. **Advanced options > Material tools > Scan IFC materials...**: an explicit, read-only source scan lists unique `IfcMaterial.Name` values, including unused definitions, with direct/type/eligible-parent match counts and a search/select dialog. Selected names transfer exactly to the main material filter input; they do not start filtering. Search within the list is intentionally case-insensitive.

## Preserved behavior

- Batch Cleanup default and Standard validation default.
- IFC-only output by default; audit, timing, comparison and verification outputs remain opt-in.
- Original source IFC is never edited by the scanner or the filter.
- Aggregate and type material resolution, openings, placements, presentation layers, reachability and STEP pruning are unchanged except for material-name capitalization comparisons.
- GitHub Actions `workflow_dispatch` only; no push-triggered automatic build.
- m10 and m12 performance modifications remain explicitly out of scope.

## Inventory semantics

Counts answer: *How many physical IFC elements would be selected if this exact name were filtered by itself?* The scanner uses the filtering engine's effective material-precedence order and material graph walker; the current parent mode is applied. Composite components can contain more than one matching material name. Consequently, sums across material rows are **not** the same as the count for an OR-selected set. Structural support shells/openings do not count as independently material-selected elements.

Inventory results are only cached in application memory. Changing source path, source file contents (size/mtime), or parent mode invalidates or prevents reuse. A scan of an IFC with duplicate `IfcElement.GlobalId` values fails safely.

## Verification before release acceptance

- Local headless Python suite: 108 tests total, 94 passed, 14 skipped because IfcOpenShell is unavailable in the local container.
- A graphical Tkinter smoke test under Xvfb confirmed the scanner dialog, multi-selection transfer, input-path cache invalidation and progress reset.
- `python -m compileall` and source/package integrity checks passed.
- The Windows GitHub Actions runner must execute the skipped IFC2X3, IFC4 and IFC4X3 integration tests and frozen executable smoke test.
- Filter exact `Stahlbeton Schweiz` on the established 40 MB and 360 MB models. Expected material-selected counts: 2,415 and 2,417 respectively; retained IFC elements: 3,333 and 3,337. Geometry and material verification should report no differences.
- Re-scan each reference IFC; the scanner's **matching elements** for `Stahlbeton Schweiz` should equal the corresponding **selected** count, not the retained support-inclusive count.
- Verify that a casing-only typo stops with a helpful suggestion and produces no filtered IFC.

**Build kit status:** Ready for manually triggered GitHub Windows build and user acceptance testing; not yet verified on the target Windows EXE.
