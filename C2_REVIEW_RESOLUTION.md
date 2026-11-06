# Code review C2 — decision and disposition

**Decision:** Keep Batch Cleanup as the default and recommended GUI engine.

**Reason:** The project's 40 MB and 360 MB models passed independent structural, world-space tessellated-geometry and effective-material comparisons, with no reported additional schema-error count in the final v1.4.6 tests. This is enough evidence for the project default; it is not a proof for arbitrary models.

**Documentation corrected:** Removed the obsolete default “Full validation” wording; explained that Standard (`basic`) is the GUI default and does not run full schema validation or orphan-placement diagnostics; clarified optional Full, geometry and material checks; changed the Batch engine docstring and current README heading to reflect validated project-default status; replaced the obsolete “v1.3 production fallback” direction and demarcated historical notes.

**Unchanged:** export engine, filter/cleanup logic, GUI default `engine=batch`, GUI default `validation=basic`, advanced controls, output preferences, GitHub Actions workflow.

**Remaining independent findings:** C1 (zero selection), M1–M9 and other code-review items were *not* resolved by this C2-only change. They should be assessed separately; in particular C1 remains potentially important for normal use.
