---
name: ai-zemax-optical-design
description: "Automated optical design agent for Ansys Zemax OpticStudio 2024 R1 through ZOS-API. Use when Codex should automatically turn optical requirements or an existing .zmx/.zos/.zar file into an executable Zemax design loop: parse requirements, create or load a lens model, run baseline analyses, choose variables and constraints, build a merit function, run staged optimization, compare iterations, save final lens files, and produce machine-readable design logs. Supports both prime lenses and multi-configuration zoom systems."
---

# AI Zemax Optical Design

Use this skill as an automation agent for Zemax optical design. The deliverable is executable ZOS-API automation, not only design advice.

Target environment: Ansys Zemax OpticStudio v20.3+, with ZOSPy handling version discovery and API connection.

## Operating Contract

Always drive toward these artifacts:

- A normalized requirements JSON with explicit assumptions.
- A seed-design selection record when an official or catalog case can shorten the path to a valid design.
- A runnable ZOS-API Python script or patched scaffold.
- Baseline analysis exports before optimization.
- A staged variable/constraint/merit-function plan.
- Versioned lens saves for accepted stages.
- A final design log with metrics, constraints, changes, and unresolved risks.

Do not stop at conceptual optical-design suggestions unless the user explicitly asks only for theory.

For complex lens families, treat the existing multi-round scoring / optimization scaffold as stable infrastructure and do not rewrite it in this pass.

## Hard Constraints

- Do not invent a starting architecture when a closer official or catalog seed is available.
- Do not silently switch from a seed-based workflow to a from-scratch workflow.
- Do not broaden the problem scope beyond the user's requested lens class, focal-length range, aperture, and packaging limits.
- Do not treat a weakly similar seed as acceptable unless the mismatch is explicitly logged.
- Do not begin optimization until the seed selection, target normalization, and structural gap list are complete.
- Do not claim a design is suitable for the target if the seed-to-target gap is still unaccounted for.
- Do not fill missing structural details with guesses; record them as assumptions or ask for user confirmation.
- Do not modify the user's requested class of lens to make the problem easier.
- Do not replace the staged optimization logic; preserve the existing feasibility -> image quality -> field balance -> manufacturability flow unless the user explicitly requests a different strategy.

## Complex-Design Guardrails

- Use a conservative interpretation for difficult lenses: prioritize structural fidelity, convergence stability, and traceable changes over aggressive optimization.
- Treat large family mismatches as blocking until the structural gap is explained and logged.
- Prefer the nearest seed that matches the requested optical family, zoom behavior, aperture regime, and packaging constraints, even if the focal length is imperfect.
- If the best available seed is only a partial match, log the exact mismatch and the adaptation burden before proceeding.
- For difficult designs, do not expand degrees of freedom just to force convergence; increase them only when the current stage and gap analysis justify it.

## Automation Flow

1. Parse input.
   - Normalize requirements with `references/requirements-schema.md`.
   - If an existing `.zmx`, `.zos`, or `.zar` is provided, load it first and extract baseline fields, wavelengths, aperture, configurations, prescription, and merit state.
   - Mark assumptions in the log instead of silently inventing constraints, and include seed provenance for any adopted starting design.
   - For new designs, search first for the closest official Zemax example or catalog/reference lens with the same structural family, then adapt from that seed instead of starting from a blank system.
   - For fast zoom imaging tasks such as an F/1.4, 3x zoom, 18-55 mm-style lens, prefer a structurally similar zoom seed and record the match criteria.
   - If no clearly relevant seed is available, stop and report the missing structural basis instead of improvising a new architecture.
   - Record the structural gap list before any optimization so the adaptation burden is explicit.

2. Create or load the Zemax model.
   - Prefer loading an existing model when provided.
   - For new designs, choose the best seed design first, then adapt it to the requested focal-length range, aperture, field, and packaging limits.
   - When no suitable seed exists, create a minimal sequential starting model from first-order requirements, then set surfaces, aperture, fields, wavelengths, stop, image plane, and materials.
   - For zoom designs, set multi-configuration data before optimization.
   - Keep the seed architecture stable during the initial adaptation stage; do not add, remove, or reorder groups without logging the reason.

3. Run baseline evaluation.
   - Export first-order data, prescription, spot, FFT MTF, wavefront, ray fan, and field curvature/distortion.
   - Add domain-specific analyses when relevant.
   - Parse raw analysis text into metrics JSON where practical.

4. Select variables and constraints.
   - Choose variables in stages: focus/air gaps, curvatures, thicknesses, glass substitutions, aspheres, multi-configuration solves, tolerance compensators.
   - Encode hard feasibility constraints before image quality goals.
   - Only vary parameters that preserve the current structural intent unless the user explicitly approves a structural change.

5. Build and run the merit function.
   - Use `references/merit-function.md`.
   - Run staged optimization: feasibility, image quality, field balance, manufacturability, optional tolerance readiness.
   - Save lens and metrics after each stage.
   - If a stage fails, fix the failure at the current stage rather than jumping ahead to a later one.

6. Compare and accept iterations.
   - Compare each candidate against baseline, previous accepted design, and user targets.
   - Reject candidates that improve one score by creating hidden geometry, glass, aperture, field, or tolerance failures.
   - Preserve seed-design provenance so the final log explains how the result diverged from the starting case.
   - Reject any candidate that changes the lens class, zoom behavior, or complexity envelope without explicit user approval.
   - Log any new assumption introduced during optimization immediately, with the reason it was needed.

7. Report outputs.
   - Return final lens path, intermediate lens paths, analysis output paths, design log path, performance versus targets, assumptions, and manual checks still needed.

## Scripts

- `scripts/automated_design_agent.py`: controller for the automated prime-lens design loop.
- `scripts/zoom_lens_design_agent.py`: controller for multi-configuration zoom lens design with MCE setup, variable air gaps, and per-configuration optimization.
- `scripts/zos_design_primitives.py`: ZOS-API connection (pythonnet with ZOSPy fallback), analysis export, save, metrics, and optimization primitives. Supports OpticStudio 2024 R1+.
- `scripts/connection_smoke_test.py`: quick connection test for Standalone or Interactive Extension.
- `scripts/connection_smoke_test.ps1`: PowerShell smoke test that loads the OpticStudio DLLs directly when Python lacks `pythonnet`.
- `scripts/design_single_lens_interactive.ps1`: live Interactive Extension smoke design that creates a simple N-BK7 singlet, saves lens files, and exports analyses.
- `examples/minimal_imaging_requirements.json`: small sample input for smoke-testing the automated design controller.
- `examples/apsc_18-55_f1.4_zoom_requirements.json`: APS-C 18-55mm F/1.4 3× zoom lens requirements with three zoom configurations (wide/mid/tele).

## References

- `references/requirements-schema.md`: normalized input schema.
- `references/merit-function.md`: staged merit-function and variable-selection rules.
- `references/result-parsing.md`: analysis export, parsing, comparison, and logging rules.
- `references/zos-api-patterns.md`: OpticStudio 2024 R1 ZOS-API reminders.

Load only the reference files needed for the active task.

## Seed-Design Policy

For complex optical structures, especially zoom lenses, the default strategy is:

1. Find the closest official Zemax example or a catalog/reference lens in the same structural family.
2. Compare candidate seeds against the request on these axes:
   - focal-length span
   - aperture and entrance pupil behavior
   - number of groups and elements
   - zoom mechanism and conjugate behavior
   - field of view and image format
   - package length and back focal space
   - glass strategy and asphere usage
3. Pick the best structural match as the seed design and log the gaps explicitly.
4. Adapt the seed in small stages instead of redrawing the system from scratch.
5. Keep seed provenance, mismatch notes, and any manual structural edits visible in the final design log.

For a fast 3x zoom 18-55 mm lens at F/1.4, bias toward the nearest zoom imaging seed even if it is not an exact focal-length match.

## Connection Diagnostics

For Python automation, **pythonnet** (`pip install pythonnet`) is required. ZOSPy (`pip install zospy`) is also supported as an alternative connection layer.

Default to Interactive Extension for live testing because Standalone may crash or hang
when the API license/session is unhealthy. Use Standalone only when explicitly requested
or after the smoke test passes.

Expected healthy connection:

- Standalone: `CreateNewApplication()` returns an application, `IsValidLicenseForAPI=True`, and `PrimarySystem` is not null.
- Interactive Extension: OpticStudio must be open in an extension-ready state; `ConnectAsExtension(0)` must return an application with valid API license and primary system.

If a connection object exists but `IsValidLicenseForAPI=False` or `PrimarySystem` is null,
treat it as not usable for automation and fix the OpticStudio extension/license state before
running the design loop.

Do not retry Standalone repeatedly after an OpticStudio exception dialog or timeout.
Clear the dialog, restart OpticStudio if needed, then validate Interactive Extension first with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\connection_smoke_test.ps1
```

### ZOS-API Quirks (2024 R1)

- `system.LDE.StopSurface = N` — set stop by property, not `MakeSurfaceStop()`.
- `system.MFE` — access merit function editor directly, not via `Tools.OpenMeritFunction()`.
- MCE: `AddConfiguration(True)` — takes bool, not int.
- MCE: `ChangeType(MultiConfigOperandType.THIC)` — use enum, not string.
- Optimization wizard: `wizard.OK()` not `Ok()`. Properties: `Ring`, `Arm`, `Data` (singular).
- Python.NET 3.0: cannot assign `int` to enum properties (e.g. `tool.Cycles`).
- `SaveAs()` requires absolute paths; relative paths may fail with non-ASCII directories.
