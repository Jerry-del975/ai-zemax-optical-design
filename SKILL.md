---
name: ai-zemax-optical-design
description: "Automated optical design agent for Ansys Zemax OpticStudio 2024 R1 through ZOS-API. Use when Codex should automatically turn optical requirements or an existing .zmx/.zos/.zar file into an executable Zemax design loop: parse requirements, create or load a lens model, run baseline analyses, choose variables and constraints, build a merit function, run staged optimization, compare iterations, save final lens files, and produce machine-readable design logs."
---

# AI Zemax Optical Design

Use this skill as an automation agent for Zemax optical design. The deliverable is executable ZOS-API automation, not only design advice.

Target environment: Ansys Zemax OpticStudio 2024 R1, with default install path `D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00`.

## Operating Contract

Always drive toward these artifacts:

- A normalized requirements JSON with explicit assumptions.
- A runnable ZOS-API Python script or patched scaffold.
- Baseline analysis exports before optimization.
- A staged variable/constraint/merit-function plan.
- Versioned lens saves for accepted stages.
- A final design log with metrics, constraints, changes, and unresolved risks.

Do not stop at conceptual optical-design suggestions unless the user explicitly asks only for theory.

## Automation Flow

1. Parse input.
   - Normalize requirements with `references/requirements-schema.md`.
   - If an existing `.zmx`, `.zos`, or `.zar` is provided, load it first and extract baseline fields, wavelengths, aperture, configurations, prescription, and merit state.
   - Mark assumptions in the log instead of silently inventing constraints.

2. Create or load the Zemax model.
   - Prefer loading an existing model when provided.
   - For new designs, create a minimal sequential starting model from first-order requirements, then set surfaces, aperture, fields, wavelengths, stop, image plane, and materials.
   - For zoom designs, set multi-configuration data before optimization.

3. Run baseline evaluation.
   - Export first-order data, prescription, spot, FFT MTF, wavefront, ray fan, and field curvature/distortion.
   - Add domain-specific analyses when relevant.
   - Parse raw analysis text into metrics JSON where practical.

4. Select variables and constraints.
   - Choose variables in stages: focus/air gaps, curvatures, thicknesses, glass substitutions, aspheres, multi-configuration solves, tolerance compensators.
   - Encode hard feasibility constraints before image quality goals.

5. Build and run the merit function.
   - Use `references/merit-function.md`.
   - Run staged optimization: feasibility, image quality, field balance, manufacturability, optional tolerance readiness.
   - Save lens and metrics after each stage.

6. Compare and accept iterations.
   - Compare each candidate against baseline, previous accepted design, and user targets.
   - Reject candidates that improve one score by creating hidden geometry, glass, aperture, field, or tolerance failures.

7. Report outputs.
   - Return final lens path, intermediate lens paths, analysis output paths, design log path, performance versus targets, assumptions, and manual checks still needed.

## Scripts

- `scripts/automated_design_agent.py`: controller for the automated design loop.
- `scripts/zos_design_primitives.py`: Zemax 2024 R1 ZOS-API connection, analysis export, save, metrics, and optimization primitives.
- `scripts/connection_smoke_test.py`: quick connection test for Standalone or Interactive Extension.
- `scripts/connection_smoke_test.ps1`: PowerShell smoke test that loads the 2024 R1 DLLs directly when Python lacks `pythonnet`.
- `scripts/design_single_lens_interactive.ps1`: live Interactive Extension smoke design that creates a simple N-BK7 singlet, saves lens files, and exports analyses.
- `examples/minimal_imaging_requirements.json`: small sample input for smoke-testing the automated design controller.

## References

- `references/requirements-schema.md`: normalized input schema.
- `references/merit-function.md`: staged merit-function and variable-selection rules.
- `references/result-parsing.md`: analysis export, parsing, comparison, and logging rules.
- `references/zos-api-patterns.md`: OpticStudio 2024 R1 ZOS-API reminders.

Load only the reference files needed for the active task.

## Connection Diagnostics

For Python automation, `pythonnet` is required. If `import clr` fails, install `pythonnet` in the Python environment used to run the script, or use `scripts/connection_smoke_test.ps1` to verify OpticStudio DLL and license state first.

Default to Interactive Extension for live testing because Standalone may crash or hang when the API license/session is unhealthy. Use Standalone only when explicitly requested or after the smoke test passes.

Expected healthy connection:

- Standalone: `CreateNewApplication()` returns an application, `IsValidLicenseForAPI=True`, and `PrimarySystem` is not null.
- Interactive Extension: OpticStudio must be open in an extension-ready state; `ConnectAsExtension(0)` must return an application with valid API license and primary system.

If a connection object exists but `IsValidLicenseForAPI=False` or `PrimarySystem` is null, treat it as not usable for automation and fix the OpticStudio extension/license state before running the design loop.

Do not retry Standalone repeatedly after an OpticStudio exception dialog or timeout. Clear the dialog, restart OpticStudio if needed, then validate Interactive Extension first with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\connection_smoke_test.ps1
```
