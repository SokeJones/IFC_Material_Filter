# IFC Material Filter v1.2 — compact multi-material IFC export

**Status:** Build kit with unit tests; full extraction has NOT been validated on your 358 MB IFC. This ZIP does not contain a prebuilt executable.

## What changed compared with v1.1

v1.1 deleted the unwanted `IfcElement` entries but left large orphaned geometry and properties behind. v1.2 replaces the deletion loop with **IfcPatch `ExtractElements`**: select desired element GlobalIDs, extract them into a new IFC graph, write to a temporary file, reopen and validate, then rename to the requested output path. The original IFC remains unchanged.

Reference: https://docs.ifcopenshell.org/autoapi/ifcpatch/recipes/ExtractElements/index.html

## Materials and relationships

- Enter multiple materials, one per line or separated by semicolons; case-insensitive exact names. Commas are allowed within material names.
- **OR** selection: one matching material is sufficient.
- Direct material association takes priority over the IFC type's material; constituent material layer sets are traversed.
- Default `aggregates` option includes unassigned child elements under parents whose material matches. This is an **application convention**, not automatic IFC material inheritance.
- Optional `aggregates+nests` also includes nesting ancestry; `none` disables parent matching.
- Missing-matching-material elements are excluded. Required opening elements may be included to preserve void geometry. IfcPatch may retain non-geometric assembly ancestors/spatial structures.

## Outputs

- `<name>_filtered.ifc`: new extracted IFC, expected to be substantially smaller than v1.1.
- `<name>_filtered.audit.csv`: all physical elements and KEEP/REMOVE decisions, with match reason.
- For IFC2X3 inputs the output must remain IFC2X3. Extracted IFC is validated by reopening, checking GlobalIDs, checking that expected geometry references remain, and rejecting unexpected geometry on nonselected physical elements.
- Validation does **not** check full geometric equivalence, opening subtraction results, every IFC EXPRESS rule, property set completeness, or viewer compatibility. Verify in BIMcollab Zoom.
- There is no guaranteed file-size target (8.5 MB BIM.works is a useful benchmark).

## Build a portable Windows EXE using GitHub Actions

1. Create a **private** GitHub repository, and upload the files in this kit, preserving `.github/workflows/build-windows.yml`.
2. In GitHub **Actions**, run **Build Windows portable EXE**.
3. Download the artifact `IFC_Material_Filter_Windows` and extract both the artifact and the inner ZIP. Run `IFC_Material_Filter.exe` in a writable folder.
4. No Python installation or administrator rights should be needed to run it; corporate application policy could still prevent execution.
5. IFC data is processed locally. **Never upload your project IFC to GitHub for this workflow.**

Build uses Python 3.12, `ifcopenshell==0.8.5`, `ifcpatch==0.8.5` and PyInstaller. These are pinned to avoid untested future changes, but must be proven against the IFC2X3 input. Known extract recipe version-specific IFC2X3 issues have been reported upstream.

## Local developer commands

```
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python app.py
python cli.py model.ifc filtered.ifc --material "Stahlbeton Schweiz" --material "Beton C30/37"
```

## Troubleshooting

- If validation fails, the destination IFC is not finalised. Look for `<name>_filtered.incomplete.ifc` for diagnostics (do not use as final output).
- If no elements match, only the audit report is created; extraction refuses to create an empty IFC.
- If IfcPatch raises an IFC2X3 compatibility error, send the entire traceback and record the installed/build dependency versions. Do not silently upgrade `ifcpatch` to a development build.
- The IfcPatch recipe may take significant memory/time when extracting thousands of GUIDs from large models.

## Update from v1.1

Replace **all** repository source files with v1.2 and preserve the GitHub workflow. `safe_remove.py` is obsolete and can be deleted. **Rebuild** using GitHub Actions; merely editing source does not update the previous EXE.

## Scope

Only physical `IfcElement` occurrences are material-selected. IFC annotations, standalone quantities and nonphysical objects are not intentionally selected; required model structure can remain. New extraction retains original geometry definitions and supporting references where available, without remeshing.

## Version 1.3: instrumented selection performance

- **Same extraction mechanism and material selection semantics as v1.2.** No change to the geometry copying recipe.
- Caches matched material sets by material root entity ID, rather than by individual element; materials and material layer sets are commonly shared by thousands of occurrences.
- Reuses geometry-presence information collected during selection instead of rescanning the entire input after extraction.
- Each stage reports wall-clock seconds in the application's log and writes a `*.timing.csv` beside the IFC, showing opening, element indexing, hierarchy indexing, selection, audit, extraction, writing, reopening, and validation.
- A 50% speedup is **not guaranteed**. In particular, if `07 IfcPatch ExtractElements` dominates, the caching optimizations will have limited overall effect. Use two validated baseline models to compare timings and output GlobalIDs.

### Verification

Keep your v1.2 EXE and filtered outputs. Rebuild the v1.3 EXE using GitHub Actions. Filter the same input IFC and materials into a new destination, compare counts in the audit CSV, inspect both outputs in BIMcollab Zoom, and compare `*.timing.csv` with total stopwatch time. Do not overwrite production output until the models are checked.

