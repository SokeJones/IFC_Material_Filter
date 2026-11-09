# v1.6.1 — Material filtering and scanner

## Main window

- Normal workflow and all v1.5.6.1 defaults remain unchanged: Batch Cleanup / Standard validation / only the filtered IFC saved.
- Material input remains multiline with the hint **One per line or separated by semicolons.**
- Selection is now **case-sensitive exact matching** after trimming leading/trailing whitespace. `Stahlbeton Schweiz` and `stahlbeton schweiz` are two different names. Existing OR selection and type inheritance/aggregate semantics are unchanged.
- Zero-match protection still aborts; error and partial-match warnings suggest exact-case names when possible, but do not silently alter selections.

## Advanced options > Material tools > Scan IFC materials...

1. Select the original IFC in the main window; choose **Scan IFC materials...**.
2. Follow the animated progress bar. The source is opened read-only, and the scan never saves files.
3. The inventory window shows the distinct material names actually defined in `IfcMaterial.Name`, including names with zero matching elements.
4. The matching count represents the number of physical `IfcElement`s selected by that one name, **including** direct, type-inherited, and eligible unassigned aggregate/nested children for the currently selected parent mode. Supporting openings and shells are **excluded** from these counts.
5. Search ignores capitalization for convenience, but the displayed names and subsequent filtering preserve capitalization.
6. Select entries using Ctrl/Shift or **Select visible**; click **Use selected materials** to replace the main text field. This alone never runs the filter.
7. Reopening the scanner for an unchanged source and parent mode reuses in-memory results. Changing the source path, file size/modified time or parent mode causes a rescan.

**Important:** If a composite element has multiple material names, it may count toward more than one row. Therefore the sum of all material rows can exceed the number of physical elements and is not the count of their combined OR selection.

## Testing / acceptance

- The v1.6.1 local test suite includes synthetic scanner and case-sensitive selection tests. The pinned IfcOpenShell integration test runs on GitHub Actions, testing IFC2X3/IFC4/IFC4X3 and comparing scanner counts to actual Batch output.
- The GitHub Actions workflow is **manually triggered only** (`workflow_dispatch`). Its compiled Windows EXE smoke test remains intact.
- Check against the project reference models that the exact name `Stahlbeton Schweiz` still selects 2,415 elements in the 40 MB model and 2,417 elements in the 360 MB model; no filtering-core graph/reachability changes were made.
- Run geometry/material comparison on the reference models before accepting the new version.
