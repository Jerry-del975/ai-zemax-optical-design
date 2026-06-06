# ZOS-API Patterns for OpticStudio 2024 R1

## Connection

- Default install root: `D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00`.
- Standalone mode: `ZOSAPI.ZOSAPI_Connection().CreateNewApplication()`.
- Interactive Extension: `ConnectAsExtension(0)` after OpticStudio is open and extension mode is available.
- 2024 R1 commonly stores `ZOSAPI_NetHelper.dll`, `ZOSAPI_Interfaces.dll`, and `ZOSAPI.dll` in the install root.
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
