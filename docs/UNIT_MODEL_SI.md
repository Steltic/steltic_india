# India HR unit model (SI wave 2)

**Date:** 2026-09-18 Asia/Bangkok (UTC+7)

## Native system: **N-mm-sec**

| Quantity | Engine unit | Typical display |
|----------|-------------|-----------------|
| Force | N | kN |
| Length | mm | m (plan/story); mm (member) |
| Moment | N·mm | kN·m |
| Stress | MPa (= N/mm²) | MPa |
| Pressure (gravity) | kN/m² | kN/m² |
| Mass (OpenSees) | tonne (= N·s²/mm) | t |
| g | 9810 mm/s² | |
| E_steel | 200000 MPa | |
| G_steel | E/2.6 ≈ 76923 MPa | |

## Boundaries

1. **Brief → engine:** `india_units.apply_si_geometry(cfg)` (alias `apply_metric_geometry`) converts m → mm when `units` is metric/SI/m/mm. Sets `cfg['units']='N-mm'` and `engine3d.activate_si_units()`.
2. **load_plan RAG:** provenance strings stay in the units the standard cites (usually SI). Do not rewrite RAG text.
3. **Sections:** IS 808 / IS 1161 prefer `A_si_mm2`, `Izz_si_mm4`, `Iyy_si_mm4`; otherwise inch×25.4^n.
4. **Legacy kip-in:** `units='kip-in'` or `force_kip_in=True` → `apply_metric_geometry_legacy_kip_in`.
5. **Reports / CSV (wave 2):** HTML and `member_schedule.csv` use SI labels (kN, mm, kN·m, MPa) via `india_units.display_scale` / `demand_field_names`. Engine numbers stay N / N·mm; display divides by 1000 / 1e6.

## Remaining kip islands

See `india_units.KIP_ISLANDS`. USA archetype CFGs and AISC shape CSV fallbacks remain inch; India briefs do not use them.
