# India complete-gap wave1

Closes HR India blockers toward COMPLETE on **IN_Ex1 / IN_Ex2 / IN_Ex3** (base tip ~`484b5a5` / P2).

| Item | Fix |
|------|-----|
| Report Ch.3 wind narrative | `_wind_section` reads `load_plan.wind_summary` + W_X/W_Y (vector or scalar) |
| Column Pd χ buckling | `india_is800.design_compressive_strength` — IS 800 §7.1.2 / Table 7 |
| §12 SMF SCWB | `india_is800.scwb_ratio` — numerical when Mp/Zx available; found:false only if inputs missing |
| Panel-zone / doubler | `india_is800.panel_zone_check` |
| §12 / base-plate / weld D/Cs | stubs + `fill_connection_component_dc` / `base_plate_worksheet` — no invented capacities |
| k4 OCR miss (IN_Ex3) | `resolve_k4` — EOR-documented k4+cite when corpus digits found:false (CFS-style) |
| Building length (IN_Ex3) | `resolve_building_length_m` — prefer `cfg['building_length_m']`; else documented assumption |
| R≤3 consistency | Skip always-on CONFIRM reminder when `capacity_design.checks.wind_vs_seismic` is computed |
| H6 / H7 | composite stubs + E250B process note **kept** |

Tests: `tests/test_india_complete_gap_wave1.py`.
