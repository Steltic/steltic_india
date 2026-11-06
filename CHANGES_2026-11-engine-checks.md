# steltic-india — 2026-11 engine checks (combinations by sign, Table 2 web class with N, one IS 2062 band)

Branch `fix/2026-11-engine-checks`, started on main 41fb2f7 and merged with main e927f35 (PR #31, the MSME
angle-truss shed; merge 1414ba4, conflicts in `member_check_is800`, `peb_station_checks` and the static replay
resolved to keep both sides). An independent review of the PEB golds
(`briefs/PEB_REVIEW.md`, sections A, B, C and "Other findings") found three gaps in the HR engine's member and joint
checks that let auto-sized members at 0.99–1.00 pass when they are overstressed. The gaps are in the engine, so they
affect every HR job, not only the PEB ones. This branch closes them and two small items. Gold cfgs are not edited: the
job owners re-size their golds on this engine (the gold-impact table below says what moves).

## Why

| # | Gap on main | Effect the review found |
|---|---|---|
| A | The member checks saw a ranked subset of the combinations (top 3 by \|N\|, \|Mmaj\|, \|Mmin\|, \|V\|, 3 most compressive, the span-load ones). The ranking ignored the sign of the moment, which decides the compression flange and its LTB length. | IN_Ex2 canopy root checked for −235 kN·m hogging (1.000); the −285 kN·m hogging case 1.2DL+1.2LL+1.2WM0 was dropped: 1.211. |
| B | The IS 800 Table 2 web class was found with N = 0 (and N = 1 N for the axial terms). The "generally" web rows with r1, r2 were never used with the real force. | IN_Ex3 column about 1.07, IN_Ex2 wind column about 1.05, IN_Ex1 main column about 1.03 (reviewer's hand estimates). |
| C | Plate yield stresses outside the member material took a fixed 250 MPa (or 250 / 350 up to 20 mm in the PEB sizer). IS 2062:2025 gives 240 / 330 MPa above 16 mm. | IN_Ex3 knee stiffeners 1.000 → 1.024 (hand); the sizer wrote fy 250 into the cfgs the full runs judge. |

## What the engine does now

### A. Every combination, both signs (`design_pipeline.member_check_records`, `design_pipeline.py:741`)

- `member_checks_is800` and `peb_station_checks` hand EVERY combination of the element to
  `india_is800.member_check_is800`, in the order of the records (the combination order of the run; ties resolve the
  same way on every run — the old subset was a `set`, so its order changed with the hash seed).
- `_top_records` is kept as an alias for older callers and returns every combination.
- The member check already checks each sign of each combination with its own LTB length (`Mz_sag` with
  `LLT_sag_mm`: the flange held by the purlins / deck; `Mz_hog` with `LLT_hog_mm`: the flange held by the fly braces),
  the in-span extreme of a span load of either sign, the max compression, the max tension and every shear. With every
  combination kept there is no subset to prove complete.
- Audit of the sign-dependent restraints:
  - beams and rafters: `member_records` gives beam moments sagging-positive; PEB rafters take `LLT_sag` = purlin gap,
    `LLT_hog` = fly-brace gap (`peb_build.overrides`); canopy beams the same from `flange_braces[kind]`;
  - PEB columns take the larger of the girt and fly-brace gaps for both signs (`peb_build.overrides`, documented
    there); no gold declares a column `member_overrides` with different sagging / hogging lengths;
  - station checks keep the sign of each end moment, so each station takes its own sign's length.
- **Run-time cost** (measured; see the table in "Gold impact"): the per-combination check is arithmetic. Offline on
  the IN_Ex19 records (1,308 elements × 141 combinations) the member checks take 3.9 s with every combination against
  0.8 s with the subset; on IN_Ex2 (548 elements, stations not counted) 3.1 s against 0.4 s. Whole runs: see below.
  This is far under the 1.5× budget, so no subset is kept (and no subset test is needed).
- **Connections, splices and bases already see every combination and both signs** (checked):
  - column bases: `india_connection_design.base_load_cases` takes |Mmaj_i|, |Mmin_i| of every record (a declared base
    is symmetric: one `f_mm` / `n_tension` pattern);
  - column splices: `column_splice` takes |Mmaj|, |Mmin| of every record (symmetric splices);
  - PEB rafter splices and the apex: `peb_checks.splice_records` takes the largest \|M\| over every record and
    `reverse_demand` the largest of the opposite sign, checked against the bolts on that side (`end_plate_layout`);
  - PEB knees: `knee_records` takes \|M\| over every record and checks the end plate in both signs at the connection
    demand; Section 12 joints use 1.2 Mp (sign-free) against a symmetric connection (no non-PEB gold declares an
    end-plate beam-to-column joint);
  - Section 12 member forces (`section12_model_data`) were already every record.

### B. The Table 2 web class with each combination's axial force (`india_is800.py`)

IS 800:2007 Table 2 (corpus `documents/standards/IS_800_2007/tables/IS_800_2007_Table_2_recovered.md`, pdf p. 24),
web of an I, H or box section:

| Row | Plastic | Compact | Semi-compact |
|---|---|---|---|
| neutral axis at mid-depth | 84ε | 105ε | 126ε |
| generally, if r1 is negative | 84ε/(1 + r1) but ≤ 42ε | 105.0ε/(1 + r1) | 126.0ε/(1 + 2r2) but ≤ 42ε |
| generally, if r1 is positive | 84ε/(1 + r1) but ≤ 42ε | 105.0ε/(1 + 1.5r1) but ≤ 42ε | 126.0ε/(1 + 2r2) but ≤ 42ε |
| axial compression | Not applicable | Not applicable | 42ε |

Note 5: "r1 = Actual average axial stress (negative if tensile) / Design compressive stress of web alone;
r2 = Actual average axial stress (negative if tensile) / Design compressive stress of overall section".

- `section_class_table2` (`:2343`) with the combination's N (`_table2_web`, `:2295`; reading stated in the comment
  `WEB_ROWS_CITE`, `:2291`):
  - r1 = (N / (d tw)) / (fy / γm0) (2 d tw for a box), r2 = (N / A) / (fy / γm0), N compression positive — the
    engine's reading of "web alone" / "overall section", as before;
  - N = 0: the mid-depth row; N ≠ 0 with bending about either axis: the "generally" rows (r1 negative in
    tension); N > 0 with no bending at all (|M| ≤ 1 N·m about both axes at every check point: a compression member,
    where the class decides only the 7.3.2 area): the "axial compression" row. A first cut used the axial row whenever
    the major-axis moment was zero; with a minor-axis moment that classed the web of a corner column carrying a few
    MPa of uniform compression as slender and cut its minor-axis capacity from Zp to Ze (IN_Ex3 corner column
    0.911 → 1.179, IN_Ex2 0.990 → 1.085). Minor-axis bending with axial force is "in general", so the r1 / r2 rows
    apply there (the reading is stated in `WEB_ROWS_CITE`);
  - "but ≤ 42ε" stays a floor (the HR-INTEGRATE decision, tested in `test_india_snow_drift_and_table2.py`);
  - a row whose denominator is zero or negative (r1 ≤ −1, r2 ≤ −1/2: large tension) sets no limit for that class
    (engine reading: the formula's limit grows without bound as the denominator falls to zero; the web is not a
    compression element there). The record says which limit is not applicable (`no_limit`) and stays JSON-safe;
  - the classes are nested (`_web_class`, `:2315`): a plastic web also meets the compact and semi-compact limits, so
    under large tension, where the r1 limit can exceed the r2 limit, the stricter one governs;
  - the axial-compression row's "Not applicable" plastic / compact cells are read as no web requirement there: up to
    42ε the web does not limit the class (the flanges do), beyond it the section is slender;
  - the record carries `web_row`, `web_class`, `web_d_tw`, `web_limits`, `r1`, `r2`.
- `member_check_is800` (`:3211`) classifies every combination (`_classify`, `:3304`) and takes the capacity set
  that follows the class (`_caps`, `:3270`, cached per class and web limit):
  - plastic / compact: Zp, 9.3.1.1; semi-compact: βb = Ze/Zp, Ze for the high-shear and 9.3.1.3 rows;
  - slender (I-sections): the 3.7.2(d) effective section designed as semi-compact, as before, but the bending
    effective section now keeps the web's semi-compact limit FOR THAT COMBINATION, 126ε/(1 + 2r2) (floored at 42ε),
    instead of 126ε (`effective_section_3_7_2d(..., web_dt_limit=)`, `:2165`); the axial effective area keeps the
    42ε "axial compression" web (the engine's documented 3.7.2(d) basis, unchanged);
  - Nd, Pd (`compression_capacity(..., section_class=)`, `:2849`), Md, the LTB Md and the 9.3.1 form all follow the
    combination's class; CHS and angles keep their own "axial compression" rows for Pd (unchanged);
  - each per-combination record has `section_class` (the class designed for) and `table2` (the gross class, row,
    r1, r2); the member record has `section_class_by_combination` and reports the governing combination's capacities
    (`capacities.section_class`), with the N = 0 class beside them (`section_class_without_axial_force`);
  - the "LLT not declared" flag is written once, not once per combination.

### C. One IS 2062 (Part 1):2025 Table 3 band (`india_is800.fy_is2062`, `india_is800.py:2111`)

IS 2062 (Part 1):2025 Table 3 (corpus `documents/standards/IS_2062_Part_1_2025/tables/
IS_2062_Part_1_2025_p006_010_003_p009.md`), ReH min by thickness ≤ 16 / > 16 to 40 / > 40 to 100 / > 100 mm:
E 250 250 / 240 / 230 / 210, E 350 350 / 330 / 320 / 290 (the engine's `IS2062_TABLE3`, unchanged, matches).

- `india_is800.fy_is2062(grade, t_mm)` is the one band function. A gold cfg imports it:
  `from india_is800 import fy_is2062` (the PEB sandbox cfgs already do: `_fy2062 = I8.fy_is2062`).
- Everything that takes fy from a thickness now goes through it:
  - member sections: `material_for_section` (max(tf, tw)) — already;
  - connection plates (base, end, fin, cover, splice, shear key, gusset, CJP): `india_connections.plate_fy_is2062`
    caps a declared fy at the band — already;
  - **new** `india_connections.plate_fy_band(t, grade, fy_MPa=...)` (`india_connections.py:109`): a declared fy capped at the band, or the
    band value when no fy is declared (grade: its own, else `cfg['plate_grade']`, else E250 — the grade the old 250 MPa
    default stood for);
  - PEB knee panel (`peb_checks.knee_records`): the diagonal stiffeners, the flange stiffeners and the web doubler
    (`_stiffener_fy`, `peb_checks.py:55`); the doubler's share of the stiffener check (`:777`) is now at the doubler
    plate's own fy (it was at the column fy, while the panel-shear row already took 250 MPa for it); a job with E350
    doublers declares `knee_panel.doubler_grade` (or `doubler_fy_MPa`), documented in `contract/AGENT_START.md`;
  - PEB fly braces (`flange_brace_records`): the angle's own band;
  - `peb_checks._fy_plate`: no grade → the E250 band of the governing thickness (was 250);
  - crane bracket (`crane_bracket.bracket_record`): bracket plates, column stiffeners (band), column fy (its section's
    material, a declared value capped at it; was 350 by default);
  - PEB sizer (`peb_autosize.py`): `plate_fy` (`:236`, used by `apply_plate` / the end-plate, stiffener and key
    writers) is `fy_is2062` (was 250 / 350 up to 20 mm), `fy_of` (`:958`), the fabrication class screen (`:1309`) and
    the local knee rows (`knee_rows`, `:1574`, as `peb_checks`).
- Not thickness rules, left as they are: `design_pipeline` / `report` `Fy_default` (legacy unit defaults, not used
  by the India checks), `peb_autosize.py:884` (the cold-formed IS 811 purlin fy).

### Small items

- **Gable wind columns take Ka of their own tributary area** (review "Other findings" 5).
  - IS 875 (Part 3):2015 7.2.2.1 (corpus `IS_875_Part_3_2015.md`): "(a) Overall structure – For evaluating loads on
    frames the tributary area shall be taken as the centre to centre distances between frames multiplied by the
    individual panel dimension in the other direction"; "(b) Individual elements – For beam type elements, purlins,
    etc, the tributary area shall be taken as effective span multiplied by spacing."
  - A wind post (a wall column line whose top piece is pinned: a gable wind column, a pinned gravity column in a
    wall; `static_model._wind_post_columns`, `:1351`) is a beam-type element: A = the wall area each pattern loads
    it with, piece by piece (tributary width × piece length, summed over its span: span × spacing).
  - The member-wind pressures of a pattern carry pd at the frame's Ka (`wind_summary.Ka_basis = 'frame_tributary'`).
    The post's pressure is scaled by max(Kd Ka(A) Kc pz, 0.7 pz) / max(Kd Ka_frame Kc pz, 0.7 pz)
    (`static_model.wind_post_ka_factor`, `:1369`; applied in `member_wind_loads`, `:1282`), in both directions (a larger post area lowers it). Not applied, and the reason
    recorded, unless the wind summary states Kd, Kc, pz, Ka on the frame basis and its pd follows them.
  - The static replay of a custom build now keeps the column end releases (`rel`, `:133`) for this.
  - The package lists every post and pattern (`calc_package.json` `wind_post_Ka`, `design_pipeline.py:1464`).
- **Minor-axis base-plate outline gate** (review "Other findings" 4; `india_connections.py:1273`, `:1408`).
  `base_plate_design` fails a plate inside the
  column outline as a gate (`geometry_plate_outline`, the same text as the PEB branch) and no longer computes a
  compression-side moment from a negative projection; `base_plate_design_biaxial` keeps that row from the minor-axis
  call (`y:geometry_plate_outline`: B < 0.95 bf), where it used to drop every `geometry_*` row and could return a zero
  plate demand.

- **PEB sizer floor for shear keys** (found by the full suite): a strengthen-only run (`floor=True`) could propose a
  shorter shear key than the floor design's (a shorter cruciform key is stronger in bending, so it can be the
  lightest passing key); `peb_autosize.size_key(..., floor=)` (`:2025`) keeps every key dimension at or above the
  floor's (`test_peb_levers_2026_10.py::test_strengthen_only_keeps_the_gold_as_a_floor` met it once the member checks
  saw every combination).

## Tests

`tests/test_engine_checks_2026_11.py` (fixtures of real gold pieces in `tests/fixtures/engine_checks_2026_11/`,
captured from the gold runs on the origin/main engine):

| Fix | Unit tests | End-to-end on a real gold piece (origin/main → branch, same records) |
|---|---|---|
| A | `test_A_member_check_records_keep_every_combination_in_order`, `test_A_hogging_combination_ranked_out_by_sagging_cases_governs` (the old filter drops the hogging case; the check takes LLT_hog), `test_A_free_span_moment_of_either_sign_and_both_LTB_lengths` | `test_A_e2e_IN_Ex2_canopy_root_hogging_case_governs_at_1_21`: IN_Ex2 canopy root e483 0.9995 → **1.211** (1.2DL+1.2LL+1.2WM0+) |
| B | `test_B_table2_web_rows_with_the_actual_axial_force` (IN_Ex3 numbers: r1 0.220, compact limit 66.7), `test_B_table2_tension_rows_and_no_limit_beyond_the_denominator`, `test_B_axial_compression_row_without_bending`, `test_B_axial_row_only_without_any_bending_in_the_member_check`, `test_B_member_check_classifies_each_combination_and_capacity_follows` (Ze against Zp), `test_B_slender_web_effective_section_takes_the_web_limit_of_the_combination` | `test_B_e2e_gold_columns_with_the_actual_axial_force`: IN_Ex3 column WI475X220X16X5 0.994 → **1.075**; IN_Ex2 wind column WI400X220X20X4 0.993 → **1.050**; IN_Ex1 main column WI862X225X12X8 0.996 → **1.063** |
| C | `test_C_one_band_function_IS2062_2025_Table3`, `test_C_sizer_plate_fy_follows_the_band`, `test_C_plate_fy_band_declared_capped_and_undeclared_from_the_table`, `test_C_knee_stiffener_and_doubler_fy_from_the_band`, `test_C_crane_bracket_fy_from_the_band` | `test_C_e2e_IN_Ex3_knee_stiffeners_and_doubler_at_their_plate_fy`: IN_Ex3 knee 1.024 → **1.096** (the 6 mm doubler at 250 MPa); the cdfc027 declaration (18 mm at 250 MPa) capped at 240 |
| Ka | `test_wind_post_ka_factor_own_tributary_area` (IN_Ex3 numbers: 67.2 m², +1.3 %), `test_wind_post_columns_are_the_pinned_top_lines` | `test_wind_post_e2e_gable_wind_column_carries_its_own_Ka`: pipeline run of the test shed (`tests/_peb_fixture.py`), the gable wind column's span moment at its own Ka |
| Gate | `test_base_plate_minor_axis_outline_gate_fails_loudly` | (no gold has such a plate: review "Verified" 5) |

The fixtures are the member inputs and every combination record of the governing element (and the IN_Ex3 knee's
joint, its two elements' records and the cfg connection block), captured on 2026-11-06 at
`design_pipeline.member_checks_is800` / `peb_station_checks` / `peb_checks.knee_records` while the PEB sandbox golds
ran on origin/main 41fb2f7. Their `dc_origin_main` is the origin/main result on the same records.

Mutation check (`/home/claude/wt/ENG/tools/mutate.py`: each fix reverted in a scratch copy, its tests run):

| Mutation (reverted in a scratch copy) | Tests that fail |
|---|---|
| A: member checks back to the \|N\|/\|M\|/\|V\| top-3 subset | 2 (the synthetic hogging case, the IN_Ex2 canopy root) |
| B: Table 2 class back to N = 0 for every combination | 4 (classification per combination, the three gold columns) |
| B': effective section back to the 126ε web whatever N | 2 (the r2 web limit, the IN_Ex1 column) |
| C: sizer `plate_fy` back to the old 20 mm band | 1 |
| C': knee stiffener / doubler fy back to the declared value / 250, doubler at the column fy | 2 (unit, IN_Ex3 knee) |
| C'': crane bracket fy back to the 250 / 350 defaults | 1 |
| Ka: wind-post pressure not scaled | 1 (the pipeline run) |
| Gate: minor-axis outline row dropped again | 1 |

Full HR suite on the merged head 1414ba4 (under heavy): **1,281 passed, 5 skipped, 0 failed** (main e927f35:
1,258 / 5 as the lead reports; main 41fb2f7, run here before any change: 1,200 / 5). The 23 new tests are in
`test_engine_checks_2026_11.py`.

## Gold impact (A/B: main e927f35 against this branch at 1414ba4; every HR gold run once per engine)

**Setup.**
- Engines: main e927f35 (`/home/claude/wt/ENG/base`) and this branch at 1414ba4 (`/home/claude/wt/ENG/engrun`), each
  with the CFS repo symlinked.
- Harness: a copy of the gold harness with `W` / `RR` taken from the environment (`/home/claude/wt/ENG/gold/harness`).
- Jobs: copies of every job folder, run under heavy with `PYTHONHASHSEED=0`, one slot at a time:
  - `/home/claude/gold/jobs_hr`, all 20 jobs plus the units IN_Ex11/workshop, IN_Ex12/unitB_link,
    IN_Ex12/unitC_gym and IN_Ex19/stem;
  - the PEB sandbox golds `/home/claude/wt/PEB/gold/jobs_hr` IN_Ex1–Ex5 (snapshot 2026-11-06 10:35, unchanged since
    by cfg and secondary results);
  - IN_Ex21 `/home/claude/wt/MSME/gold/jobs_hr` (snapshot 13:12).
- Results: `/home/claude/wt/ENG/gold/results/{main,eng}/<set>/<job>.digest.json`, `compare_main_eng.json`.

A first A/B against 41fb2f7 is kept in `results/old_41fb2f7`. PR #31 changes the PEB results only in the Table 3 rows of
a few roof members (Ex1 / Ex3 / Ex5 CHS168.3X4.5, Ex2 CHS219.1X6.3 and WI300X250X18X8), never the elements of the
fixtures.

Fix of each change above 1.0:
- **A**: the governing combination was outside the old top-|N|/|M|/|V| subset.
- **B**: the combination's Table 2 class differs from the N = 0 class.
- **Ka**: a wind post in a member-wind combination; the factor shown is the largest in that pattern.
- **C**: the knee stiffener row with the doubler at its own fy.

| Set | Job | Status main → branch | Worst member main → branch (governing check) | Worst connection main → branch | Above 1.0 on the branch (main → branch; fix) |
|---|---|---|---|---|---|
| PEB sandbox | IN_Ex1 | COMPLETE → PARTIAL (6) | lateral_col-WI862X225X12X8 0.996 → 1.063 (9.3) | 0.991 → 1.062 peb-knee-WI975X225X12X8-WI975X250X14X6 | WI862X225X12X8 0.996 → 1.063 (B: semi-compact → slender); WI938X225X12X8 0.958 → 1.002 (B: semi-compact → slender); knee-WI975X225X12X8-WI975X250X14X6 0.991 → 1.062 (C: doubler fy) |
| PEB sandbox | IN_Ex2 | COMPLETE → PARTIAL (8) | roof-WI408X190X12X5 0.999 → 1.211 (9.3) | 0.994 → 1.076 peb-knee-WI725X230X22X14-WI575X260X22X16 | WI408X190X12X5 0.999 → 1.211 (A: hogging case outside the old subset); WI225X280X18X4 0.99 → 1.06 (Ka: wind post, pattern factor up to ×1.080); WI400X220X20X4 0.993 → 1.051 (B: compact → semi-compact; Ka: wind post, pattern factor up to ×1.080); knee-WI725X230X22X14-WI575X260X22X16 0.973 → 1.076 (C: doubler fy) |
| PEB sandbox | IN_Ex3 | PARTIAL (2) → PARTIAL (4) | lateral_col-WI475X220X16X5 0.994 → 1.075 (9.3) | 1.024 → 1.096 peb-knee-WI475X220X16X5-WI675X225X12X6 | WI475X220X16X5 0.994 → 1.075 (B: compact → semi-compact); knee-WI475X220X16X5-WI675X225X12X6 1.024 → 1.096 (C: doubler fy) |
| PEB sandbox | IN_Ex4 | COMPLETE → PARTIAL (4) | gravity_col-WI475X190X12X4 0.994 → gravity_col-WI200X220X16X4 1.032 (9.3) | 0.984 → 1.083 peb-knee-WI650X250X20X14-WI575X250X18X16 | WI200X220X16X4 0.97 → 1.032 (Ka: wind post, pattern factor up to ×1.063); knee-WI650X250X20X14-WI575X250X18X16 0.973 → 1.083 (C: doubler fy) |
| PEB sandbox | IN_Ex5 | PARTIAL (59) → PARTIAL (59) | lateral_col-WI862X225X12X8 1.132 → 1.214 (9.3) | 1.091 → 1.091 peb-splice-190702 | WI575X190X10X5 1.048 → 1.083 (B: semi-compact → slender); WI950X250X14X6 1.077 → 1.101 (B: semi-compact → slender); WI562X225X12X8 1.081 → 1.081; WI712X225X12X8 1.054 → 1.054; WI788X225X12X8 1.099 → 1.139 (B: semi-compact → slender); WI862X225X12X8 1.132 → 1.214 (B: semi-compact → slender); WI938X225X12X8 1.093 → 1.147 (B: semi-compact → slender); knee-WI975X225X12X8-WI975X250X14X6 0.991 → 1.062 (C: doubler fy); 18 rafter splices 1.090-1.091 (unchanged) |
| MSME sandbox | IN_Ex21 | COMPLETE → COMPLETE | truss_diagonal-ISA70X70X6 0.96 → 0.96 (Table 3) | 0.964 → 0.964 truss_vertical-ISA60X60X6 | none |
| published | IN_Ex1 | PARTIAL (2) → PARTIAL (2) | lateral_col-WI300X180X8X5 1.301 → 1.378 (9.3) | 0.969 → 0.969 roof-WI972X250X14X6 | WI300X180X8X5 1.301 → 1.378 (Ka: wind post, pattern factor up to ×1.060) |
| published | IN_Ex2 | COMPLETE → COMPLETE | roof-WI500X300X25X14 0.93 → roof-WI500X200X12X6 0.937 (9.3) | 0.974 → 0.974 lateral_col-WI700X300X22X14 | none |
| published | IN_Ex3 | PARTIAL (2) → PARTIAL (2) | gravity_col-WI300X200X10X6 1.19 → 1.276 (9.3) | 0.948 → 0.948 lateral_col-WI550X250X16X8 | WI300X200X10X6 1.19 → 1.276 (Ka: wind post, pattern factor up to ×1.072) |
| published | IN_Ex4 | PARTIAL (4) → PARTIAL (4) | gravity_col-WI350X250X12X6 1.207 → 1.283 (9.3) | 0.984 → 0.984 brace-WPB180X180X51.22 | WI350X250X12X6 1.207 → 1.283 (Ka: wind post, pattern factor up to ×1.063); WI450X200X10X6 1.091 → 1.072 (Ka: wind post, pattern factor up to ×1.063) |
| published | IN_Ex5 | PARTIAL (13) → PARTIAL (15) | lateral_col-WI300X180X8X5 1.301 → 1.378 (9.3) | 0.969 → 0.969 roof-WI972X250X14X6 | WI972X250X14X6 1.072 → 1.096 (B: semi-compact → slender); WI300X180X8X5 1.301 → 1.378 (Ka: wind post, pattern factor up to ×1.060); WI781X250X14X6 1.0 → 1.031 (B: semi-compact → slender); WI869X250X14X6 1.052 → 1.088 (B: semi-compact → slender); WI956X250X14X6 1.102 → 1.142 (B: semi-compact → slender) |
| published | IN_Ex6 | COMPLETE → COMPLETE | floor-NPB600X220X122.45 0.887 → 0.887 (9.3) | 0.919 → 0.919 floor-NPB600X220X122.45 | none |
| published | IN_Ex7 | COMPLETE → COMPLETE | lateral_col-WPB600X300X211.92 0.953 → lateral_col-NPB750X270X202.49 0.954 (9.3) | 0.838 → 0.838 lateral_col-NPB750X270X202.49 | none |
| published | IN_Ex8 | COMPLETE → COMPLETE | roof-WPB500X300X155.08 0.804 → 0.804 (9.3) | 0.893 → 0.893 roof-WPB500X300X155.08 | none |
| published | IN_Ex9 | PARTIAL (4) → PARTIAL (4) | gravity_col-WPB200X200X42.26 2.081 → 2.081 (9.3) | 0.897 → 0.897 lateral_col-BOX450X400X25 | WPB200X200X42.26 2.081 → 2.081; WPB200X200X61.3 1.12 → 1.12 |
| published | IN_Ex10 | COMPLETE → COMPLETE | roof-WPB450X300X139.76 0.92 → 0.92 (9.3) | 0.786 → 0.786 lateral_col-WPB320X300X126.66 | none |
| published | IN_Ex11 | COMPLETE → COMPLETE | roof-NPB450X190X67.16 0.947 → 0.947 (9.3) | 0.905 → 0.905 lateral_col-WPB240X240X60.32 | none |
| published | IN_Ex11/units/workshop | COMPLETE → COMPLETE | roof-NPB450X190X67.16 0.947 → 0.947 (9.3) | 0.943 → 0.943 lateral_col-WPB200X200X42.26 | none |
| published | IN_Ex12 | COMPLETE → COMPLETE | floor-NPB700X250X143.42 0.983 → 0.983 (9.3) | 0.979 → 0.979 gravity_col-WPB300X300X117.03 | none |
| published | IN_Ex12/unitB_link | COMPLETE → COMPLETE | floor-NPB700X250X143.42 0.983 → 0.983 (9.3) | 0.935 → 0.935 lateral_col-BOX450X450X25 | none |
| published | IN_Ex12/unitC_gym | COMPLETE → COMPLETE | roof-NPB700X250X143.42 0.96 → 0.96 (9.3) | 0.905 → 0.905 lateral_col-BOX500X450X25 | none |
| published | IN_Ex13 | COMPLETE → COMPLETE | floor-NPB450X190X67.16 0.97 → 0.97 (9.3) | 0.959 → 0.959 brace-WPB200X200X50.92 | none |
| published | IN_Ex14 | COMPLETE → COMPLETE | floor-NPB450X190X92.37 0.864 → 0.864 (9.3) | 0.947 → 0.947 brace-WPB300X300X100.85 | none |
| published | IN_Ex15 | COMPLETE → COMPLETE | floor-WPB260X260X114.4 0.999 → 0.999 (9.3) | 0.985 → 0.985 link-WPB450X300X171.12 | none |
| published | IN_Ex16 | COMPLETE → COMPLETE | roof-NPB500X200X90.69 0.774 → 0.774 (9.3) | 0.986 → 0.986 roof-WPB320X300X126.66 | none |
| published | IN_Ex17 | COMPLETE → COMPLETE | floor-NPB750X270X145.29 0.933 → 0.933 (9.3) | 0.952 → 0.952 lateral_col-BOX450X450X28 | none |
| published | IN_Ex18 | COMPLETE → COMPLETE | floor-NPB750X270X174.54 0.889 → 0.889 (9.3) | 0.93 → 0.93 roof-WPB320X300X126.66 | none |
| published | IN_Ex19 | COMPLETE → COMPLETE | floor-WPB400X300X155.26 0.972 → 0.972 (9.3) | 0.985 → 0.985 link-WPB400X300X155.26 | none |
| published | IN_Ex19/units/stem | COMPLETE → COMPLETE | floor-WPB340X300X134.16 0.946 → 0.946 (9.3) | 0.985 → 0.985 link-WPB400X300X155.26 | none |
| published | IN_Ex20 | COMPLETE → COMPLETE | floor-WPB550X300X199.44 0.967 → 0.967 (9.3) | 0.979 → 0.979 brace-WPB240X240X83.2 | none |

Reading the table:
- **Non-PEB published golds (IN_Ex6–Ex20 and units):** no status changes and no worst ratio changes. Two ratios move
  below 1.0, both A: IN_Ex7 lateral_col-NPB750X270X202.49 0.941 → 0.954 (a dropped crane combination) and published
  IN_Ex2 roof-WI500X200X12X6 0.776 → 0.937. The members of these golds are rolled or stocky; the gaps bite on welded
  thin webs, sign-reversing canopies and knee stiffeners.
- **The PEB sandbox golds** (the ones to be published) all go over 1.0.
  - IN_Ex1: B (main column 1.063, the WI938 station 1.002, as the review estimated ~1.00) and C (knee 1.062).
  - IN_Ex2: A (canopy root 1.211), B and Ka (wind column 1.051), Ka (corner column 1.060), C (knee 1.076).
  - IN_Ex3: B (column 1.075) and C (knee 1.096).
  - IN_Ex4: Ka (corner column 1.032) and C (knee 1.083). The review's wind column 0.994 → about 0.997 does not
    appear: its own area (larger than the frame's) lowers its Ka, 0.994 → 0.979.
  - IN_Ex5: already PARTIAL on main, it gets worse.
- **The published IN_Ex1–Ex5** are the October golds, already PARTIAL on main. They move the same way.
- **IN_Ex21** stays COMPLETE: the bottom chord 0.950 → 0.956 (Ka of the gable posts).

**Run-time cost of A** (seconds, harness elapsed; noise between runs is about ±10 %):

| Job | main e927f35 | fix A alone (`/home/claude/wt/ENG/timingA`) | branch |
|---|---|---|---|
| IN_Ex19 (1,308 elements × 141 combinations) | 92.9 | 94.6 (1.02×) | 94.8 (1.02×) |
| IN_Ex12 | 9.0 | 9.9 (1.10×) | 10.4 (1.16×) |
| IN_Ex2 PEB (stations, the longest run) | 256.4 | 256.3 (1.00×) | 250.5 (0.98×) |

Offline, the member-check stage alone costs 0.8 → 3.9 s on IN_Ex19 and 0.4 → 3.1 s on IN_Ex2 (station checks not
counted). Every combination is kept. This is far under the 1.5× budget, so no subset is used and no subset test is
needed.

## Gold cfg helpers that hard-code the IS 2062 band (for the job owners; cfgs not edited here)

`fy_is2062` is the function to switch to (`from india_is800 import fy_is2062`). Paths are the job folders under
`/home/claude/gold/jobs_hr` (published) unless marked; line numbers of 2026-11-06.

**Old band (250 / 350 MPa up to 20 mm; IS 2062:2025 gives 240 / 330 above 16 mm):**

| Job | cfg.py line | Helper |
|---|---|---|
| IN_Ex1 | 346, 348 | `bolted_end_plate` (E350 / E250 plate fy) |
| IN_Ex2 | 538, 540 | `bolted_end_plate` |
| IN_Ex3 | 424, 426 | `bolted_end_plate` |
| IN_Ex4 | 350, 352 | `bolted_end_plate` |
| IN_Ex5 | (runs IN_Ex1's cfg.py) | the IN_Ex1 helper |
| IN_Ex11 | 412 | column base plate `fy_plate_MPa` |
| IN_Ex11 units/workshop | 414 | column base plate `fy_plate_MPa` |
| IN_Ex21 (MSME sandbox, `/home/claude/wt/MSME/gold/jobs_hr`) | 592 | column base plate `240.0 if t > 20 else 250.0` |

**Declared literals above the band (the engine now caps them; before this branch the knee-panel stiffeners were not
capped):** IN_Ex2 :713 (diagonal stiffener 20 mm at 250), IN_Ex3 :568 (flange stiffener 20 mm at 250), IN_Ex4 :508
(diagonal stiffener 20 mm at 250).

**Hand-coded bands that are right today but are copies (switch to `fy_is2062`):**
- partial bands without the > 40 mm row (wrong above 40 mm): IN_Ex6 :195 (cover plate), IN_Ex8 :304 and :309
  (cover plate, E250 assumed for the member), IN_Ex14 :481 (splice flange), IN_Ex16 :576, :582, :707 (cover plate,
  splice), IN_Ex17 :540 (splice plate);
- full E250 bands: IN_Ex15 :284 (fin plate), IN_Ex16 :711, :713, IN_Ex18 :656, IN_Ex19 :562, :593 (fin plate, base
  plate), IN_Ex20 :665 (base plate); the same lines in IN_Ex19 units/stem (:562, :593);
- E350 without the <= 16 mm row (conservative): IN_Ex19 :613 and units/stem :613 (box plates `330 if t <= 40 else 320`);
- literal plate values inside the band: IN_Ex13 :216 (gusset 20 mm at 240).

**PEB sandbox (`/home/claude/wt/PEB/gold/jobs_hr`):** already on the engine function (`_fy2062 = I8.fy_is2062`:
IN_Ex1 :37, IN_Ex2 :47, IN_Ex3 :43, IN_Ex4 :40; IN_Ex5 runs IN_Ex1's cfg). Its remaining literals are inside the band
(fly-brace angles 250 MPa at <= 16 mm, gussets 250 / 240 MPa by thickness, the crane bracket 250 MPa at 16 mm).
The study cfgs that `peb_autosize.apply_plate` wrote before this branch (fy 250 for 16-20 mm E250 plates, e.g.
`/home/claude/gold_var/study/IN_Ex1_*/solar_ready/run`) are superseded by the sizer's new `plate_fy`.


## Open points for the lead

1. **3.7.2(d) effective area under combined loading.** When a web is slender only by the "generally" row (126ε /
   (1 + 2 r2)), the engine keeps its documented effective section: the axial area with the 42ε web, the bending
   modulus with the combination's semi-compact web limit. IN_Ex1's main column gives 1.063 that way. The review's
   "about 1.03" is one effective section per combination with the r2 web limit for both terms (3.7.2(d) read as
   "deduct the excess over the semi-compact limit of this loading"). Both are readings of 3.7.2(d); the engine's is the
   more conservative and was kept. A lead / owner ruling is needed to change it.
2. **Pd of a section that is slender only in pure compression.** The engine reads 7.3.2 ("gross area ... so long as
   the section is semi-compact or better") with the class of the combination. The BS 5950 / EC3 practice is different:
   the compression resistance uses the class under axial compression alone (the 42ε web). That reading would put every
   welded web above 42ε (most PEB columns and rafters) on the effective area in every check. It was not adopted.
3. **Section 12 class gates still classify at N = 0** (12.7.2.4 braces, 12.8.4.1 SCBF columns, the SMF column and
   beam classes, `india_is800_s12.py:296, 603, 609, 1105`). With the 12.2.3 axial force a column web can drop a class.
   This was left unchanged because it is outside these fixes.
4. **The Section 12 panel-zone doubler takes the column fy** (`panel_zone_check`). This is the same issue as the PEB
   knee doubler fixed here, but the Section 12 joint spec declares no doubler grade, so it was left unchanged.
5. **A member-wind artefact on main, found here, not fixed.** `static_model.member_wind_loads` loads the first exposed
   column of each strip at each height. When a wall column is split above the eave (the IN_Ex21 gable posts: a
   6.5 m piece and a 1.5 m piece), the upper piece is the only column at that height. For the across-ridge wind it is
   loaded with the long-wall pressure over half the building length (an 18 m strip). The upper pieces e355 / e357 /
   e359 / e361 carry Mmin_free 3.9 kN·m under WM0 on main. The PEB golds' wind columns are single elements, so they
   do not have it. The MSME owner should know.
6. **Merging with `fix/2026-10-third-peb-golds`** (trial merge, not committed): one conflict, in
   `india_connections.base_plate_design_biaxial`, where the PEB branch made the same minor-axis outline fix (keep
   either side). `peb_autosize.py` merges cleanly.
7. **Gold owners** re-size on this engine. The knee stiffener rows are where C bites hardest: the web doubler is now
   at its own (E250) fy. A job with E350 doublers declares `knee_panel.doubler_grade`.
