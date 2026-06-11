# AI Zemax Optical Design

Automated optical design skill for **Claude Code** — drives **Ansys Zemax OpticStudio** through ZOS-API to turn optical requirements into executable, multi-stage design loops.

[![version](https://img.shields.io/badge/version-1.2.0-blue)](https://github.com/Jerry-del975/ai-zemax-optical-design)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## What's New in v1.2.0

- **Zoom lens design agent** — new `scripts/zoom_lens_design_agent.py` for multi-configuration zoom systems with automatic MCE setup, staged optimization, and per-configuration analysis export.
- **APS-C 18-55mm F/1.4 example** — complete zoom requirements and 4-group starting prescription with 3× zoom ratio, constant F/1.4 aperture.
- **Hardened ZOS-API patterns** — fixed real-world API mismatches discovered during intensive testing: `MultiConfigOperandType` enum usage, MCE `AddConfiguration` signatures, optimization wizard property names, `LDE.StopSurface`, Python.NET 3.0 enum handling, and more.
- **Automated analysis export** — per-configuration spot, MTF, wavefront, ray fan, and distortion analyses for every stage.
- **Extended merit function builder** — built-in optimization wizard integration plus first-order targets (EFFL, WFNO, REAY, AXCL, LACL, DIMX) and manufacturing constraints (MNCT, MNET, MNEA, MXSD, MNEG, GCOS).

## What's New in v1.1.0

- **ZOSPy integration** — connection layer uses [ZOSPy](https://github.com/MREYE-LUMC/ZOSPy) for version discovery. Falls back to pythonnet for direct API access when needed.
- **Multi-version support** — OpticStudio v20.3 through v26+.
- **Dual-mode connection** — Interactive Extension (recommended) and Standalone.

---

## Installation

```bash
# Clone the repo
git clone https://github.com/Jerry-del975/ai-zemax-optical-design.git
cd ai-zemax-optical-design

# Install Python dependencies
pip install zospy pythonnet

# Install as Claude Code skill
npm install
```

The postinstall script deploys the skill to `~/.claude/skills/ai-zemax-optical-design/`. Restart Claude Code and the skill is ready.

### Prerequisites

| Component | Requirement |
|-----------|-------------|
| **OS** | Windows 10/11 |
| **OpticStudio** | 2024 R1 (tested), v20.3+ (via ZOSPy) |
| **Python** | 3.10+ |
| **Python packages** | `zospy>=2.1`, `pythonnet` |
| **Claude Code** | latest |

---

## Quickstart

### 1. Smoke test connection

Make sure OpticStudio is open, then:

```bash
python scripts/connection_smoke_test.py
# Expected: "Connected: yes"
```

### 2. Design a lens

**Simple prime lens:**
```bash
python scripts/automated_design_agent.py \
  --requirements examples/minimal_imaging_requirements.json \
  --out output/my-design
```

**Zoom lens (APS-C 18-55mm F/1.4):**
```bash
python scripts/zoom_lens_design_agent.py \
  --requirements examples/apsc_18-55_f1.4_zoom_requirements.json \
  --out output/aps-c-zoom
```

### 3. Review results

```
output/aps-c-zoom/
├── zoom_baseline.zmx          ← Baseline lens (before optimization)
├── zoom_feasibility.zmx       ← After feasibility stage
├── zoom_image-quality.zmx     ← After image quality optimization
├── zoom_field-balance.zmx     ← After field balancing
├── zoom_manufacturability.zmx ← Final lens (all stages)
├── design-log.jsonl           ← Machine-readable event log
├── metrics-*.json             ← Per-stage merit values
├── requirements.json          ← Normalized requirements (copy)
└── analyses/
    ├── baseline/              ← 5 analyses × 3 configurations
    ├── feasibility/
    ├── image-quality/
    ├── field-balance/
    └── manufacturability/
```

---

## What It Does

This skill turns Claude Code into a Zemax automation agent:

1. **Parse requirements** — normalize optical specs from JSON or existing `.zmx` / `.zos` / `.zar` files
2. **Build or load models** — create sequential starting prescriptions (prime or zoom), or adapt existing designs
3. **Setup multi-configuration** — automatic MCE operand setup for zoom systems with variable air gaps
4. **Run baseline analyses** — spot diagrams, FFT MTF, wavefront maps, ray fans, field curvature/distortion
5. **Stage optimization** — feasibility → image quality → field balance → manufacturability
6. **Export everything** — versioned lens files, analysis text exports, metrics JSON, and design logs

---

## Project Structure

```
├── SKILL.md                              # Skill definition (loaded by Claude Code)
├── README.md
├── package.json
├── install.js                            # Postinstall: deploys skill to ~/.claude/skills/
│
├── scripts/
│   ├── zos_design_primitives.py          # Core: connection, analysis, optimization, save
│   ├── automated_design_agent.py         # Prime lens design controller
│   ├── zoom_lens_design_agent.py         # ★ Multi-config zoom design controller (new)
│   └── connection_smoke_test.py          # Quick ZOS-API health check
│
├── references/
│   ├── requirements-schema.md            # Normalized input schema
│   ├── merit-function.md                 # Staged merit-function rules
│   ├── result-parsing.md                 # Analysis export & logging rules
│   └── zos-api-patterns.md               # ZOS-API 2024 R1 reference
│
├── examples/
│   ├── minimal_imaging_requirements.json
│   ├── apsc_18-55_f1.4_zoom_requirements.json  # ★ APS-C zoom example
│   └── seeded_complex_zoom_requirements.json
│
├── tests/
│   ├── test_zos_design_primitives.py
│   ├── test_automated_design_agent.py
│   └── test_requirements_schema.py
│
└── output/                               # ★ Design outputs (gitignored)
```

---

## Supported Design Types

| Type | Agent | Features |
|------|-------|----------|
| Prime lens | `automated_design_agent.py` | Single-config, EFFL/BFL/F# targets |
| Zoom lens | `zoom_lens_design_agent.py` | Multi-config MCE, variable air gaps, per-config EFL |
| Seed-based | `automated_design_agent.py` | Load `.zmx` as starting point, adapt to targets |

---

## Optimization Stages

| Stage | What It Does | Variables |
|-------|-------------|-----------|
| **Baseline** | Export analyses without optimization | None |
| **Feasibility** | Hit EFL, F/#, BFL, image height targets | MCE gaps, BFL, first curvature per group |
| **Image Quality** | Minimize RMS spot, wavefront, chromatic error | All radii, selected thicknesses |
| **Field Balance** | Equalize performance across fields/configs | All radii, all thicknesses |
| **Manufacturability** | Enforce edge thickness, glass constraints | All radii, thicknesses, glass substitutions |

---

## Connection

The skill supports two connection modes:

```python
from zos_design_primitives import connect_zemax

# Interactive Extension (OpticStudio must be open — recommended)
app = connect_zemax(standalone=False)

# Standalone (creates new OpticStudio instance)
app = connect_zemax(standalone=True)

system = app.PrimarySystem
```

---

## Known Limitations

- **MCE operand API** — Python.NET 3.0 has limited enum-to-int conversion; MCE operand types must use `MultiConfigOperandType` enum values explicitly.
- **Chinese paths** — OpticStudio `SaveAs` requires absolute paths; relative paths may silently fail with non-ASCII directory names.
- **Optimization wizard** — properties use `OK()` (uppercase), `Ring`/`Arm`/`Data` (singular), `PupilIntegrationMethod` (full name) — not the intuitive names.
- **Merit function access** — use `system.MFE` directly, not `system.Tools.OpenMeritFunction()`.
- **Stop surface** — set via `system.LDE.StopSurface = N`, not `MakeSurfaceStop()`.

---

## Upgrading

```bash
# Remove old skill
rm -rf ~/.claude/skills/ai-zemax-optical-design

# Pull latest
cd ai-zemax-optical-design
git pull origin master
npm install
```

---

## License

MIT © [Jerry](https://github.com/Jerry-del975)
