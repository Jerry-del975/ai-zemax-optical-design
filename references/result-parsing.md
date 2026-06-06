# Result Parsing and Logging

Automated design needs comparable metrics, not only raw Zemax text files.

## Artifacts Per Stage

- Saved lens file: `stage-N-name.zmx` or `.zos`.
- Raw analysis outputs under `analyses/stage-N-name/`.
- Parsed metrics JSON: `metrics-stage-N-name.json`.
- Design event appended to `design-log.jsonl`.

## Core Metrics

Capture merit value, EFL, BFL, F/# or NA, total track, RMS spot, MTF, distortion, field curvature, astigmatism, wavefront, and constraint violations.

## Parsing Rules

- Zemax text output may be UTF-16; try UTF-16 first, then UTF-8.
- Keep raw text files even when parsing fails.
- Use stable metric keys so stages can be compared programmatically.
- Report per-field and per-wavelength regressions instead of hiding them inside averages.
