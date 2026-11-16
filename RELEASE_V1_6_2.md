# IFC Material Filter v1.6.2 — local SSD workspace reliability release

## Scope

Built on accepted v1.6.1. The validated material selection, aggregation, relationship repair, reachability and STEP-pruning rules are unchanged. No m10/m12 algorithm optimizations.

## What changed

- `local_workspace.py` owns an isolated per-run local directory under `%LOCALAPPDATA%\IFCMaterialFilter\Work` (fallback `TEMP`, `TMP`, `USERPROFILE` if on a **local fixed disk**). UNC/network temporary directories are rejected.
- Before B00, Batch creates a local workspace and requires available space of at least `max(1 GiB, 3 × input-file bytes + 512 MiB)`. This is a conservative threshold, not a guaranteed upper bound; a full disk still causes an error and cleanup attempt.
- B06 writes `unpruned.ifc` locally, B07 writes `pruned.ifc` locally, B08/B09/B10 validate locally. B11 copies the validated IFC to a unique `.<run-uuid>.publishing.incomplete.ifc` staging filename **on the destination filesystem**, flushes it, and only then renames it to the final name (Windows). A pre-existing final output remains protected. For POSIX test environments, a no-overwrite hardlink is used.
- The optional IfcPatch engine also uses local temporary IFC storage and final staged publication.
- Standard completion and handled errors clean the workspace. Each run holds an exclusive OS file lock to prevent recovery from deleting active sessions. Next application startup (and export attempts) clean identifiable abandoned workspaces, including their associated destination staging files.
- Cleanup is best-effort under forced termination, server unavailability or power loss: **nothing can guarantee instantaneous deletion after a hard crash without a later recovery process**. Recovery is attempted on the next run. If destination staging deletion fails, metadata is retained for another retry. Do not manually delete other application instances' work directories.
- Legacy `.unpruned.incomplete.ifc` files from v1.6.1 are NOT automatically removed (ownership unknown).
- Diagnostic CSV/JSON and user-requested final output remain in the selected destination as before.

## Platform considerations

Portable EXE requires no administrator privileges. Startup recovery runs asynchronously in the GUI. A Windows-compatible exclusive file lock is implemented using `msvcrt.locking` and a fallback `fcntl` implementation is used on POSIX tests. Final publish is a per-share rename, not a durable transaction: a network disconnect can leave an orphan staging filename, which is recovered when access returns.

## Tests

- Run `python -m unittest discover -s tests -v` on GitHub Actions (IfcOpenShell integration tests included).
- Verify the existing frozen-EXE headless smoke test.
- Verify the new unit tests covering local-only B06/B07/B08, final publication, collision prevention, copy failure, active locks, and a subprocess terminated by `os._exit()` then recovered.
- With the 40 MB, 360 MB and new 435 MB reference models, compare selected and retained GlobalIDs, model geometry/material verification, placement diagnostics and output IFC integrity. Execute at least one network-output test, ensuring B06 is local and B11 performs the copy.
- Manually terminate an EXE during B06 and B11, relaunch, and verify workspace/staging cleanup. Test with a disconnected network output and insufficient free local disk space before accepting v1.6.2.

## Acceptance status

Python compilation and 115 local tests: **101 passed, 14 skipped** (native IfcOpenShell unavailable in this container). Windows execution, real IFC regression and forced-close tests on Windows are **still pending**. Keep v1.6.1 EXE as rollback.
