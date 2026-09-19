# India complete-gap wave2

Closes HR India COMPLETE blockers on **IN_Ex4** (dual hospital) plus fold-ins from
**IN_Ex1–Ex3** and **IN_Ex5**. Base tip ~`49b01c9`.

| Item | Fix |
|------|-----|
| Dual Table 9 R found:false | `india_seismic_gates.resolve_R` — R+R_source+R_cite; eor_documented / sbf_concentric_for_dual; COMPLETE refuses proxy |
| Ω0 | `resolve_Omega0` — found:false default; optional eor_documented; never invent ASCE Ω0 |
| k4 hospital (Ex4) | `resolve_k4` eor_documented when OCR digits found:false |
| §12 / brace / SMF / portal / mezz D/C | `is4000_bolt_shear_capacity_N`, `fillet_weld_capacity_is800_N`, `apply_rag_capacities_to_connection` |
| Ex2 panel-zone doubler | `panel_zone_doubler_detail` — thickness + grade/electrode from RAG |
| Ex2 SCWB scope | Representative joint documented; multi-joint optional |
| Ex3 base-plate / weld + ARPACK | RAG fill; eigen stderr suppressed (not a fake PASS) |
| Ex5 storage height | `resolve_storage_height_m` — cfg or documented assumption (no silent 2.5 m) |
| Ex5 mass irregularity | `mass_irregularity_screen_note` — Table 6(ii) screen + Zone note |
| H6 / H7 | stubs / process notes **kept** |

Tests: `tests/test_india_complete_gap_wave2.py`.
