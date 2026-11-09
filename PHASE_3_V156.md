# Phase 3 — IFC Material Filter v1.5.6

**Basis:** validated v1.5.5 implementation. Phase 2 audit CSV was confirmed correct using v1.5.5, so the optional v1.5.5.1 audit patch is not included. All material selection, geometry pruning, type handling, support object rules, spatial reparenting and failure-safe export semantics are retained.

## Implemented

| Finding | Resolution | Risk |
|---|---|---|
| m1 — CLI semicolon parsing | `parse_materials` now splits **each list entry** by semicolons and line breaks; preserves trimming, case-insensitive deduplication and OR semantics | Low |
| m2 — hard-coded version | New `version.py` exports `__version__ = '1.5.6.1'`; GUI title and comparison JSON both use it | None to IFC |
| m3 — timing overwritten | Selection/original-IFC-baseline timing now uses `*.selection.timing.csv` and `*.selection.timing.metrics.csv`; engine timing keeps `*.timing.csv` / `*.timing.metrics.csv`. The comparison JSON references selection timing | Diagnostic only |
| m5 — audit-only success | GUI shows **Audit completed — no IFC exported** and does not require manually entering an output IFC filename in audit-only mode. The CLI can omit the output path with `--dry-run` | Low |
| m6 — dead argument and tolerance | Removed unused `opening_ids` from `validate_extraction` signature. Geometry comparison now uses actual placement matrices and `math.isclose`, applying the requested project-unit tolerance to translation and a separate `1e-8` dimensionless tolerance to orientation. This prevents rounding-boundary false mismatches | Only optional geometry verifier changes |
| m7 — wrong wrapper-count comment | The counter uses `len(model)` only for objects that support it. IfcOpenShell 0.8.5 files do **not** implement `__len__`; the original iterator-based counting remains in use. v1.5.6.1 fixes the incompatible test assumption. STEP pruning and validation remain unchanged | Diagnostic only; no real-IFC speedup claimed |
| m9 — documentation | Updated version, CLI examples, GUI labels, optional report paths, limits and release status | None |
| m11 — hard-coded developer example | Material input field starts blank. The multiline/semicolon hint remains. Documentation provides a neutral concrete/steel example; existing exact matching is unchanged | User input only |

**CLI defaults also now match everyday GUI defaults:** Batch Cleanup, Standard validation, only filtered IFC output. Audit and diagnostic files are explicitly opt-in via `--save-audit` and `--save-reports`. Legacy `--no-audit` and `--no-reports` remain accepted as redundant compatibility switches.

## Performance findings: m10 and m12

Based on the supplied 360 MB v1.5.5 Full validation timing CSV:

| Stage | Measured time |
|---|---:|
| B02 — remove products / repair relationship membership | **41.98 s** |
| B03b — presentation-layer clipping, including reachability check | **2.42 s** |
| B04 — primary reachability index | **10.89 s** |
| B05 — count unreachable entities | **17.16 s** |
| B06 — serialize edited IFC | **47.31 s** |

- **m10:** B03b's complete elapsed time is about 1.3% of the 187.89 s Batch engine run. Its internal extra reachability pass is a subset of that 2.42 s. Do not change reachability semantics to optimize this yet.
- **m12:** B02 is a significant measured cost (41.98 s). A single model does **not** establish the predicted O(n²) relationship-size scaling. Preserve proven relationship edits and investigate with synthetic models at several relationship sizes before refactoring.
- **m7:** B05 remains a high-cost **diagnostic counter** on IfcOpenShell 0.8.5. The optional constant-time path is not available on its `file` class. The integration test now verifies the actual reachable/unreachable counts instead of assuming `len(model)` exists. Future optimization requires a separately verified approach.

No unverified relationship-removal or reachability algorithm optimization is included. These two investigations may be addressed in a dedicated future performance version if scaling tests demonstrate a meaningful benefit.

## Acceptance checks

1. GitHub Actions is **manual `workflow_dispatch` only**. Source regression/integration suite, packaging and frozen EXE self-test must pass.
2. GUI: material names field starts empty; hint, centered bold button, progress reset, Advanced Options and session log remain.
3. Routine run creates only filtered IFC; enabling reports creates **separate** selection and engine timing CSV files; audit-only creates CSV and never claims IFC export.
4. Small model: 2,415 selected, 3,333 retained IFC elements. Large model: 2,417 selected, 3,337 retained.
5. Run optional geometry and material verification on both reference models; expect zero mismatches and no unverified elements. The geometry verifier's placement comparison method has changed, so both reference models should be checked again.
6. Large model Full validation: original and filtered each had four reported `IfcSite` errors in v1.5.5, with **zero orphan placements**. Confirm no newly introduced error categories.
7. Check new comparison JSON `application_version: 1.5.6.1`, and separate selection/engine timing reports.

**Release status:** Local tests do not exercise real IfcOpenShell; full GitHub Actions and user reference-model regression checks remain required before acceptance.
