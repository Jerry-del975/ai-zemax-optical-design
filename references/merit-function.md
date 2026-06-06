# Merit Function and Variable Strategy

Build merit functions in stages and save after each stage.

## Stage 1: Feasibility

Constrain EFL, BFL, F/# or NA, total track, image plane, thickness, air gaps, clear aperture, glass catalogs, stop, and pupil requirements.

Variables: focus/image distance, air spaces, and a small number of powered curvatures.

## Stage 2: Image Quality

Optimize RMS spot, wavefront, MTF, chromatic error, field curvature, and astigmatism.

Variables: more curvatures, selected thicknesses, and controlled glass substitutions.

## Stage 3: Field Balance

Balance weights across center, mid-field, edge-field, wavelengths, and configurations. Reject center-only improvements.

## Stage 4: Manufacturability

Constrain diameters, sag, slope, edge thickness, incidence angles, cemented surfaces, and glass cost/availability.

## Stage 5: Tolerance Readiness

Add compensators, sensitivity checks, and lightweight tolerancing when available.

Accept an iteration only if it improves target metrics without violating hard constraints.
