# India complete-gap wave1

Closes HR India blockers toward COMPLETE on IN_Ex1 / IN_Ex2 (tip base ~`484b5a5` / P2).

| Item | Fix |
|------|-----|
| Report Ch.3 wind narrative | `_wind_section` reads `load_plan.wind_summary` + W_X/W_Y (no false “no wind parameters”) |
| Column Pd χ buckling | `india_is800.design_compressive_strength` — IS 800 §7.1.2 / Table 7 |
| §12 SMF SCWB | `india_is800.scwb_ratio` — numerical ΣMpc/ΣMpb when Mp/Zx available; found:false only if inputs missing |
| Panel-zone / doubler | `india_is800.panel_zone_check` — sizes/flags or lists required_inputs |
| §12 connection D/Cs | stubs + `fill_connection_component_dc` — D/C only when RAG capacity present |
| H6 / H7 | composite stubs + E250B process note **kept** |

Tests: `tests/test_india_complete_gap_wave1.py`.
