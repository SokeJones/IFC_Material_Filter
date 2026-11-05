# GitHub Actions build troubleshooting (v1.4.6 build-fix)

The GitHub status message `Process completed with exit code 1` is generic. Expand the red step to identify the failing command.

## Build
1. Replace all files in the repository with this kit's source files, preserving `.github/workflows/build-windows.yml` (the `.github` directory is hidden on some systems).
2. Open **Actions** > **Build Windows portable EXE** > **Run workflow**.
3. If it fails, open the failed run and expand the **first red step**.
4. Download artifact `IFC_Material_Filter_Build_Logs`, available even for a failed run once the diagnostics step completes. Share `tests.txt` or `pyinstaller.txt`, and the first red step.
5. If the run succeeds, download `IFC_Material_Filter_Windows`. This contains the portable EXE ZIP.

The workflow deliberately fails if any integration tests fail. Do NOT skip or suppress failing tests just to obtain the EXE. The workflow does not alter the filtering algorithm.

This build-fix was syntax checked and the Python-only tests run locally. A full Windows execution with IfcOpenShell installed has not been performed here.

## Build-fix 2: unavailable placement API
The previous Windows integration failure was `AttributeError: ...placement has no attribute get_placement`. Build-fix 2 replaces all three occurrences and uses `get_local_placement` supported by the pinned package. The release remains subject to a successful GitHub Actions integration run.
