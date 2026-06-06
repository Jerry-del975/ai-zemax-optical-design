# Requirements Schema

Normalize user requirements into this shape before running the automated design loop.

```json
{
  "system_type": "imaging_lens",
  "mode": "new_design_or_existing_file",
  "input_lens": null,
  "wavelengths_um": [{"value": 0.486, "weight": 1}, {"value": 0.588, "weight": 1}, {"value": 0.656, "weight": 1}],
  "fields": [{"type": "angle_deg", "value": 0}, {"type": "angle_deg", "value": 10}],
  "aperture": {"type": "f_number", "value": 4.0},
  "targets": {
    "efl_mm": null,
    "bfl_mm": null,
    "total_track_mm": null,
    "mtf": [{"frequency_lp_per_mm": 40, "min_contrast": 0.3}],
    "rms_spot_um": null,
    "distortion_percent_max": null
  },
  "constraints": {
    "glass_catalogs": ["SCHOTT"],
    "max_elements": null,
    "min_center_thickness_mm": 0.8,
    "min_air_gap_mm": 0.1,
    "max_diameter_mm": null,
    "aspheres_allowed": false,
    "zoom_configurations": []
  },
  "automation": {
    "max_stages": 5,
    "max_optimization_seconds_per_stage": 120,
    "save_every_stage": true
  },
  "assumptions": []
}
```

Keep units explicit. For existing lenses, infer missing values from the loaded model before asking the user.
