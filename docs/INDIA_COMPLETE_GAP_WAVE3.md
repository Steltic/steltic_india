# India complete-gap wave3

Closes remaining COMPLETE blockers folded from **IN_Ex1–Ex3** and **IN_Ex5**
(IN_Ex4 COMPLETE on wave2). Tip ~`7ca9ca0`. USA steltic **not** modified. **No push.**

| Item | Fix |
|------|-----|
| Base-plate bending t | `base_plate_bending_check` + wired into `base_plate_worksheet` — IS 800 LSD cantilever / RAG capacity; found:false if miss (no invent t) |
| B5 SI false-positive | `preflight` B5 unit-aware: SI uses m (N×S/1000), threshold ~91 m; no mm→ft WARN |
| Whitmore / block shear | `gusset_whitmore_capacity_N`, `gusset_block_shear_capacity_N` — RAG or disclosed; found:false if miss |
| End-plate Rn | `end_plate_or_continuity_capacity_N` RAG passthrough (kept; exercised) |
| Column base/splice Pn | `column_base_or_splice_Pn_capacity_N` — axial RAG only; never beam bolt shear on P_N |
| PZ doubler-in-model | `panel_zone_apply_doubler_in_model` — re-check when t in cfg/model; else document pending |
| Multi-joint SCWB | `scwb_multi_joint` optional; representative joint remains OK |
| Ex5 storage_height_m | Brief field preferred in `resolve_storage_height_m` + Ex5 cfg |
| Ch.1 USA boilerplate | `_design_basis_codes` India SI → IS 875/1893/800 (no IBC/ASCE rows) |
| H6 / H7 | stubs / process notes **kept** |

Tests: `tests/test_india_complete_gap_wave3.py`.
