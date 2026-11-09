# IFC Material Filter v1.5.6.1 — Phase 3 integration-test hotfix

**Status:** v1.5.6.1 GitHub Actions source/build kit for a portable Windows executable (no compiled EXE included). **Batch Cleanup is the supported default engine for this project**, based on the 40 MB and 360 MB reference-model tests. Those tests passed structural, world-space tessellated-geometry and effective-material comparisons; schema-error counts did not increase. These are project-specific regression results, not a guarantee for all IFC files or schemas.

## Everyday workflow

1. Select an input IFC.
2. Enter **Material names (one per line or separated by semicolons)**. The field starts empty.
3. Accept or change the output filename and click **Filter IFC**.
4. Follow the animated progress indicator and status message. It is indeterminate, not a fabricated percentage.

**Defaults:** Batch Cleanup, Standard (`basic`) validation, and `aggregates` parent handling. These settings can be changed under **Advanced options > Export settings...**. Geometry verification, material verification, and the scrollable, savable processing log are under **Advanced options > Verification tools**.

The source IFC is never overwritten. Existing destinations are not overwritten. Optional verification actions do not slow down normal filtering.

See [`V1_5_UI.md`](V1_5_UI.md) for the UI guide and limitations.

## Engines and outputs

The default **Batch Cleanup** (`batch`) engine writes the requested filtered IFC filename. In the GUI, **Save audit CSV** and **Save detailed reports** are both OFF by default, so ordinary filtering saves only the IFC (unless a failure requires emergency diagnostics). Enable the respective Advanced Options checkboxes to save reports. Optional **IfcPatch** is a reference engine; **Both** creates `_batch.ifc` and `_ifcpatch.ifc` for comparison. Audit-only mode saves a CSV rather than an IFC and does not require an output filename. The success message explicitly states that no IFC was exported.

## Material semantics

- Multiple names: one per line, or separated by semicolons (OR logic; case-insensitive exact comparison).
- Direct occurrence materials take precedence over IFC type material assignments.
- Parent aggregation is optional (default `aggregates`) and adds unassigned children whose parent matches. This is a selection heuristic, **not normative IFC material inheritance**.
- Optional `aggregates+nests` follows nesting parents as well.
- Openings and unrepresented assembly shells are retained where needed.

## Batch Cleanup algorithm (default engine)

1. Reopen a **separate** IFC instance for the batch engine; do not modify the reference model.
2. Invert the shared material selection and remove rejected products with v1.1's relationship-safe routine; do not recursively delete shared property sets.
3. Clear representations of retained non-selected assembly shells.
4. Remove IFC4+ declarations for unused product types, without removing non-type definitions. Traverse the remaining project, spatial structure and retained elements via forward references and selected inverse relationships. Retain material properties and shape aspects attached to live material and shape definitions. These targeted inverse links are not a general traversal into excluded geometry.
5. Serialize the edited IFC to a temporary STEP file, then stream only reachable STEP entity records to a second temporary IFC. Unused geometry and other resources are dropped without calling `model.remove()` millions of times.
6. Reopen the pruned IFC and check required GlobalIDs and representation references before publishing. Full schema validation is performed only when **Full** is selected.

The 40 MB and 360 MB reference-model benchmarks support using Batch Cleanup as the project default. Size and speed are model-dependent, and cleanup can require substantial RAM. Models from unfamiliar exporters or schemas may contain untested relationships: use **Full validation** and, when warranted, the independent **Verify geometry** / **Verify materials** actions.

## Validation levels

**Standard (`basic`) — GUI default:** reopens the output and checks required GlobalIDs, IFC schema identity, retained elements and geometry-representation presence. It does **not** run full `ifcopenshell.validate.validate()` schema attribute/cardinality checks or orphan-placement diagnostics. Standard is a fast structural validation, **not** a statement that the entire IFC is schema-valid.

**Full — optional (Advanced Options):** additionally runs IfcOpenShell schema attribute/cardinality validation and orphan-placement diagnostics, retaining findings if report saving is enabled. EXPRESS WHERE rules are not checked; pre-existing source errors may remain.

**Both engines — optional benchmark mode:** compares selected GlobalIDs/classes and representation presence between Batch Cleanup and IfcPatch; this parity check is structural, not a proof of exact shape or world placement. Independent **Verify geometry** and **Verify materials** actions are available in Advanced Options. These are not run during routine filtering.

## Build EXE on Windows via GitHub Actions

1. Upload source files to your existing **private** GitHub repository, preserving `.github/workflows/build-windows.yml`.
2. Run GitHub Actions **Build Windows portable EXE**. It installs pinned IfcOpenShell 0.8.5/IfcPatch 0.8.5, psutil and PyInstaller; it runs all tests including a small IFC integration test on Windows before building.
3. Download `IFC_Material_Filter_Windows`, extract the inner ZIP, run `IFC_Material_Filter.exe`.
4. No Python or admin rights are normally needed to run the packaged executable (subject to corporate security policy).

**Do not upload proprietary IFC model files to GitHub.** Everything can run locally after you have built the EXE.

### CLI alternative

```powershell
python cli.py original.ifc filtered.ifc --material "Concrete;Steel"
# Optional reports:
python cli.py original.ifc filtered.ifc --material "Concrete" --save-audit --save-reports
# Audit-only: output IFC path can be omitted:
python cli.py original.ifc --material "Concrete" --dry-run
```

**CLI defaults:** Batch Cleanup (`batch`) and Standard (`basic`) validation, with audit/report saving OFF. `--save-audit` and `--save-reports` enable additional files; `--no-audit`/`--no-reports` remain accepted as compatibility aliases. Newlines and semicolons are split within **every** `--material` argument. Routine use still writes only the output IFC.

## Phase 3 — v1.5.6 maintenance (m1–m12)

- Shared `version.__version__` sets GUI title and comparison-report version.
- Optional timing now uses separate `*.selection.timing.csv` and `*.timing.csv` files, with distinct `*.metrics.csv` companions. Selection and engine timing are no longer overwritten.
- Audit-only saves an audit CSV and shows a correct status; an output IFC filename is not required.
- Geometry verification compares placement matrices numerically, with requested project-unit tolerance for **translations** and an independent dimensionless orientation tolerance (`1e-8`); the world-space tessellation hash method remains otherwise unchanged.
- The unreachable-entity diagnostic counter uses a length-based fast path **only when the model supports `len()`**. IfcOpenShell 0.8.5's `file` objects do not; the original iterator-based count is retained. v1.5.6.1 fixes the GitHub integration test to verify actual counts instead of assuming `len(model)`. This is not a runtime optimization for the pinned IfcOpenShell version. Export/pruning semantics are unchanged.
- The material entry field starts empty; all prior hints and Advanced Options are preserved.
- Performance findings m10/m12 were reviewed using the measured reference-model timings. Both relationship removal and reachability behavior are **unchanged**, pending targeted scaling evidence. See `PHASE_3_V156.md`.

## Phase 2 — v1.5.5 semantic preservation (M1, M2, M5, M6, M9)

- **M1 — Unused product types:** In IFC4/IFC4X3, `IfcRelDeclares` entries for `IfcTypeProduct` definitions with no surviving `IfcRelDefinesByType` occurrence are removed before reachability. Mixed declarations preserve all non-product-type definitions. IFC2X3 does not define `IfcRelDeclares` and bypasses this pass. Types reachable through other retained relationships may still survive; this is deliberate conservative behavior.
- **M2 — Material and shape metadata:** Narrow inverse traversal retains `IfcMaterialProperties` (including IFC2X3 `IfcExtendedMaterialProperties`) attached to reachable material definitions, and `IfcShapeAspect` attached to retained product definition shapes and representation maps. The existing material verifier checks *effective material assignments*, not every inverse-linked property; new integration cases check the extra metadata explicitly.
- **M5 — Audit CSV:** When enabled, the optional audit now marks retained non-selected aggregate parent shells as `KEEP_SUPPORT / support_shell` and retained openings as `KEEP_SUPPORT / support_opening`. The `KEEP` category and selection totals still mean independently material-selected elements. The default remains **IFC output only**.
- **M6 — Retention policy:** `IfcProject` and all non-space spatial containers are retained (even if empty). `IfcSpace` objects are removed, with contained retained products moved to an ancestor storey and their global transforms preserved. Non-`IfcElement` products such as grids, annotations and ports are not material-selected; they may survive only if reachable through retained graph context. Their classes/counts are reported in the engine's internal validation summary. We intentionally do not make Batch Cleanup structurally identical to the optional IfcPatch engine.
- **M9 — Tests:** Synthetic IFC2X3, IFC4 and IFC4X3 integration tests cover type-inherited material selection, direct-material overrides, unused type declarations, material properties, shape aspects and end-to-end Batch export. They run on the GitHub Windows runner with IfcOpenShell installed. The real Windows executable smoke test remains enabled.

**Validation boundary:** The 40 MB and 360 MB reference models are IFC2X3 and are not sufficient to validate new IFC4/IFC4X3 type-declaration behavior. The v1.5.5 IFC2X3 reference models passed independent geometry and material comparisons, and the 360 MB Full validation reported four source and four output schema errors with zero orphan placements. IFC4/IFC4X3 behavior must still be verified through the corresponding synthetic integration tests. Optional Full schema validation, geometry comparison and material comparison remain recommended for new IFC sources.

**Build:** `.github/workflows/build-windows.yml` remains **manual `workflow_dispatch` only**. No build starts on push.

## Benchmark and release status

The project previously compared Batch Cleanup and IfcPatch on approximately 40 MB and 360 MB IFC inputs. Batch Cleanup passed structural checks, world-space tessellated-geometry verification (3,214 and 3,218 represented elements respectively, zero reported mismatches), and material verification (3,333 and 3,337 retained elements respectively, zero reported mismatches). The 360 MB filtered file had the same number of reported schema errors as its source (4); the 40 MB output had 7,007 versus 10,453 in the source, primarily from pre-existing relationship issues. **These checks justify Batch Cleanup as the project default, not universal certification.**

IfcPatch remains an **optional comparison/reference engine**, not the everyday production fallback. For unfamiliar IFC exporters or high-consequence deliverables, select Full validation and optionally run the independent geometry/material comparisons. Historical experimental notes below describe earlier versions and do not override the current defaults.

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

## Historical development notes (v1.4.x)

The following sections document earlier experimental steps and may contain historical wording such as “experimental,” “pending benchmarks,” or references to an older fallback. They describe the state **at that version**, not the current v1.5.6.1 default.

### v1.4.2 diagnostic update

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


## v1.4.6: selective spaces and presentation-layer cleanup (historical release note)

* The Batch engine removes `IfcSpace` objects rather than retaining them as spatial roots.
* If retained elements are spatially contained within a space, they are attached to its existing ancestor `IfcBuildingStorey`. Their placements are not changed. Exports abort if no valid ancestor storey can be located.
* Room-boundary relationships for removed spaces are discarded. Space-oriented workflows should continue to use the original IFC.
* Presentation layers retain assignments only to geometric representations reachable from surviving elements and their types. Empty layers are deleted, and nonmatching items are removed.
* IfcPatch reference export is unchanged. Full semantic and geometry validation on the user's models remains required.
* New counters: spaces removed, contained elements reparented, presentation layer assignments clipped.


## v1.4.6 - correctness / placement / geometry (historical release note)

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


## v1.5.1 output saving preferences

In **Advanced options > Export settings**, both **Save audit CSV** and **Save detailed reports** default to OFF. Standard GUI filtering writes only the final filtered IFC. Detailed reports includes timing CSVs and metrics, comparison JSON, reachability JSON, STEP-class CSV, and placement diagnostics; computation and essential validation continue even with reports OFF.

**Audit only (CSV; do not export IFC)** remains a special mode and always writes an audit CSV. Independent geometry and material verification actions intentionally continue writing their requested comparison JSON outputs. Errors are always visible in the in-app processing log; STEP-pruning failures may also leave emergency diagnostics to aid recovery. Advanced 'Both' engine mode necessarily generates two IFC outputs.

CLI behavior remains backward compatible; `--no-audit --no-reports` disables routine reports.

## v1.5.2 UI refinement

- The **Filter IFC** button is centered, bold, and has a fixed comfortable width.
- Choosing or editing a different input IFC clears the previous progress animation, status message, and elapsed time.
- During processing, the input filename field and Browse action cannot change the active source.
- The processing log remains available for the entire session.
- No changes to filter selection, output defaults, or report generation.


## v1.5.2 C2 documentation clarification

- **Batch Cleanup remains the default export engine** and is labeled recommended in the UI. No algorithmic or UI-default changes were made in this documentation update.
- **Standard** remains the default validation level; it does not run complete schema validation. **Full** and independent geometry/material verification remain optional.
- Historical experimental cautions are preserved as development history, not current guidance. Previous project benchmark passes support the default for the tested models, but do not imply exhaustive coverage of IFC2x3/IFC4/IFC4X3 or unknown exporters.

## v1.5.4 Phase 1B — spatial integrity and support-shell checks

Phase 1B updates only the Batch Cleanup structural cleanup and its checks:

- **M3 (nested IfcSpace removal):** resolve ancestor storeys and capture retained product placements for *all* discarded spaces before any space or decomposition relationship is removed. A missing ancestor aborts before space removal. This eliminates file-order dependence for parent/child spaces.
- **M4 (placement parent):** after reparenting spatial containment, verify both the original global transform and `IfcLocalPlacement.PlacementRelTo` against the actual ancestor storey's placement (or an absolute placement if that storey has none). A mismatch fails closed rather than producing a misleading successful IFC. The already-used documented IfcOpenShell placement-editing operation is retained; placement semantics for the two production reference IFCs still require regression testing.
- **m8 (support shells):** after representations are cleared, and again after reopening the export, reject non-selected aggregate shells that retain their own `Representation` or type-provided `RepresentationMaps`. Intentionally retained openings are exempt from this shell-only rule.

**Limitations:** This release does not yet clean up unused type declarations (M1) or alter how type representations are retained. If an aggregate shell is represented by its type, the exporter now **aborts** instead of silently exporting potentially unwanted geometry. A future M1 review should determine whether safe removal of those type-geometry links is appropriate.

**Release gate:** Tests under `tests/test_phase1b_v154.py` include a nested-space synthetic IFC (requiring IfcOpenShell), plus shell invariant tests. Run the manually triggered GitHub Actions Windows workflow and verify the 40 MB and 360 MB reference models, including world-space geometry and material comparison. Do not treat local skipped integration tests as passing the Windows integration stage.

## v1.5.3 Phase 1A (input safety and reliability)

See [PHASE_1A_V153.md](PHASE_1A_V153.md). This update aborts on zero matching elements and duplicate element GlobalIDs; warns on partial requested-material matches; performs early temporary-file checks, cleans up run-created IFC temp files on failure, and stops performance sampling on failure. GitHub Actions now runs a headless real-IFC filter smoke test on the **frozen EXE**. Batch Cleanup and Standard validation remain the GUI defaults; by default only the filtered IFC is saved.


### Manually triggering the Windows build

The GitHub Actions workflow is **manual-only** (`workflow_dispatch`). Uploading or committing source changes does not start a Windows build automatically. To build, open **Actions > Build Windows portable EXE > Run workflow**, select the branch and confirm.

### Frozen EXE smoke-test diagnostics (v1.5.3 build correction)

The GitHub Actions workflow uses Python `subprocess.run` to wait for the frozen GUI-subsystem executable. The executable's `--selftest --selftest-report <path>` mode writes a PASS/FAIL diagnostic to `build-logs/frozen-selftest.txt`, which is uploaded with other build logs even if the step fails. This replaces the unreliable PowerShell `$LASTEXITCODE` check after directly launching a `--windowed` executable.

### v1.5.4.1: placement-parent repair (Phase 1B hotfix)

On some IFC2X3 files, changing a retained element's spatial container and
calling `geometry.edit_object_placement` did not update
`IfcLocalPlacement.PlacementRelTo` to the desired storey. v1.5.4.1 explicitly
recomputes its storey-relative placement when necessary, preserves world-space
coordinates and aborts on unexpected geometry movement. See
`PLACEMENT_HOTFIX_V1541.md`. This hotfix requires GitHub integration tests and
reference-model confirmation before acceptance.


### v1.5.4.2: IFC2X3 owner-history-independent placement repair

The new Phase 1B IFC2X3 integration test in v1.5.4.1 failed in
`ifcopenshell.api.geometry.edit_object_placement`: IfcOpenShell attempted to
update owner history, but the deliberately minimal synthetic IFC had no owner
user configured. This is an integration-test failure, not a demonstrated
world-space geometry mismatch.

For elements being moved from spaces to a known ancestor storey, v1.5.4.2
now directly rebuilds the storey-relative `IfcAxis2Placement3D` and assigns
`IfcLocalPlacement.PlacementRelTo`. The world transform is checked before and
after; unsupported or shared product placements fail closed. The legacy
geometry API remains available only to callers without a supplied target
parent. No changes were made to element selection or serialization.

**Release gate:** Re-run all GitHub real-IfcOpenShell tests, the frozen EXE
smoke test, and both reference-model geometry/material checks. Local tests
without IfcOpenShell skip real integration tests and do not certify this fix.
