# AI Zemax Optical Design

Automated optical design skill for **Claude Code** — drives **Ansys Zemax OpticStudio** (v20.3–v26+) through ZOS-API to turn optical requirements into executable design loops.

## What's New in v1.1.0

- **ZOSPy integration** — connection layer now uses [ZOSPy](https://github.com/MREYE-LUMC/ZOSPy) (v2.1.5+, MIT license) instead of manual pythonnet DLL loading. ZOSPy auto-discovers OpticStudio installations across versions.
- **Multi-version support** — v20.3 through v26+, no more hardcoded `D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00`.
- **Zero downstream breakage** — `connect_zemax()` signature unchanged. The returned ZOS-API application object is identical, so all analysis, optimization, and save code works as before.
- Migration from `pythonnet` raw DLL loading → ZOSPy connection layer.

## Installation

```bash
npm install -g github:Jerry-del975/ai-zemax-optical-design
```

Or install from npm (once published):

```bash
npm install -g ai-zemax-optical-design
```

The postinstall script automatically copies the skill into `~/.claude/skills/ai-zemax-optical-design/`. Restart Claude Code and the skill is ready to use.

## What It Does

This skill turns Claude Code into a Zemax automation agent. Instead of just giving design advice, it produces **executable ZOS-API Python scripts** that:

1. **Parse requirements** — normalize optical specs from JSON or an existing `.zmx` / `.zos` / `.zar` file
2. **Create or load lens models** — build sequential models from first-order requirements, or load existing designs
3. **Run baseline analyses** — spot diagrams, MTF, wavefront, ray fans, field curvature/distortion before optimization
4. **Stage optimization** — feasibility → image quality → field balance → manufacturability → tolerance readiness
5. **Compare iterations** — each candidate scored against baseline and targets, with hidden-failure detection
6. **Save versioned outputs** — lens files, analysis exports, metrics JSON, and design logs at every stage

## Quickstart

### Prerequisites

- **Ansys Zemax OpticStudio** v20.3 or later (ZOSPy handles multi-version discovery)
- **Python 3.10+** with `zospy` (`pip install zospy`)
- **Claude Code** (the skill deploys to `~/.claude/skills/`)

```bash
# One-time: install ZOSPy
pip install zospy
```

### Smoke Test

```bash
# Test ZOS-API connection to an open OpticStudio
python scripts/connection_smoke_test.py
```

### Using in Claude Code

Once installed, invoke the skill in Claude Code and provide requirements:

```
Use ai-zemax-optical-design to design a 50mm f/2.8 double-gauss lens
for 35mm format, diffraction-limited at f/5.6, using only catalog glasses.
```

Or pass a requirements file:

```
Design from examples/minimal_imaging_requirements.json
```

## Project Structure

```
├── SKILL.md                        # Skill definition (loaded by Claude Code)
├── agents/                         # Agent interface config
│   └── openai.yaml
├── scripts/                        # ZOS-API Python automation
│   ├── zos_design_primitives.py              # Core: ZOSPy connection, analysis, optimization, save
│   ├── automated_design_agent.py             # Controller for the full design loop
│   └── connection_smoke_test.py              # Quick ZOS-API health check
├── references/                     # Domain knowledge for the skill
│   ├── requirements-schema.md                # Normalized input schema
│   ├── merit-function.md                     # Staged merit-function rules
│   ├── result-parsing.md                     # Analysis export & logging rules
│   └── zos-api-patterns.md                   # OpticStudio ZOS-API reference (v20.3+)
├── examples/                       # Sample input files
│   ├── minimal_imaging_requirements.json
│   └── telescope_12x60_requirements.json
├── tests/                          # Unit tests
│   └── test_zos_design_primitives.py
├── package.json
├── install.js                      # Postinstall: deploys skill to ~/.claude/skills/
└── README.md
```

## Target Environment

| Component | Requirement |
|-----------|-------------|
| **OS** | Windows 10/11 |
| **OpticStudio** | v20.3+ (auto-detected by ZOSPy) |
| **Python** | 3.10+ with `zospy>=2.1` |
| **Claude Code** | latest |

## Connection

ZOSPy handles all .NET interop and version discovery — no paths, DLLs, or `pythonnet` import needed in user code. `connect_zemax()` returns a raw ZOS-API application object compatible with all existing analysis and optimization calls.

```python
from zos_design_primitives import connect_zemax

# Interactive Extension (OpticStudio must be open)
app = connect_zemax(standalone=False)

# Standalone (creates new instance)
app = connect_zemax(standalone=True)

system = app.PrimarySystem  # Same IOpticalSystem as before
```

### Known Limitation

The ZOS-API multi-configuration editor (MCE) has limited operand manipulation support through pythonnet 3.0. For zoom/multi-configuration designs, manual MCE setup in the Zemax GUI is recommended before running the automated optimization loop.

## Examples

### Minimal imaging lens

```json
{
  "efl": 50,
  "f_number": 2.8,
  "half_fov": 20,
  "wavelengths_nm": [486, 587, 656],
  "image_diagonal_mm": 43.2,
  "glass_catalog": "SCHOTT",
  "design_stages": ["feasibility", "image-quality", "manufacturability"]
}
```

See `examples/` for more.

## Upgrading from v1.0.0

1. Uninstall the old skill: `rm -rf ~/.claude/skills/ai-zemax-optical-design`
2. Install the new version: `npm install -g github:Jerry-del975/ai-zemax-optical-design`
3. Install ZOSPy: `pip install zospy`
4. Restart Claude Code

## License

MIT
