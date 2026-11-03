# IFC Material Filter — Windows (multiple materials)

**Version 1.1 — removal stability fix (2026-11-03)**

Standalone filtering of IFC2X3/IFC4 models using IfcOpenShell.

## Input
- Choose an `.ifc` file.
- Enter **one material name per line**, or separate names using semicolons.
- Names are matched *case-insensitively*, but otherwise exactly; a comma can be part of a material name.
- **OR selection**: retain an element if **any** requested material is found.
- Direct occurrence material takes precedence over type material.
- Composite material layer/constituent sets match if at least one constituent matches.
- Optional parent-based candidate selection: `aggregates` (default), `aggregates+nests`, or `none`. Parent association is **not normative inheritance**. Children with their own material are **not** included solely because of parent material.
- Parent assembly shells and openings required by selected elements are retained as geometry-free parent objects / supporting openings. Spatial hierarchy remains.

## Output
- New `<name>_filtered.ifc` file (never overwrites an existing file)
- `<name>_filtered.audit.csv`: detailed report of KEEP/REMOVE for every IfcElement
- For very large models (hundreds of MB), output can take substantial time and memory.

## Build a Windows executable without local Python or administrator rights
**A Windows .exe is not included in this source ZIP.** A ready-to-build GitHub Actions workflow is included.
1. Create a **private** repository at https://github.com/new (no IFC data needs to be uploaded).
2. Upload the package source files, including `.github/workflows/build-windows.yml` (the hidden `.github` directory must be preserved). Alternatively `git push` the project directory.
3. In the repo's **Actions** tab, select **Build Windows portable EXE** -> **Run workflow** (may require enabling Actions in repo settings).
4. After the run succeeds, download the `IFC_Material_Filter_Windows` artifact, unzip it, then unzip `IFC_Material_Filter_Windows.zip` inside. The resulting `IFC_Material_Filter.exe` can be run from a writable Windows folder without installing Python or IfcOpenShell.
5. Corporate Windows Defender / SmartScreen / AppLocker policies may still block an unsigned executable. Company IT may need to approve it. This package does not bypass those policies.

**Privacy:** GitHub only receives application source code; keep the actual project IFC local. Using a private repository reduces source code exposure, but GitHub Actions still processes the build. Read your organisation's policies first.

## For developers
On Windows, install Python 3.12 and run `python -m pip install -r requirements.txt` then `python app.py`.
CLI: `python cli.py model.ifc filtered.ifc --material "Stahlbeton Schweiz" --material "Beton C30/37"`

## Limits and validation
- Requires IfcOpenShell on the build runner.
- Currently targets `IfcElement` occurrences, not standalone annotations or nonphysical products.
- Does not perform shape-by-shape geometric validation; reopen in BIMcollab Zoom to review openings, element placement, geometry and quantities before downstream use.
- The script is syntax-checked but has **not** been end-to-end tested in this environment because IfcOpenShell installation is blocked here. Do not use the result as a final production model without checking.
- This software is provided as source with no warranty. Keep the unmodified original.

## Version 1.1: Fix for `invalid null reference` during export
Earlier builds used `ifcopenshell.api.root.remove_product`, which recursively
removes property sets and can fail on shared or invalidated property-set handles.
This release replaces that call with `safe_remove.detach_and_remove_product`.
It first removes the unwanted product's membership from IFC relationships,
then deletes the product itself. Shared property sets and other supporting
resources are **not** recursively deleted. This can leave unused geometry or
property entities in the filtered IFC, resulting in a larger-than-minimal file.
The filtered file should contain only retained IfcElement occurrences, support
openings and necessary parent shells, but must still be reviewed in a viewer.

The output validation no longer reads deleted product handles. The GitHub
Actions workflow runs the regression suite before compiling the executable.

**To update an older GitHub repository:** replace `filter_engine.py`, add
`safe_remove.py`, and replace `.github/workflows/build-windows.yml`. Commit and
run the build workflow to obtain a NEW Windows executable. Do not continue
using the old `.exe`; changing source files alone does not update it.

**Testing:** 8 unit tests passed, including shared-property-set removal. Full
IFC processing remains unverified here because IfcOpenShell is not available
in this container. A Windows build and a visual review are required.
