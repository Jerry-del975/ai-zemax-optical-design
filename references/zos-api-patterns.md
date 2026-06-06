# ZOS-API Patterns for OpticStudio (v20.3+)

## Connection

Connection is handled by **ZOSPy** (`pip install zospy`). ZOSPy auto-discovers the OpticStudio
installation; no paths or DLL names need to be hardcoded.

- `connect_zemax()` (in `zos_design_primitives.py`) creates a `zospy.ZOS()` instance, calls
  `zos.connect("extension")` or `zos.connect("standalone")`, and returns the raw ZOS-API
  application object — downstream code works unchanged.
- Interactive Extension: OpticStudio must be open and extension-ready.
- Standalone: ZOSPy creates a new OpticStudio instance.
- Always close analyses/tools and call `CloseApplication()` for Standalone sessions.

## Lens Data

Surfaces, wavelengths, fields, and configurations are commonly 1-based.

Use `surf.Material` for 2024 R1, not `MaterialName`.

## Analyses

Use `system.Analyses.New_*()` and `ApplyAndWaitForCompletion()`.

Common factories:

- `New_StandardSpot`
- `New_FftMtf`
- `New_WavefrontMap`
- `New_RayFan`
- `New_FieldCurvatureAndDistortion`
- `New_SeidelDiagram`

## Optimization

Use `system.Tools.OpenLocalOptimization().RunAndWaitForCompletion()` for local optimization. Do not trust merit score alone; inspect geometry and per-field performance.
