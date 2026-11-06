# steltic-india — 2026-11 engine checks (combinations by sign, Table 2 web class with N, one IS 2062 band)

Branch `fix/2026-11-engine-checks`, started on main 41fb2f7 and merged with main e927f35 (PR #31, the MSME
angle-truss shed; merge 1414ba4, conflicts in `member_check_is800`, `peb_station_checks` and the static replay
resolved to keep both sides). An independent review of the PEB golds
(`briefs/PEB_REVIEW.md`, sections A, B, C and "Other findings") found three gaps in the HR engine's member and joint
checks that let auto-sized members at 0.99–1.00 pass when they are overstressed. The gaps are in the engine, so they
affect every HR job, not only the PEB ones. This branch closes them and two small items. Gold cfgs are not edited: the
job owners re-size their golds on this engine (the gold-impact table below says what moves).

Two follow-ups are plain commits on top of the round-1 head 711cc38:
- **Follow-up 1:** the lead's first ruling, the Section 12 class gates with N, the panel-zone doubler fy and the
  member-wind artefact.
- **Follow-up 2:** the independent review (`briefs/ENG_REVIEW.md`), the lead's two rulings (Pd under axial
  compression alone; Steltic ruling D-T11 for the web under N + My) and review findings 4–13.

The code is final at 8b2ffbf, the commit the final gold A/B ran on. Later commits add tests and docs only. Nothing is
pushed.

## Why

| # | Gap on main | Effect the review found |
|---|---|---|
| A | The member checks saw a ranked subset of the combinations (top 3 by \|N\|, \|Mmaj\|, \|Mmin\|, \|V\|, 3 most compressive, the span-load ones). The ranking ignored the sign of the moment, which decides the compression flange and its LTB length. | IN_Ex2 canopy root checked for −235 kN·m hogging (1.000); the −285 kN·m hogging case 1.2DL+1.2LL+1.2WM0 was dropped: 1.211. |
| B | The IS 800 Table 2 web class was found with N = 0 (and N = 1 N for the axial terms). The "generally" web rows with r1, r2 were never used with the real force. | IN_Ex3 column about 1.07, IN_Ex2 wind column about 1.05, IN_Ex1 main column about 1.03 (reviewer's hand estimates). |
| C | Plate yield stresses outside the member material took a fixed 250 MPa (or 250 / 350 up to 20 mm in the PEB sizer). IS 2062:2025 gives 240 / 330 MPa above 16 mm. | IN_Ex3 knee stiffeners 1.000 → 1.024 (hand); the sizer wrote fy 250 into the cfgs the full runs judge. |

## What the engine does now

### A. Every combination, both signs (`design_pipeline.member_check_records`, `design_pipeline.py:752`)

- `member_checks_is800` (`:794`) and `peb_station_checks` (`:810`) hand EVERY combination of the element to
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
  - station checks keep the sign of each end moment, so each station takes its own sign's length;
  - after the review: a beam's in-span hogging extreme also reaches the check, with LLT_hog (finding 4,
    `Mmaj_hog_min`), and a cfg giving a column two different lengths is rejected (finding 12: for a column the sign
    is the end-moment sign, not a flange).
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

- `section_class_table2` (`india_is800.py:2443`) with the combination's N (`_table2_web`, `:2395`; the reading
  is stated in `WEB_ROWS_CITE`, `:2390`):
  - r1 = (N / (d tw)) / (fy / γm0) (2 d tw for a box), r2 = (N / A) / (fy / γm0), N compression positive — the
    engine's reading of "web alone" / "overall section", as before;
  - which row (**Steltic ruling D-T11**, lead ruling 2 of 2026-11-06, `D_T11_CITE` `:2211`, `d_t11_axial_row`
    `:2234`):
    - N = 0: the mid-depth row;
    - axial compression (P above the Table 3 compression tolerance `p_comp_tol`) and no meaningful major-axis
      moment (|Mz| ≤ 0.05 Mdz, Mdz the section's 8.2.1.2 strength without axial force, `mdz_without_axial_force`
      `:2222`): the "axial compression" row (42ε), whatever My;
    - major-axis bending: the "generally" rows with r1 / r2 (r1 negative in tension);
    - an earlier reading of this branch put N + My on the "generally" rows; the ruling replaced it (see
      "Follow-up 2");
  - "but ≤ 42ε" stays a floor (the HR-INTEGRATE decision, tested in `test_india_snow_drift_and_table2.py`);
  - a row whose denominator is zero or negative (r1 ≤ −1, r2 ≤ −1/2: large tension) sets no limit for that class
    (engine reading: the formula's limit grows without bound as the denominator falls to zero; the web is not a
    compression element there). The record says which limit is not applicable (`no_limit`) and stays JSON-safe;
  - the classes are nested (`_web_class`, `:2415`): a plastic web also meets the compact and semi-compact limits, so
    under large tension, where the r1 limit can exceed the r2 limit, the stricter one governs;
  - the axial-compression row's "Not applicable" plastic / compact cells are read as no web requirement there: up to
    42ε the web does not limit the class (the flanges do), beyond it the section is slender;
  - the record carries `web_row`, `web_class`, `web_d_tw`, `web_limits`, `r1`, `r2` (and `web_row_basis` when D-T11
    put a combination with small moments on the axial row).
- `member_check_is800` (`:3322`) classifies every combination (`_classify`, `:3434`) and takes the capacity set
  that follows the class (`_caps`, `:3396`, cached per class and web limit):
  - plastic / compact: Zp, 9.3.1.1; semi-compact: βb = Ze/Zp, Ze for the high-shear and 9.3.1.3 rows;
  - slender (I-sections): the 3.7.2(d) effective section designed as semi-compact, as before, but the bending
    effective section now keeps the web's semi-compact limit FOR THAT COMBINATION, 126ε/(1 + 2r2) (floored at 42ε),
    instead of 126ε (`effective_section_3_7_2d(..., web_dt_limit=)`, `:2245`);
  - Nd (9.3.1), Md, Mdy and the LTB Md follow the combination's class;
  - **Pd does not** (lead ruling 1, `PD_BASIS_3_7_2D` `:2199`): for I and box sections it is the design strength
    under axial compression alone, from the class on the "axial compression" row — one Pd per member and design
    length (`comp_ax`, `:3379`); a web above 42ε takes the 3.7.2(d) effective area with the 42ε web. CHS and angles
    keep their own axial rows; channels keep the combination's class;
  - each per-combination record has `section_class` (the class designed for) and `table2` (the gross class, row,
    r1, r2); the member record has `section_class_by_combination`, `Pd_basis`, `Pd_effective_section` (when Pd uses
    Ae) and `web_class_basis` (D-T11), and reports the governing combination's capacities (`capacities.section_class`)
    with the N = 0 class beside them (`section_class_without_axial_force`);
  - the "LLT not declared" flag is written once, not once per combination.

### C. One IS 2062 (Part 1):2025 Table 3 band (`india_is800.fy_is2062`, `india_is800.py:2141`)

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
    (`_stiffener_fy`, `peb_checks.py:55`); the doubler's share of the stiffener check (`:789`) is now at the doubler
    plate's own fy (it was at the column fy, while the panel-shear row already took 250 MPa for it); a job with E350
    doublers declares `knee_panel.doubler_grade` (or `doubler_fy_MPa`), documented in `contract/AGENT_START.md`;
  - PEB fly braces (`flange_brace_records`): the angle's own band;
  - `peb_checks._fy_plate`: no grade → the E250 band of the governing thickness (was 250);
  - crane bracket (`crane_bracket.bracket_record`): bracket plates, column stiffeners (band), column fy (its section's
    material, a declared value capped at it; was 350 by default);
  - PEB sizer (`peb_autosize.py`): `plate_fy` (`:236`, used by `apply_plate` / the end-plate, stiffener and key
    writers) is `fy_is2062` (was 250 / 350 up to 20 mm), `fy_of` (`:970`), the fabrication class screen (`:1322`) and
    the local knee rows (`knee_rows`, `:1643`, as `peb_checks`);
  - added after the review (findings 5 and 6): the knee and canopy-root column-flange web strip with the doubler at
    its own band (`peb_checks.column_web_strip_fy`, `:65`); tension rods at the band of their diameter
    (`peb_levers.rod_fy`, `:561`); the sizer's end-plate web fy from the member grade's band
    (`peb_autosize.member_web_fy`, `:246`, was 350); the D-T10 note's fallback (`design_pipeline.py:1143`).
- Not thickness rules, left as they are: `design_pipeline` / `report` `Fy_default` (legacy unit defaults, not used
  by the India checks), `peb_autosize.py:896` (the cold-formed IS 811 purlin fy).

### Small items

- **Gable wind columns take Ka of their own tributary area** (review "Other findings" 5).
  - IS 875 (Part 3):2015 7.2.2.1 (corpus `IS_875_Part_3_2015.md`): "(a) Overall structure – For evaluating loads on
    frames the tributary area shall be taken as the centre to centre distances between frames multiplied by the
    individual panel dimension in the other direction"; "(b) Individual elements – For beam type elements, purlins,
    etc, the tributary area shall be taken as effective span multiplied by spacing."
  - A wind post (a wall column line whose top piece is pinned: a gable wind column, a pinned gravity column in a
    wall; `static_model._wind_post_columns`, `:1478`) is a beam-type element: A = the wall area each pattern loads
    it with, piece by piece (tributary width × piece length, summed over its span: span × spacing).
  - The member-wind pressures of a pattern carry pd at the frame's Ka (`wind_summary.Ka_basis = 'frame_tributary'`).
    The post's pressure is scaled by max(Kd Ka(A) Kc pz, 0.7 pz) / max(Kd Ka_frame Kc pz, 0.7 pz)
    (`static_model.wind_post_ka_factor`, `:1496`; applied in `member_wind_loads`, `:1314`), in both directions (a larger post area lowers it). Not applied, and the reason
    recorded, unless the wind summary states Kd, Kc, pz, Ka on the frame basis and its pd follows them.
  - The static replay of a custom build now keeps the column end releases (`rel`, `:133`) for this.
  - The package lists every post and pattern (`calc_package.json` `wind_post_Ka`, `design_pipeline.py:1475`; when no post is found the package says why, `wind_post_Ka_note`, finding 9).
- **Minor-axis base-plate outline gate** (review "Other findings" 4; `india_connections.py:1273`, `:1408`).
  `base_plate_design` fails a plate inside the
  column outline as a gate (`geometry_plate_outline`, the same text as the PEB branch) and no longer computes a
  compression-side moment from a negative projection; `base_plate_design_biaxial` keeps that row from the minor-axis
  call (`y:geometry_plate_outline`: B < 0.95 bf), where it used to drop every `geometry_*` row and could return a zero
  plate demand.

- **PEB sizer floor for shear keys** (found by the full suite): a strengthen-only run (`floor=True`) could propose a
  shorter shear key than the floor design's (a shorter cruciform key is stronger in bending, so it can be the
  lightest passing key); `peb_autosize.size_key(..., floor=)` (`:2095`) keeps every key dimension at or above the
  floor's (`test_peb_levers_2026_10.py::test_strengthen_only_keeps_the_gold_as_a_floor` met it once the member checks
  saw every combination).

## Follow-up 1 (2026-11-06): the lead's first ruling and the three flagged items

Plain commits on top of 711cc38: 90d0a56, 6183546, 191e379, c23c056, 7548324, 1ddb6d1. The Pd text of 90d0a56 /
7548324 is superseded by lead ruling 1 (Follow-up 2); items 1–3 stand, with the D-T11 web row in item 1.

### R. Slender-section Pd (first ruling; superseded by ruling 1 in Follow-up 2)

The first ruling kept the engine's reading for IN_Ex1 (1.063 against the review's about 1.03): the effective area of a
slender section takes the 42ε "axial compression" web; the "generally" rows decide the class and Md. 90d0a56 stated
it in the record. 7548324 then added "a section semi-compact by the generally rows keeps the gross area for Pd"; the
review (finding 1) showed that this gives one member two values of Pd, and ruling 1 replaced it. Corpus
(`IS_800_2007.md`), quoted in the record:
- 9.3.2.2: "Pdy, Pdz = design strength under axial compression as governed by buckling about minor (y) and major (z)
  axis";
- 7.1.2: Pd = Ae fcd, "Ae = effective sectional area as defined in 7.3.2";
- 7.3.2: "Except as modified in 3.7.2 (Class 4), the gross sectional area shall be taken as the effective sectional
  area ... so long as the section is semi-compact or better";
- 3.7.2(d): "by deducting width of the compression plate element in excess of the semi-compact section limit".
- The rulings' "7.3.2.1" is clause 7.3.2 in the corpus text, which has no 7.3.2.1; 7.3.2 is cited.

### 1. Section 12 class gates with the axial force of each combination (`india_is800_s12.py`)

- `table2_class_by_combination` (`:240`) classifies a member with the axial force of each of its force records
  through `india_is800.section_class_table2`, as the member check does (fix B), with the web row of D-T11:
  - the "generally" web rows with r1 / r2 with major-axis bending;
  - the "axial compression" row for a record with compression and |Mz| ≤ 0.05 Mdz, whatever My (D-T11; it was "no
    bending at all" in 6183546);
  - the mid-depth row with no axial force.
- The least favourable class governs (the section must meet the class under every combination it carries). The
  governing record is the one with that class and the largest compression.
- The gates that use it:
  - 12.7.2.4 OCBF brace "not slender" and 12.8.2.5 SCBF brace "plastic" (`:367`, `:371`): the brace's Table 4 records
    (the 12.2.3 rows are column / connection demands, H07);
  - 12.8.4.1 SCBF column "plastic" and 12.11.3.1 SMF column "plastic or compact" (`:674`, `:680`): every record of the
    column, the 12.2.3 rows included (the column is designed for them, 12.5.1.1 / 12.11.3.4);
  - 12.11.3.1 SMF beam (`:1177`): every record of the beam.
- Each check row reports `governing_combo`, `governing_family`, `governing_P_N`, `web_row`, `r1`, `r2`, `web_limits`,
  `classes_by_combination`, `class_without_axial_force` and `web_class_basis` (D-T11).
- CHS, angles and channels keep their Table 2 rows, which do not take the axial force; the row says so.
- IS 18168:2023 Table 2 (ii) columns (5.3 and 12.3.4.1): Ca = Pu / (Py / γm0) was already taken from the largest
  |P| ("Pu = maximum factored axial load demand", IS 18168 notation). `_ca_governing` (`:286`) now names that record
  as the governing combination. Ca itself is unchanged.

### 2. Section 12 panel-zone doubler at its own fy (`india_is800.panel_zone_check`, `:327`)

- `fy_MPa` is the column web's. The doubler plate is checked at its own fy, never the column's:
  - its shear-buckling stress τb and its share of Vd;
  - the doubler thickness required to close the shear (three passes through the band).
- Where the doubler fy comes from (`_dbl_fy`, `:381`; `india_connections.plate_fy_band`):
  - the IS 2062:2025 Table 3 band of `doubler_grade` for the doubler's thickness;
  - a declared `doubler_fy_MPa` capped at that band;
  - neither declared: E250, and the record says so (`doubler_fy.grade_basis`: "doubler grade not declared ... E250
    assumed ... the column's fy is not used").
- The joint takes `doubler_grade` / `doubler_fy_MPa` from the beam_column connection spec, as it takes
  `doubler_t_mm` (`india_connection_design.py:145`, `design_pipeline.py:1633`, the joint call
  `india_is800_s12.py:1230`). The contract documents the keys (`contract/AGENT_START.md:508`), like
  `knee_panel.doubler_grade`.
- The PEB sizer's panel-zone screen (`peb_autosize.py:1222`) and `panel_zone_apply_doubler_in_model` pass the keys
  through; the latter reads the cfg keys `panel_zone_doubler_grade` / `panel_zone_doubler_fy_MPa`, now named in
  `contract/README_AGENT.md:103` beside `panel_zone_doubler_t_mm` (review finding 13: the contract lint).

### 3. Member wind: no wall pressure under the roof; a piece above an eave split keeps its own wall's width (`static_model.py`)

The artefact (found on IN_Ex21): `member_wind_loads` loaded the first column met from upwind at each height. A wall
column split above the eave (the IN_Ex21 gable posts: a 6.5 m piece and a 1.5 m piece through the end truss) left
the upper piece as the only column at its height.
- Under the across-ridge wind, the upper piece took the long-wall pressure over half the building length: an 18 m
  strip, up to 9.3 N/mm on a 1.5 m piece under WM0−.
- Under the along-ridge wind, it took only half its own width (3 m): the corner columns end at the eave.

The scan is now `wall_wind_pieces` (`:1399`, called at `:1292`; basis `WALL_SCAN_BASIS`, `:1350`):
- **Envelope:** the strip's sloping roof members inside the plan extent of its columns count as the envelope:
  - which members: rafters, truss chords and other sloping beams, and pin-ended truss members (`_envelope_members`,
    `:1361`); wall and frame bracing is not envelope;
  - a column piece that such a member crosses upwind of, at the piece's mid-height, is under the roof and takes no
    wall pressure;
  - a canopy outside the columns' plan extent shelters nothing.
- **Width:** the width of a face piece is half the distance to the neighbouring strips at its height, as before. It
  also reaches the neighbouring column line of its own wall where a roof member of that wall rises over that line:
  the gable triangle above the eave, so the post keeps its own tributary width.
- **Unchanged:** a main wall above a lean-to roof is still loaded, and a setback tower edge is not widened (no roof
  member in its wall plane).
- **Record:** the package lists the sheltered and widened pieces per pattern (`calc_package.json`
  `member_wind_wall_scan`, `design_pipeline.py:1484`).
- **Not modelled, as before:** side-wall pressures (Table 5 C / D at θ = 0, A / B at θ = 90) are applied to no column
  (open point 1 below).
- **No member lost wind load it should carry:** see "Member-wind totals" below (every gold, every pattern, main
  against the branch against a hand total).

## Follow-up 2 (2026-11-06): the independent review and the lead's two rulings

The review (`/home/claude/briefs/ENG_REVIEW.md`, up to 1ddb6d1) gave "merge after fixes". The lead's rulings and
the fixes are plain commits on top: 9be24fe (both rulings), 8b2ffbf (findings 4–13 and the sizer base screen), and
the docs after them.

### Ruling 1: Pd is the design strength under axial compression alone (review findings 1 and 8)

- For I and box sections Pd is always taken from the class under axial compression alone. A web (or box plate)
  with d/t > 42ε is slender on that row, and Pd = Ae fcd with the 3.7.2(d) effective area and the 42ε web.
- That gives one Pd per member and design length, whatever the combination's moments (`member_check_is800` `comp_ax`,
  `india_is800.py:3379`).
- It removes the jump the review found. On WI475X220X16X5 at 155 kN, P/Pdz was 0.0750 with no moment and 0.0643 with
  a 2 N·m moment. Now both take the 42ε Ae.
- Nd (9.3.1), Md, Mdy and the LTB stay on the combination's class.
- `compression_capacity`'s own classification (`:2949`) puts an I / box web on the axial row, so the same default
  reaches the other axial-alone checks:
  - the pin-ended truss route `axial_member_check_is800`;
  - the Section 12 brace compression, gusset, 12.5.1.1, IS 18168 SCWB Pd and 12.3.2.2 rows;
  - the PEB buckling section (`peb_buckling_section`, `:3214`).
- A slender welded box gets its 3.7.2(d) effective area (`effective_area_box_axial`, `:2323`: each plate kept to
  42ε t) instead of "not coded". No gold has one.
- `PD_BASIS_3_7_2D` (`:2199`) says exactly this. The record carries `Pd_basis` and `Pd_effective_section`; 7548324's
  "keeps the gross area" wording is gone.
- Fixtures, on the main analyses:

  | Fixture | Before ruling 1 | Ruling 1 | The review's "as worded" figure |
  |---|---|---|---|
  | IN_Ex3 column WI475X220X16X5 | 1.0748 | **1.0832** | 1.0832 |
  | IN_Ex2 wind column WI400X220X20X4 | 1.0505 | **1.0523** | 1.0523 |
  | IN_Ex1 main column WI862X225X12X8 | 1.0635 | 1.0635 | 1.0635 |
  | IN_Ex2 canopy root e483 | 1.2109 | 1.2109 | 1.2109 |

### Ruling 2: Steltic ruling D-T11, the web class under compression with minor-axis bending only (finding 2)

- The rule: with axial compression and no meaningful major-axis moment, the web is classified on Table 2's "axial
  compression" row (42ε), whatever My. The "generally" rows with r1 / r2 apply only with major-axis bending.
- "Axial compression" means P above the Table 3 compression tolerance `p_comp_tol` (max(1 N, 10⁻³ A fy), the
  engine's existing basis).
- "No meaningful major-axis moment" means |Mz| ≤ 0.05 Mdz. This is the H34 negligibility basis. Mdz is the
  section's 8.2.1.2 design strength about z without axial force (`mdz_without_axial_force`, `:2222`): Zp fy / γm0
  (≤ 1.2 Ze fy / γm0) if plastic or compact, else the gross Ze fy / γm0. That is the larger value, so the threshold
  errs on the strict side, and 1 N·m of noise no longer flips the class.
- Basis, stated in the record as `D_T11_CITE` (`:2211`), `web_class_basis` and per combination `web_row_basis`:
  - IS 800 3.7.1 classifies "each element of a cross-section subjected to compression due to axial force, moment or
    shear" by the stress it carries;
  - the web sits on the neutral axis of My, so under N + My it carries the uniform N / A;
  - Table 2 has no biaxial row. This follows the element's stress state and matches common practice.
- Where the rule applies:
  - the member check (`d_t11_axial_row`, `:2234`, called in `member_check_is800`);
  - the Section 12 gates (`table2_class_by_combination`, `india_is800_s12.py:240`);
  - the PEB sizer's 12.11.3.1 screen, which now classifies with each record's N (`LocalModel._class_with_N`,
    `peb_autosize.py:1361`; finding 7).
- It replaces this branch's first reading. Its first cut of the strict reading measured IN_Ex3 corner column
  0.911 → 1.179 and IN_Ex2 0.990 → 1.085; the gold A/B below has the final numbers.

### The review findings, one by one

| # | Finding | What was done | Where | Test |
|---|---|---|---|---|
| 1 | Pd from the combination's class (two Pd per member) | Ruling 1: Pd from the class under axial compression alone, one per member | `india_is800.py:2199`, `:3379`, `:2949` | `test_R_slender_pd_…_IN_Ex1`, `test_R_one_pd_per_member_…`; mutation R1 |
| 2 | N + My on the "generally" rows | Ruling 2 / D-T11 | `india_is800.py:2211`, `:2234`; `india_is800_s12.py:240` | `test_DT11_web_row_by_the_major_axis_moment` (3 cases), `test_DT11_tiny_compression_…`, round-1 `test_B_axial_row_with_no_meaningful_major_axis_moment_…`; mutations D-T11, D-T11' |
| 3 | Follow-up unfinished | CHANGES and ENG_RESULT4 committed with the final A/B at the head; the member-wind proof below | this file | — |
| 4 | A beam's in-span hogging peak never reached the check | `member_records` keeps `Mmaj_hog_min` = min(sag) (`REC_FIELDS`, `static_model.py:1673`; `beam_hog_minima` `:1804`); the check takes `Mz_mid_hog_Nmm` (`:1851`; `india_is800.py:3496`) with LLT_hog; station checks clear it; envelope layout bumped | `static_model.py`, `india_is800.py`, `design_pipeline.py:810` | `test_F4_beam_in_span_hogging_reaches_the_member_check`; mutation F4 |
| 5 | Knee / canopy-root web strip with the doubler at the column fy | Thickness-weighted fy, the doubler at its own band (`peb_checks.column_web_strip_fy` `:65`, knee `:839`; the sizer the same) | `peb_checks.py`, `peb_autosize.py` | `test_F5_web_strip_…`; mutation F5 |
| 6 | Hard-coded IS 2062 values | Rods at the band of their diameter (`peb_levers.rod_fy` `:561`; the existing rod test's expected Td updated: 240 MPa at 20 mm); the sizer's end-plate web fy from the member grade's band (`peb_autosize.member_web_fy` `:246`); the D-T10 note's fallback through `fy_is2062` (`design_pipeline.py:1143`) | as listed | `test_F6_rod_and_sizer_web_fy_from_the_band` |
| 7 | Sizer 12.11.3.1 screen at N = 0 | Classified with each record's N and D-T11 | `peb_autosize.py:1361` | `test_DT11_section12_gate_and_sizer_screen_…` |
| 8 | Other Pd paths on the mid-depth row | Ruling 1's default in `compression_capacity` | `india_is800.py:2949` | `test_R_axial_only_checks_take_the_axial_compression_row_too`; mutation R1b |
| 9 | Wind posts only in custom builds, silently | The package says why none was found (`wind_post_Ka_note`: parametric storey forces, or no wall column with a pinned top) | `static_model.py:1285`, `design_pipeline.py:1479` | gold packages (A/B) |
| 10 | Doc figures / Ka tag / stale comment | Fixed: the "only two ratios move" sentence, the IN_Ex2 wind column tag (B only: its own Ka factor is 1.000), the `member_check_is800` comment | this file, ENG_RESULT4, `india_is800.py` | — |
| 11 | IN_Ex21 under c23c056 | Explained below (gold impact) | — | IN_Ex21 e2e tests |
| 12 | Column LLT_sag / LLT_hog | A cfg giving a column different lengths is rejected with a plain message | `design_pipeline.member_override` `:634` | `test_F12_…`; mutation F12 |
| 13 | Suite red on the contract lint | `panel_zone_doubler_grade` / `_fy_MPa` named in the contract | `contract/README_AGENT.md:103` | `test_fix_D05_contract_lint.py` |
| — | (found by the suite after the rulings) The sizer proposed a column base section that did not fit the declared base plate, so the full run failed the plate-outline gate | `LocalModel._base_outline_fails` screens such sections (L ≥ 0.95 d, B ≥ 0.95 bf) | `peb_autosize.py:1561` | `test_peb_levers_2026_10.py::test_autosize_passes_and_is_deterministic` |

## Tests

`tests/test_engine_checks_2026_11.py` (fixtures of real gold pieces in `tests/fixtures/engine_checks_2026_11/`,
captured from the gold runs on the origin/main engine):

| Fix | Unit tests | End-to-end on a real gold piece (origin/main → branch, same records) |
|---|---|---|
| A | `test_A_member_check_records_keep_every_combination_in_order`, `test_A_hogging_combination_ranked_out_by_sagging_cases_governs` (the old filter drops the hogging case; the check takes LLT_hog), `test_A_free_span_moment_of_either_sign_and_both_LTB_lengths` | `test_A_e2e_IN_Ex2_canopy_root_hogging_case_governs_at_1_21`: IN_Ex2 canopy root e483 0.9995 → **1.211** (1.2DL+1.2LL+1.2WM0+) |
| B | `test_B_table2_web_rows_with_the_actual_axial_force` (IN_Ex3 numbers: r1 0.220, compact limit 66.7), `test_B_table2_tension_rows_and_no_limit_beyond_the_denominator`, `test_B_axial_compression_row_without_bending`, `test_B_axial_row_with_no_meaningful_major_axis_moment_in_the_member_check` (rewritten to D-T11: N + My on the axial row), `test_B_member_check_classifies_each_combination_and_capacity_follows` (Ze against Zp), `test_B_slender_web_effective_section_takes_the_web_limit_of_the_combination` | `test_B_e2e_gold_columns_with_the_actual_axial_force`: IN_Ex3 column WI475X220X16X5 0.994 → **1.083** (1.075 before ruling 1); IN_Ex2 wind column WI400X220X20X4 0.993 → **1.052** (1.050); IN_Ex1 main column WI862X225X12X8 0.996 → **1.063** |
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

Rerun at the head 8b2ffbf (`logs/mutation_round1_head.txt`): the same counts (A 2, B 4, B' 2, C 1, C' 2, C'' 1, Ka 1,
gate 1).

`tests/test_engine_checks_2026_11_followup.py` (the follow-ups; 28 tests):

| Item | Unit tests | End-to-end on a real gold piece |
|---|---|---|
| Ruling 1 (Pd) | `test_R_one_pd_per_member_from_the_class_under_axial_compression_alone` (no moment / 2 N·m / bending: one Pd = the 42ε Ae value), `test_R_axial_only_checks_take_the_axial_compression_row_too` (the truss / Section 12 default; the box effective area) | `test_R_slender_pd_takes_the_axial_compression_web_limit_IN_Ex1`: IN_Ex1 column 1.0635, Pd and Nd on the same 42ε Ae, the basis text |
| D-T11 | `test_DT11_web_row_by_the_major_axis_moment` (N + My; N + My + Mz = 0.04 Mdz: axial row; N + Mz = 0.06 Mdz: generally rows), `test_DT11_tiny_compression_is_not_axial_compression`, `test_DT11_section12_gate_and_sizer_screen_use_the_same_rule` | the gold A/B (IN_Ex3 / IN_Ex2 corner columns) |
| 1 (Section 12 classes) | `test_1_class_by_combination_takes_each_axial_force`, `test_1_smf_and_scbf_column_gates_with_the_axial_force`, `test_1_brace_gates_use_the_table4_records_and_the_axial_compression_row`, `test_1_is18168_column_ca_reports_the_governing_combination` | the gold A/B (no Section 12 class gate moves: no record carries enough axial force to drop a gold's class) |
| 2 (panel-zone doubler) | `test_2_panel_zone_doubler_at_its_own_fy_never_the_columns`, `test_2_doubler_required_at_the_doubler_fy`, `test_2_smf_joint_passes_the_declared_doubler_grade` | the gold A/B (IN_Ex12, IN_Ex18, PEB IN_Ex2 / Ex4 panel zones) |
| 3 (member wind) | `test_3_piece_under_the_roof_is_not_on_a_wall`, `test_3_own_wall_width_of_the_piece_above_the_eave_split`, `test_3_lean_to_main_wall_and_setback_tower_keep_their_scan` | `test_3_e2e_IN_Ex21_gable_posts_above_the_eave_under_the_across_ridge_wind` (4 cases) and `…_keep_their_own_width_under_the_along_ridge_wind` (2): the IN_Ex21 static-model geometry (`IN_Ex21_wall_wind_geometry.json`), origin/main's 18 m strip recorded |
| Findings 4, 5, 6, 12 | `test_F4_…`, `test_F5_…`, `test_F6_…`, `test_F12_…` | — |

Mutation check of the follow-ups (`/home/claude/wt/ENG/tools/mutate2.py`, log `logs/mutation2.txt`, at 8b2ffbf):

| Mutation (reverted in a scratch copy) | Tests that fail |
|---|---|
| R1: Pd back to the combination's class | 1 |
| R1b: `compression_capacity`'s own classification back to the mid-depth row | 1 |
| D-T11: the web row back to "no moment about either axis" | 3 |
| D-T11': the Section 12 gate back to "no moment about either axis" | 1 |
| 1: Section 12 class gates back to N = 0 | 3 |
| 2: panel-zone doubler back to the column's fy | 2 |
| 3a: member wind without the roof envelope | 5 |
| 3b: member wind without the own-wall width | 3 |
| F4: the beam's in-span hogging peak dropped | 1 |
| F5: the web strip back to the column fy | 1 |
| F12: different column LLT_sag / LLT_hog accepted | 1 |

Full HR suite, under heavy:
- the merged head 1414ba4: 1,281 passed, 5 skipped, 0 failed (main e927f35: 1,258 / 5 as the lead reports; main
  41fb2f7, run here before any change: 1,200 / 5);
- 1ddb6d1 (the reviewer's run): 1 failed, the contract lint (finding 13);
- 8b2ffbf: 1,306 passed, 3 failed, 5 skipped (`logs/suite_eng_review.txt`). The three failures were record-layout
  assertions that pinned 17 fields (finding 4 adds `Mmaj_hog_min`); eccfc95 extends them;
- **the final code head eccfc95: 1,312 passed, 5 skipped, 0 failed, 1 warning (a third-party starlette/httpx deprecation), 445.6 s under heavy** (`logs/suite_eng_final2.txt`).

Existing tests changed, each because a review finding changes the value it pins:
- `test_peb_levers_2026_10.py::test_rods_refused_outside_zone_II_ocbf`: rod Td at 240 MPa (finding 6);
- `test_span_moment_fix.py::test_record_layout_and_combo_forces` and the two `test_third_wave_peb.py` layout tests:
  REC_FIELDS[13:17] plus `Mmaj_hog_min` (finding 4);
- this branch's own round-1 `test_B_axial_row_only_without_any_bending_in_the_member_check`: rewritten to D-T11
  (ruling 2).

## Gold impact (final A/B: main e927f35 against the head 8b2ffbf; every HR gold run once per engine)

**Setup.**
- Engines:
  - main e927f35 (a worktree at `/home/claude/wt/ENG/base`, removed after the A/B; the digests stay in `results/main`);
  - the branch at three points, to tag each move with its fix: 1414ba4 (round 1, `results/eng`), c23c056
    (follow-up 1, `results/eng3`) and 8b2ffbf (the head's code, `results/eng4`; the later commits change only tests
    and docs). Each was run from `/home/claude/wt/ENG/engrun` with the CFS repo symlinked.
- Harness: a copy of the gold harness with `W` / `RR` from the environment (`/home/claude/wt/ENG/gold/harness`).
- Jobs: copies of every job folder, run under heavy with `PYTHONHASHSEED=0`, one slot at a time:
  - `/home/claude/gold/jobs_hr`: all 20 jobs and the units IN_Ex11/workshop, IN_Ex12/unitB_link, IN_Ex12/unitC_gym,
    IN_Ex19/stem;
  - the PEB sandbox golds `/home/claude/wt/PEB/gold/jobs_hr` IN_Ex1–Ex5 (snapshot 2026-11-06 10:35);
  - IN_Ex21 `/home/claude/wt/MSME/gold/jobs_hr` (snapshot 13:11).
- Results: `/home/claude/wt/ENG/gold/results/{main,eng,eng3,eng4}/<set>/<job>.digest.json`; the table below is
  `results/compose_final.md` (`gold/tools/compose_final.py`).

**Tags** (the stage that moved the item and why):
- Round 1:
  - **A**: the governing combination was outside the old subset;
  - **B**: the combination's Table 2 class differs from the N = 0 class;
  - **C**: the knee stiffener row with the doubler at its own fy;
  - **Ka**: a wind post's own Ka; the factor is the post's own.
- Follow-up 1:
  - **PZ**: the Section 12 panel-zone doubler at its own fy;
  - **MW**: the member-wind wall scan.
- Follow-up 2:
  - **R1**: Pd from the class under axial compression alone;
  - **D-T11**: N with no meaningful Mz on the axial web row;
  - **F5**: the knee web strip with the doubler at its own fy.

| Set | Job | Status main → head | Worst member main → head (check) | Worst connection main → head | Above 1.0 at the head (main → head; tags) |
|---|---|---|---|---|---|
| PEB sandbox | IN_Ex1 | COMPLETE → PARTIAL (8) | lateral_col-WI862X225X12X8 0.996 → 1.063 (9.3) | 0.991 → 1.062 knee-WI975X225X12X8-WI975X250X14X6 | WI862X225X12X8 0.996 → 1.063 (B); WI938X225X12X8 0.958 → 1.002 (B); knee 0.991 → 1.062 (C) |
| PEB sandbox | IN_Ex2 | COMPLETE → PARTIAL (62) | roof-WI408X190X12X5 0.999 → 1.211 (9.3) | 0.994 → 1.076 knee-WI725X230X22X14-WI575X260X22X16 | WI408X190X12X5 (canopy root) 0.999 → 1.211 (A); WI225X280X18X4 (corner post) 0.990 → 1.060 → 1.085 (Ka ×1.080; D-T11); WI400X220X20X4 (wind column) 0.993 → 1.050 → 1.052 (B; R1); knee 0.973 → 1.076 (C); 52 Section 12 `smf_column_class` rows (12.11.3.1) now fail (D-T11) |
| PEB sandbox | IN_Ex3 | PARTIAL (2) → PARTIAL (6) | lateral_col-WI475X220X16X5 0.994 → gravity_col-WI200X190X12X4 1.179 (9.3) | 1.024 → 1.096 knee-WI475X220X16X5-WI675X225X12X6 | WI200X190X12X4 (corner post) 0.911 → 0.977 → 1.179 (Ka; D-T11); WI475X220X16X5 0.994 → 1.075 → 1.083 (B; R1); knee 1.024 → 1.096 (C) |
| PEB sandbox | IN_Ex4 | COMPLETE → PARTIAL (92) | gravity_col-WI475X190X12X4 0.994 → gravity_col-WI200X220X16X4 1.243 (9.3) | 0.984 → 1.083 knee-WI650X250X20X14-WI575X250X18X16 | WI200X220X16X4 (corner post) 0.970 → 1.032 → 1.243 (Ka ×1.063; D-T11); knee 0.973 → 1.083 (C); 88 Section 12 `smf_column_class` rows now fail (D-T11) |
| PEB sandbox | IN_Ex5 | PARTIAL (59) → PARTIAL (61) | lateral_col-WI862X225X12X8 1.132 → 1.214 (9.3) | 1.091 → 1.091 (rafter splice) | WI575X190X10X5 1.048 → 1.083 (B); WI950X250X14X6 1.077 → 1.101 (B); WI562X225X12X8 1.081 → 1.109 (R1); WI638X225X12X8 0.982 → 1.016 (R1); WI712X225X12X8 1.054 → 1.090 (R1); WI788X225X12X8 1.099 → 1.139 (B); WI862X225X12X8 1.132 → 1.214 (B); WI938X225X12X8 1.093 → 1.147 (B); knee 0.991 → 1.062 (C); 18 rafter splices 1.090–1.091 (unchanged) |
| MSME sandbox | IN_Ex21 | COMPLETE → COMPLETE | truss_diagonal-ISA70X70X6 0.960 → 0.960 (Table 3) | 0.964 → 0.964 truss_vertical-ISA60X60X6 | none; the bottom chord 0.950 → 0.956 → 0.782 (Ka; MW) |
| published | IN_Ex1 | PARTIAL (2) → PARTIAL (4) | lateral_col-WI300X180X8X5 1.301 → 1.378 (9.3) | 0.969 → 1.033 knee-WI1000X250X14X6-WI1000X250X14X6 | WI300X180X8X5 1.301 → 1.378 (Ka ×1.060); knee 0.969 → 1.033 (F5: the column-flange T-stub row, the web strip with its 8 mm E250 doubler) |
| published | IN_Ex2 | COMPLETE → PARTIAL (52) | roof-WI500X300X25X14 0.930 → roof-WI500X200X12X6 0.937 (9.3) | 0.974 → 0.974 lateral_col-WI700X300X22X14 | 52 Section 12 `smf_column_class` rows now fail (D-T11); the canopy beam 0.776 → 0.937 (A) |
| published | IN_Ex3 | PARTIAL (2) → PARTIAL (2) | gravity_col-WI300X200X10X6 1.190 → 1.276 (9.3) | 0.948 → 0.948 lateral_col-WI550X250X16X8 | WI300X200X10X6 1.190 → 1.276 (Ka ×1.072) |
| published | IN_Ex4 | PARTIAL (4) → PARTIAL (70) | gravity_col-WI350X250X12X6 1.207 → 1.284 (9.3) | 0.984 → 0.984 brace-WPB180X180X51.22 | WI350X250X12X6 1.207 → 1.284 (Ka ×1.063); WI450X200X10X6 1.091 → 1.072 → 1.076 (Ka < 1; R1); 66 Section 12 `smf_column_class` rows now fail (D-T11) |
| published | IN_Ex5 | PARTIAL (13) → PARTIAL (17) | lateral_col-WI300X180X8X5 1.301 → 1.378 (9.3) | 0.969 → 1.033 knee-WI1000X250X14X6-WI1000X250X14X6 | WI972X250X14X6 1.072 → 1.096 (B); WI300X180X8X5 1.301 → 1.378 (Ka); WI781X250X14X6 1.000 → 1.031 (B); WI869X250X14X6 1.052 → 1.088 (B); WI956X250X14X6 1.102 → 1.142 (B); knee 0.969 → 1.033 (F5) |
| published | IN_Ex6 | COMPLETE → COMPLETE | floor-NPB600X220X122.45 0.887 → 0.887 | 0.919 → 0.919 | none |
| published | IN_Ex7 | COMPLETE → COMPLETE | lateral_col-WPB600X300X211.92 0.953 → lateral_col-NPB750X270X202.49 0.956 | 0.838 → 0.838 | none (NPB750 0.941 → 0.954 → 0.956: A, then R1) |
| published | IN_Ex8 | COMPLETE → COMPLETE | roof-WPB500X300X155.08 0.804 → 0.804 | 0.893 → 0.893 | none |
| published | IN_Ex9 | PARTIAL (4) → PARTIAL (4) | gravity_col-WPB200X200X42.26 2.081 → 2.081 | 0.897 → 0.897 | WPB200X200X42.26 2.081, WPB200X200X61.3 1.120 (unchanged) |
| published | IN_Ex10, Ex11 (+ workshop), Ex13–Ex17, Ex19 (+ stem), Ex20 | COMPLETE → COMPLETE | unchanged | unchanged | none |
| published | IN_Ex12 (+ unitB_link, unitC_gym) | COMPLETE → COMPLETE | floor-NPB700X250X143.42 0.983 → 0.983 | 0.979 → 0.979 | none; 8 panel zones 0.926 → 0.946 (PZ: the 48 mm doublers at the E250 > 40 mm band, 230 MPa) |
| published | IN_Ex18 | COMPLETE → COMPLETE | floor-NPB750X270X174.54 0.889 → 0.889 | 0.930 → 0.930 | none; 6 panel zones 0.932 → 0.923 (PZ: 15 mm doublers at 250 MPa beside 45 mm column plates at 230) |

Reading it:
- **IN_Ex6–Ex20 and the units** keep their status and their worst ratios.
  - The moves above 0.5 % are IN_Ex7's NPB750 crane column (A, then R1), the published IN_Ex2 canopy beam (A) and
    the IN_Ex12 / IN_Ex18 panel zones (PZ).
  - Several gravity columns and one floor beam move by 0.01–0.6 %: IN_Ex12 WPB300X300X117.03 0.8212 → 0.8233,
    IN_Ex13 WPB300X300X88.34 0.9567 → 0.9579, IN_Ex15 floor NPB750X270X145.29 0.6058 → 0.6094 (finding 4: an in-span
    hogging case), and IN_Ex15 / Ex16 / Ex18 / Ex19-stem box and WPB gravity columns by 1e-4 to 1e-3.
  - No Section 12 class gate moves on these golds: their rolled and box sections stay stocky under every record's N.
    For example, IN_Ex13 SCBF column e1 is governed by a 12.2.3 record on the axial row and is still plastic.
- **The PEB golds (sandbox and published)** all fail now.
  - D-T11 moves the corner posts: IN_Ex3 0.977 → 1.179, IN_Ex4 1.032 → 1.243, IN_Ex2 1.060 → 1.085. These are
    welded posts with d/tw just above 42ε, carrying N and My with little Mz.
  - D-T11 also makes the SMRF columns of IN_Ex2 and IN_Ex4 fail 12.11.3.1 "plastic or compact" (open point 2):
    - IN_Ex2 WI725X230X22X14 has d/tw 48.6 against 42ε = 36.6. Its interior columns are on the axial row in most
      records.
    - IN_Ex4 WI552X250X20X14 has d/tw 36.6 against 36.56. It fails by a hair in 1–3 wind records where the column
      moment passes through zero.
  - R1 adds 2–4 % to the tapered columns whose webs are above 42ε: IN_Ex3 1.075 → 1.083; IN_Ex5 WI562 / WI638 /
    WI712 now over 1.0; IN_Ex1 WI788 0.967 → 0.998.
  - F5 puts the published IN_Ex1 / Ex5 knee (an 8 mm E250 doubler on a 6 mm E350 web) at 1.033.
- **IN_Ex21** stays COMPLETE.
  - The truss bottom chord falls from 0.956 to 0.782 (main e927f35 0.950; round 1 0.956, the review's figure, from
    fix A's extra combinations; follow-up 1 and the head 0.782). Its governing check becomes the Table 3 slenderness.
  - Why: on main, under the across-ridge wind, the four 1.5 m upper gable-post pieces (inside the end truss) took
    the long-wall pressure over an 18 m strip, 22 kN of wall load that is not there (member-wind totals below).
  - That load reached the frames' knee-braced trusses through the roof. Interior truss e134, the bottom chord next
    to the eave at X = 12 m, carried 82.5 kN of compression under 1.5DL+1.5WM0−R on main and 62.9 kN on the branch.
  - Its 9.3 ratio (0.950 on main, 0.956 at round 1) came from that compression. Without the artefact, the chord's worst strength ratio is 0.19
    (element e44), and its Table 3 ratio 0.782 governs.
  - The diagonal ISA80 (0.686 → 0.583), the vertical (0.708 → 0.685) and the knee brace (0.826 → 0.798) fall for the
    same reason. The governing case moves from WM0 to W_Y.
  - The IN_Ex21 owner should know that the truss has margin now; the worst member is still the Table 3 diagonal,
    0.960.

**Run-time cost of A** (seconds, harness elapsed; noise between runs is about ±10 %):

| Job | main e927f35 | fix A alone (`/home/claude/wt/ENG/timingA`) | branch |
|---|---|---|---|
| IN_Ex19 (1,308 elements × 141 combinations) | 92.9 | 94.6 (1.02×) | 94.8 (1.02×) |
| IN_Ex12 | 9.0 | 9.9 (1.10×) | 10.4 (1.16×) |
| IN_Ex2 PEB (stations, the longest run) | 256.4 | 256.3 (1.00×) | 250.5 (0.98×) |

Offline, the member-check stage alone costs 0.8 → 3.9 s on IN_Ex19 and 0.4 → 3.1 s on IN_Ex2 (station checks not
counted). Every combination is kept. This is far under the 1.5× budget, so no subset is used and no subset test is
needed.

The follow-ups add arithmetic only:
- the wall scan costs 22 → 35 ms per member-wind pattern on IN_Ex2 PEB (offline, `gold/tools/wind_totals.py`
  timing);
- the one Pd per member is computed once instead of once per class;
- D-T11 and the hogging extreme are a comparison and one extra moment.

The later A/B runs had the other heavy slot busy, so their elapsed times are not comparable: IN_Ex2 PEB 345 / 321 s,
IN_Ex19 105 / 109 s, IN_Ex12 13 / 11 s at c23c056 / 8b2ffbf.

## Member-wind totals: c23c056 takes no wind load a member should carry

For every gold with member wind (16 jobs) and every pattern in both directions, `gold/tools/wind_totals.py` builds
the job's static model and sums what `static_model.member_wind_loads` applies, on main e927f35 and on the branch
(`results/wind_totals/`):
- the wall force along the wind axis;
- the roof force, positive towards the roof.

The hand total is IS 875-3 7.3.1 F = (Cpe − Cpi) A pd with the pattern pressures. The areas come from the declared
roof planes (or from the grid for a model without them):
- across the ridge: two eave walls, length × eave height, and the two slopes;
- along the ridge: two gables, span × eave height + span × rise / 2, and half the roof each side.

The reverse direction gives the same totals with the opposite sign everywhere.

| Set | Job | Wind | Wall force, kN: main / branch / hand | Roof, Cpi +, kN: main = branch / hand | Roof, Cpi −: main = branch / hand |
|---|---|---|---|---|---|
| MSME sandbox | IN_Ex21 | across ridge (Y) | 117.4 / 95.4 / 95.4 | -326.4 / -326.4 | -39.7 / -39.7 |
| MSME sandbox | IN_Ex21 | along ridge (X) | 43.3 / 45.9 / 47.1 | -342.0 / -338.2 | -55.4 / -51.5 |
| PEB sandbox | IN_Ex1 | across ridge (Y) | 300.7 / 302.5 / 300.7 | -1117.8 / -1117.8 | -163.5 / -163.5 |
| PEB sandbox | IN_Ex1 | along ridge (X) | 108.9 / 109.4 / 108.9 | -1081.0 / -1063.3 | -126.7 / -109.0 |
| PEB sandbox | IN_Ex2 | across ridge (Y) | 1487.6 / 1496.2 / 1487.6 | -10836.2 / -10836.2 | -1235.0 / -1235.0 |
| PEB sandbox | IN_Ex2 | along ridge (X) | 1134.7 / 1141.7 / 1134.7 | -10721.4 / -10561.4 | -1120.1 / -960.1 |
| PEB sandbox | IN_Ex3 | across ridge (Y) | 424.3 / 427.5 / 424.3 | -1261.9 / -1261.9 | -184.6 / -184.6 |
| PEB sandbox | IN_Ex3 | along ridge (X) | 151.5 / 156.0 / 151.5 | -1225.4 / -1200.4 | -148.1 / -123.0 |
| PEB sandbox | IN_Ex4 | across ridge (Y) | 922.9 / 927.8 / 922.9 | -3267.3 / -3267.3 | -477.9 / -477.9 |
| PEB sandbox | IN_Ex4 | along ridge (X) | 277.6 / 279.1 / 277.6 | -3151.2 / -3108.0 | -361.8 / -318.6 |
| PEB sandbox | IN_Ex5 | across ridge (Y) | 367.1 / 369.3 / 367.1 | -1117.8 / -1117.8 | -163.5 / -163.5 |
| PEB sandbox | IN_Ex5 | along ridge (X) | 108.9 / 109.4 / 108.9 | -1081.0 / -1063.3 | -126.7 / -109.0 |
| published | IN_Ex1 | across ridge (Y) | 300.7 / 302.5 / 300.7 | -1117.8 / -1117.8 | -163.5 / -163.5 |
| published | IN_Ex1 | along ridge (X) | 108.9 / 109.4 / 108.9 | -1081.0 / -1063.3 | -126.7 / -109.0 |
| published | IN_Ex2 | across ridge (Y) | 1485.4 / 1494.0 / 1485.4 | -10836.2 / -10836.2 | -1235.0 / -1235.0 |
| published | IN_Ex2 | along ridge (X) | 1134.7 / 1141.7 / 1134.7 | -10721.4 / -10561.4 | -1120.1 / -960.1 |
| published | IN_Ex3 | across ridge (Y) | 424.3 / 427.5 / 424.3 | -1261.9 / -1261.9 | -184.6 / -184.6 |
| published | IN_Ex3 | along ridge (X) | 151.5 / 156.0 / 151.5 | -1225.4 / -1200.4 | -148.1 / -123.0 |
| published | IN_Ex4 | across ridge (Y) | 922.9 / 927.8 / 922.9 | -3267.3 / -3267.3 | -477.9 / -477.9 |
| published | IN_Ex4 | along ridge (X) | 277.6 / 279.1 / 277.6 | -3151.2 / -3108.0 | -361.8 / -318.6 |
| published | IN_Ex5 | across ridge (Y) | 367.0 / 369.2 / 367.0 | -1117.8 / -1117.8 | -163.5 / -163.5 |
| published | IN_Ex5 | along ridge (X) | 108.9 / 109.4 / 108.9 | -1081.0 / -1063.3 | -126.7 / -109.0 |
| published | IN_Ex6 | along X (WMX) | 253.2 / 253.2 / 253.2 | -586.4 / -586.4 | -53.3 / -53.3 |
| published | IN_Ex6 | along Y (WMY) | 121.6 / 121.6 / 121.6 | -594.4 / -594.4 | -54.0 / -54.0 |
| published | IN_Ex7 | across ridge (X) | 1381.9 / 1381.9 / 1381.9 | -3190.2 / -3190.2 | -666.7 / -666.7 |
| published | IN_Ex7 | along ridge (Y) | 322.4 / 322.4 / 322.4 | -3181.5 / -3136.4 | -658.0 / -612.9 |
| published | IN_Ex8 | across ridge (Y) | 447.0 / 447.0 / 447.0 | -1745.3 / -1745.3 | -255.3 / -255.3 |
| published | IN_Ex8 | along ridge (X) | 298.0 / 298.0 / 298.0 | -1706.3 / -1660.2 | -216.3 / -170.2 |
| published | IN_Ex9 | across ridge (X) | 603.0 / 603.0 / 603.0 | -2890.4 / -2234.8 | -451.5 / -272.0 |
| published | IN_Ex9 | along ridge (Y) | Cpi + 280.9 / 280.9 / 241.2; Cpi − 257.1 / 257.1 / 241.2 | -2935.1 / -2315.8 | -496.1 / -353.0 |
| published | IN_Ex10 | across ridge (Y) | 460.6 / 460.6 / 460.6 | -2585.7 / -2585.7 | -1292.8 / -1292.8 |
| published | IN_Ex10 | along ridge (X) | 307.0 / 307.0 / 307.0 | -2693.4 / -2585.7 | -1400.6 / -1292.8 |

Reading it:
- **Roof:** main = branch for every job and pattern. c23c056 does not touch roof wind.
  - Across the ridge the roof equals the hand total.
  - Along the ridge the scheme splits the E/G and F/H zones per rafter segment, not at half the roof, so it is
    within a few percent of the half-and-half hand split.
  - IN_Ex9 has a lean-to roof outside its one declared plane.
- **Walls, IN_Ex21:** the only job whose wall total drops.
  - Across the ridge, main loaded 117.4 kN against a hand total of 95.4 kN. The 22.0 kN surplus is the artefact:
    the four 1.5 m upper gable-post pieces took the long-wall pressure over an 18 m strip. The branch carries
    exactly the hand total.
  - Along the ridge, the branch carries 45.9 kN against 43.3 on main (the upper pieces keep the posts' own 6 m width)
    and a hand total of 47.1. The rest of the gable above the posts' tops (2.25 m² per gable, between 8.0 m and the
    8.75 m ridge) is carried by the end truss's top chord, which takes no wall wind in this scheme. The posts' own
    Ka (0.986) accounts for the rest.
- **Walls, the PEB golds:** the branch is 0.3–1.0 % above main and main = hand.
  - This is the round-1 wind-post Ka (7.2.2.1 (b)): factors up to ×1.080 on the corner posts, some below 1 on the
    large posts.
  - It is not c23c056: the package scan record lists no sheltered and no widened piece in any PEB gold.
- **Walls, IN_Ex6 / IN_Ex7 / IN_Ex8 / IN_Ex9 / IN_Ex10:** main = branch.
  - IN_Ex6, IN_Ex7, IN_Ex8 and IN_Ex10 equal the hand total (IN_Ex6, IN_Ex7, IN_Ex8 and IN_Ex10 declare no roof
    planes, so their hand areas come from the grid).
  - IN_Ex9's along-ridge wall is above the single-plane hand area because the lean-to's end wall (12 m wide) is
    loaded too. Its two Cpi signs differ because the lean-to wall is on one side.
- **Members that lost load:** only the four IN_Ex21 upper gable-post pieces e355 / e357 / e359 / e361, under the
  across-ridge patterns. Their own wall, the gable, is a side wall for that wind, and the engine applies side-wall
  pressure to no column (open point 1).

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

1. **Side-wall pressure is applied to no column.** This is not new; it was found while checking the gable posts.
   - The member-wind patterns carry the windward and leeward wall pressures only. The Table 5 side-wall Cpe (C / D
     at θ = 0, A / B at θ = 90) is not applied to any column.
   - For a gable post under the across-ridge wind, its own wall (the gable) is a side wall. IN_Ex21 (h/w 0.36,
     l/w 2.0) has C / D = −0.6, so the outward net is (−0.6 − 0.5) pd = −1.1 pd, 0.47 kN/m².
   - The largest outward pressure the engine gives those posts is the leeward gable under the along-ridge wind,
     (−0.1 − 0.5) pd = −0.6 pd, 0.26 kN/m².
   - Under the along-ridge wind the long-wall columns of every portal get no side-wall suction, (−0.5 ∓ 0.5) pd.
   - Adding side walls would move every portal gold. It needs a ruling before the owners re-size.
2. **D-T11 in the Section 12 gates fails the PEB SMRF columns.**
   - Ruling 2 applies D-T11 to the gates, and the gate takes the least favourable class over every record.
   - So 12.11.3.1 "plastic or compact" fails wherever a record carries compression with |Mz| ≤ 0.05 Mdz and the web
     is above 42ε:
     - IN_Ex2's WI725X230X22X14 (d/tw 48.6, interior columns on the axial row in most records), 52 rows;
     - IN_Ex4's WI552X250X20X14 (d/tw 36.6 against 36.56) in 1–3 wind records where the column moment passes through
       zero, 88 rows;
     - the published IN_Ex2 / Ex4 the same.
   - Either the owners thicken the webs (d/tw ≤ 42ε), or the lead rules that 12.11.3.1 is judged in the records
     that can form hinges (the 12.2.3 / EL combinations), or by the class without the axial row.
3. **Merging with `fix/2026-10-third-peb-golds`** (trial merge at 711cc38, not committed): one conflict, in
   `india_connections.base_plate_design_biaxial`, where the PEB branch made the same minor-axis outline fix. Keep
   either side. `peb_autosize.py` merged cleanly then. The sizer has changed since: the base-outline screen, the
   12.11.3.1 screen with N, the web-strip and member-web fy. A fresh trial merge is advised.
4. **Gold owners re-size on this engine.**
   - The knee stiffener rows: the web doubler is at its own (E250) fy. A job with E350 doublers declares
     `knee_panel.doubler_grade`; a Section 12 joint declares `doubler_grade` in its `beam_column` spec.
   - The golds with Section 12 doublers declare no doubler grade. They are at E250 now: IN_Ex12 (48 mm, 230 MPa),
     IN_Ex16, IN_Ex18 and IN_Ex9 (20 mm, 240 MPa).
5. **The cfg band helpers** listed above, to switch to `fy_is2062` (the lead takes this list).
