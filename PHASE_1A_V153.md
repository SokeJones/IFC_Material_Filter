# v1.5.3 — Phase 1A safety and reliability

Scope: C1, M7, M8, m4, frozen-EXE smoke test. **No intentional changes to IFC element-selection semantics for valid files**, geometry, type inheritance, aggregate handling, or default UI options.

- **C1:** If no matching elements exist, export fails before writing an audit or IFC. Near-match suggestions use names actually defined as `IfcMaterial.Name`. A partially matched multi-name request produces a **warning** and continues for matching names; carefully check the processing log before using output.
- **M8:** Duplicate `IfcElement.GlobalId` occurrences cause a fail-closed error before material processing. Repair the source IFC rather than silently deduplicating objects.
- **M7:** Refuse existing `.incomplete.ifc` and `.unpruned.incomplete.ifc` temporary files in preflight. On exceptions during the export finalization, remove only the temporary files created by that run. Do not overwrite existing IFC files. Unremovable files are reported in the processing log. IfcPatch cleanup is also improved.
- **m4:** Selection performance sampler always stops via `finally`, even during source-open or selection failures; engine samplers retain their existing `finally` behavior.
- **Build:** GitHub Actions runs an actual synthetic IFC4 filter through the *frozen Windows EXE* using `--selftest`, confirms retained and excluded elements, and asserts the default single-IFC-only output. This is in addition to source-level tests.

Default UI remains **Batch Cleanup / Standard validation / no audit / no detailed reports**. Manual geometry and material verification remain available in Advanced Options.

**Verification status:** Local tests (without IfcOpenShell) exercise input-safety helpers, code compilation and packaging. The IfcOpenShell-dependent integration tests and frozen-EXE smoke test must run on the Windows GitHub Actions runner before the release is considered validated. Re-run reference models before promotion to production use.
