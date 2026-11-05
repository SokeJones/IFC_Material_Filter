# IFC Material Filter v1.4.7 — Optional material verification

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

## v1.4.2 diagnostic update

The previous 1.4.1 benchmark showed 127,372 reachable STEP IDs but only
127,371 serialized records, so the experimental engine refused to publish.
Version 1.4.2 **does not assume that missing record is harmless**. Instead:

- It records all missing expected STEP IDs and duplicate serialized IDs in
  `*_batch.incomplete.step_prune_diagnostics.json` (the naming depends on the
  specified output path). The report survives a failed export.
- It enriches missing IDs with IFC entity class, GlobalID where available,
  and inverse-reference count from the in-memory graph.
- It validates the **source IFC** before either engine runs (in Full mode)
  and includes `source_validation` plus simple error-count differences in
  `.comparison.json`. These totals are **not normalized by graph size**;
  review error categories rather than interpreting the difference as a
  definitive introduced-error count.
- It refuses to publish batch output if STEP records are missing or duplicate.
- The proven IfcPatch export path and multi-material selection are unchanged.

Please rerun the same benchmark and share `.comparison.json` and the new
`*.step_prune_diagnostics.json`. They will identify the precise entity behind
this issue. This is a **diagnostic version**, not a confirmed resolution.

**Important:** Your v1.4.1 reference export logged 9,941 schema validation
errors. A model opening in a viewer does not prove those are harmless; the
source baseline check helps decide how to investigate.


## v1.4.3 hotfix: non-serialized STEP ID #0

The real v1.4.2 diagnostic established that the only missing STEP record is ID
`#0`. No `#0` record exists in a valid STEP serialization; IfcOpenShell may
expose temporary/inline entities with `id() == 0`. The reachability traversal
was adding that sentinel to the serialized keep-ID set, producing a guaranteed
one-record mismatch even when every real STEP record was retained.

Changes:
- Treat entities with ID <= 0 as non-serialized while traversing any forward
  references to real STEP objects.
- Reject invalid keep-ID sets before running the STEP pruning process.
- Add dedicated tests for transient ID #0 in graph traversal and pruning.
- Continue fail-closed validation for genuinely missing STEP IDs and duplicate
  STEP records. No relaxation of export integrity checks.

This fixes the specific reported v1.4.2 error, but the experimental Batch
Cleanup engine still requires IFC schema/geometry review. Input model has
10,453 schema errors and the IfcPatch output 9,978; these are not resolved by
this fix. Test both engines and compare the compact outputs in BIMcollab Zoom.

## v1.4.6: reachability profiling (diagnostic, non-behaviour-changing)

This version deliberately **does not alter the v1.4.3 keep/remove rules**. It
instruments the graph traversal to identify why the 365 MB model retains far
more STEP resources than the smaller model. Every Batch Cleanup run generates:

- `*_batch.reachability.json`: retained entity counts by IFC class, first
  discovery mechanism (root/forward/inverse), number and classes of inverse
  relationships traversed, and a bounded list of the largest inverse-fanout
  sources including GlobalIDs where available. It is written immediately after
  graph traversal, even if later export stages fail.
- `*_batch.step_classes.csv`: STEP entity counts and serialized bytes retained
  vs pruned, grouped by IFC class and sorted by retained byte size. This is
  written after a successful streaming prune (before model validation).

The diagnostics capture *first* discovery paths, not a formal proof of the
unique cause of reachability: an entity may have several references. This
release retains the full v1.4.3 filtering and validation logic; it adds
performance overhead and should not be interpreted as a speed optimization.
Compare the class reports from the 40 MB and 365 MB models, then change the
traversal based on those findings in a separate version.


## v1.4.6: selective spaces and presentation-layer cleanup (experimental)

* The Batch engine removes `IfcSpace` objects rather than retaining them as spatial roots.
* If retained elements are spatially contained within a space, they are attached to its existing ancestor `IfcBuildingStorey`. Their placements are not changed. Exports abort if no valid ancestor storey can be located.
* Room-boundary relationships for removed spaces are discarded. Space-oriented workflows should continue to use the original IFC.
* Presentation layers retain assignments only to geometric representations reachable from surviving elements and their types. Empty layers are deleted, and nonmatching items are removed.
* IfcPatch reference export is unchanged. Full semantic and geometry validation on the user's models remains required.
* New counters: spaces removed, contained elements reparented, presentation layer assignments clipped.


## v1.4.6 - correctness / placement / geometry

- Batch: when a retained element is reparented out of an unselected IfcSpace,
  rebuild its placement using the **documented IfcOpenShell**
  `ifcopenshell.api.geometry.edit_object_placement` operation and its prior
  global placement matrix. Any observed displacement aborts the export.
- Full validation writes `*_batch.placement_diagnostics.json`, listing
  orphaned `IfcLocalPlacement` objects, to investigate source-versus-output
  findings. This report is diagnostic; it does not silently delete placements.
- New **Verify geometry...** button: select the original IFC in the main
  window, click the button, then select an existing filtered IFC. The check
  triangulates every retained IfcElement from each file using identical
  IfcOpenShell settings, compares world-space triangles and global placement
  matrices by GlobalID, and writes `*.geometry_comparison.json`. Unsupported
  geometries are reported as UNVERIFIED, not PASS. The check may take a long
  time and use substantial memory, so it is separate from the filter run.
- The existing STEP serialization/prune architecture remains unchanged.
- v1.4.6 is **experimental pending full source-model benchmarks**. No claim
  of repaired errors or geometric equivalence is made until real-world run.

**Caution:** Mesh matching with default 0.0001 project-length-unit tolerance validates the generated
triangulated surface, not mathematical BREP identity. The comparison verifies
only retained IFC elements, not correctness of the material-selection decision
itself.


## v1.4.6 build-fix 2 (IfcOpenShell 0.8.5 placement API compatibility)
- Replaced calls to `ifcopenshell.util.placement.get_placement`, which is not available in the Windows runner's pinned IfcOpenShell 0.8.5, with `get_local_placement`.
- Placement repair converts IFC project-unit translations to SI metres before calling `edit_object_placement(..., is_si=True)`; rotations remain unchanged.
- The geometry comparison and the integration test also use `get_local_placement`.
- The GitHub test gate stays enabled; the filter/export and serialization algorithms are unchanged.


## v1.4.7 — Optional material assignment comparison

This version adds **Verify materials...** as a separate action next to **Verify geometry...**.
Filtering, selection, pruning, serialization and regular processing stages are unchanged.

1. Choose the **original IFC** with *Source IFC*.
2. Click **Verify materials...** and select the previously filtered `*_batch.ifc`.
3. The independent comparison writes `*_batch.material_comparison.json` next to the filtered file.
4. Inspect `passed`, `material_mismatches`, `material_unverified` and the GlobalID-specific details.

It checks every retained `IfcElement`, comparing IFC class and the **effective material root**
via IfcOpenShell `get_material(should_inherit=False/True)`. It distinguishes direct
and type-inherited assignments and compares nested material structures, including
material layers, thicknesses and constituent/profile details. It compares neither
material presentation inverses nor the correctness of *discarded* elements.
Unassigned supporting objects can legitimately have no effective material in both
models; the report counts those separately. Differences and resolution errors fail
verification; no attempt is made to modify the IFCs. STEP IDs are ignored.

The original and filtered IFC files are opened **sequentially** to reduce memory
consumption. Since both are reopened, the operation has additional I/O overhead,
especially for the 360 MB source. **No extra time is added to normal filtering.**
The optional full check should be run once for both reference models, when IFC
schema or authoring conventions change, and after revisions to filter logic.

Command-line alternative for developers:

```powershell
python material_verification.py original.ifc filtered_batch.ifc
```

The Windows build is created with the existing `.github/workflows/build-windows.yml`
GitHub Actions workflow. All integration tests run on the Windows runner.
