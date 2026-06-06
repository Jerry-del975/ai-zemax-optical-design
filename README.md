# AI Zemax Optical Design

Automated optical design skill for **Claude Code** — drives **Ansys Zemax OpticStudio 2024 R1** through ZOS-API to turn optical requirements into executable design loops.

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
- **Ansys Zemax OpticStudio 2024 R1** installed (default: `D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00`)
- **Python** with `pythonnet` installed for ZOS-API connectivity
- **Claude Code** (the skill deploys to `~/.claude/skills/`)

### Smoke Test

```bash
# Test ZOS-API connection to Zemax
python scripts/connection_smoke_test.py

# Or via PowerShell (no pythonnet needed)
powershell -ExecutionPolicy Bypass -File scripts/connection_smoke_test.ps1
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
├── SKILL.md                  # Skill definition (loaded by Claude Code)
├── agents/                   # Agent interface config
│   └── openai.yaml
├── scripts/                  # ZOS-API Python automation
│   ├── zos_design_primitives.py        # Core: connection, analysis, optimization, save
│   ├── automated_design_agent.py       # Controller for the full design loop
│   └── connection_smoke_test.py        # Quick ZOS-API health check
├── references/               # Domain knowledge for the skill
│   ├── requirements-schema.md          # Normalized input schema
│   ├── merit-function.md               # Staged merit-function rules
│   ├── result-parsing.md               # Analysis export & logging rules
│   └── zos-api-patterns.md             # OpticStudio 2024 R1 API reference
├── examples/                 # Sample input files
│   ├── minimal_imaging_requirements.json
│   └── telescope_12x60_requirements.json
├── tests/                    # Unit tests
│   └── test_zos_design_primitives.py
├── package.json
├── install.js                # Postinstall: deploys skill to ~/.claude/skills/
└── README.md
```

## Target Environment

- **OS**: Windows 10/11
- **Software**: Ansys Zemax OpticStudio 2024 R1
- **Python**: 3.10+ with `pythonnet`
- **Claude Code**: latest

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

## License

MIT
