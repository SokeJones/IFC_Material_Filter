# IFC Material Filter v1.4.1 — Two-engine benchmark (experimental)

**Status:** Source/build kit for a portable Windows executable. No prebuilt `.exe` is contained in this ZIP. The existing **v1.3 IfcPatch extraction engine** is retained as the reference and was previously verified on two real models by the user. **Batch Cleanup is experimental and has not yet been verified on the user's benchmark IFC files.** The output is not to be used in engineering deliverables until compared in a viewer.

## Engines and outputs

The interface defaults to `both`, `full` validation. With an output base name `filtered.ifc`, this creates:

- `filtered_ifcpatch.ifc`: reference output from `ExtractElements` (as in v1.3).
- `filtered_batch.ifc`: experimental output by detaching rejected elements from relationships and batch-removing unreachable IFC resources.
- `filtered.audit.csv`: source GlobalIDs, material matches and selection reasons.
- `filtered_ifcpatch.timing.csv` and `filtered_batch.timing.csv`: individual elapsed stage times and process RSS before/after/peak. Corresponding `*.timing.metrics.csv` contain entity and file-size counters.
- `filtered.comparison.json`: both engines' results, validation messages, output sizes, selected-element parity checks, and any failure tracebacks.
- `filtered.timing.csv` + `filtered.timing.metrics.csv`: common selection stages.

For a single engine (`ifcpatch` or `batch`) the requested filename is used unchanged. `batch` mode is strictly experimental. Existing IFC files are never overwritten. Failed exports do not replace the final destination; incomplete output files are left with `.incomplete.ifc` in the name for diagnostics.

## Material semantics

- Multiple names: one per line, or separated by semicolons (OR logic; case-insensitive exact comparison).
- Direct occurrence materials take precedence over IFC type material assignments.
- Parent aggregation is optional (default `aggregates`) and adds unassigned children whose parent matches. This is a selection heuristic, **not normative IFC material inheritance**.
- Optional `aggregates+nests` follows nesting parents as well.
- Openings and unrepresented assembly shells are retained where needed.

## Batch Cleanup algorithm (experimental)

1. Reopen a **separate** IFC instance for the batch engine; do not modify the reference model.
2. Invert the shared material selection and remove rejected products with v1.1's relationship-safe routine; do not recursively delete shared property sets.
3. Clear representations of retained non-selected assembly shells.
4. Traverse the remaining project's, spatial objects' and selected elements' forward references, plus inverse IFC relationships attached to live objects and types. **Do not** traverse inverse relationships from shared material nodes.
5. Serialize the edited IFC to a temporary STEP file, then stream only reachable STEP entity records to a second temporary IFC. Unused geometry and other resources are dropped without calling `model.remove()` millions of times.
6. Reopen the pruned IFC, check required GUIDs and geometry references, perform schema validation, then publish the final file.

The size and speed of this approach are not guaranteed. A graph cleanup may require substantial RAM; **peak process RSS** is monitored in the timing logs. The implementation may encounter unexpected relationships in models not represented by unit tests; it fails explicitly instead of silently emitting an unchecked file.

## Full validation (default)

- Reopen the output and verify IFC schema and retained GlobalIDs.
- Reject unexpected represented physical elements (except supporting openings).
- Detect previously represented selected elements that lose representation references.
- Run `ifcopenshell.validate.validate()` on the resulting IFC with **basic schema attribute/cardinality checks**; errors/warnings are recorded. EXPRESS WHERE rule checking is not performed, and pre-existing schema warnings may remain.
- Compare both outputs' selected GlobalIDs, classes and representation presence. The comparison is **structural**, not a proof of shape or world-placement equality. Confirm these using BIMcollab Zoom before using the batch result.
- Warn if experimental output is over 1.5 times the reference export size.

## Build EXE on Windows via GitHub Actions

1. Upload source files to your existing **private** GitHub repository, preserving `.github/workflows/build-windows.yml`.
2. Run GitHub Actions **Build Windows portable EXE**. It installs pinned IfcOpenShell 0.8.5/IfcPatch 0.8.5, psutil and PyInstaller; it runs all tests including a small IFC integration test on Windows before building.
3. Download `IFC_Material_Filter_Windows`, extract the inner ZIP, run `IFC_Material_Filter.exe`.
4. No Python or admin rights are normally needed to run the packaged executable (subject to corporate security policy).

**Do not upload proprietary IFC model files to GitHub.** Everything can run locally after you have built the EXE.

### CLI alternative

```powershell
python cli.py original.ifc filtered.ifc --material "Stahlbeton Schweiz" --material "Beton C30/37" --engine both --validation full
```

## Benchmark protocol

Use the exact same input IFC and materials as v1.3. First compare `*_ifcpatch.ifc` visually with `*_batch.ifc` in BIMcollab Zoom and check the `comparison.json`, especially schema findings and representation differences. Record total times and output sizes for both benchmark models. Keep v1.3 as your production fallback until batch output is verified and substantially faster.

## References

- IfcOpenShell file batch operations: https://docs.ifcopenshell.org/autoapi/ifcopenshell/file/index.html
- IfcOpenShell relationship removal: https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/root/index.html
- IfcPatch ExtractElements: https://docs.ifcopenshell.org/autoapi/ifcpatch/recipes/ExtractElements/index.html
- IfcOpenShell schema validation: https://docs.ifcopenshell.org/autoapi/ifcopenshell/validate/index.html

## v1.4.1 hotfix: B06 nonresponsive cleanup

In v1.4 the B06 implementation called `model.remove(model.by_id(eid))` for *every*
unused STEP entity, often millions of times, and only later invoked
`model.unbatch()`. This could take a very long time without progress and
ignored `RuntimeError` from failed removals. **Do not use that version of the
experimental Batch engine on large models.**

v1.4.1 replaces this with a serialized STEP pruning pass:

1. Detach rejected physical elements from remaining IFC relationships as before.
2. Build the reachable resource set from retained elements/spatial roots.
3. Write the edited IFC once to an `*.unpruned.incomplete.ifc` temporary file.
4. Stream over its serialized entity records, retaining only reachable STEP IDs.
   Report progress approximately every 64 MiB read.
5. Reopen the compact filtered IFC, validate required IDs, geometry references,
   and IFC schema; publish only if checks complete.

The pruning method conserves the existing IFC entity identifiers and uses no
`model.batch()` / `model.unbatch()` or per-resource `model.remove()` loop.
It creates a temporary full-size serialization on disk, so allow sufficient
free disk space. It requires normal IfcOpenShell STEP serialization. It is an
experimental optimization, **not yet validated on your large models**.

A second fix preserves the correct original element count in the summary when
benchmark mode releases the selection model before running Batch Cleanup.

The reference IfcPatch engine is unchanged. Please benchmark the experimental
output against the reference, including visual geometry/placement verification.
