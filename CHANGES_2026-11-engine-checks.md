# steltic-india — 2026-11 engine checks (combinations by sign, Table 2 web class with N, one IS 2062 band)

Branch `fix/2026-11-engine-checks`, started on main 41fb2f7 and merged with main e927f35 (PR #31, the MSME
angle-truss shed; merge 1414ba4, conflicts in `member_check_is800`, `peb_station_checks` and the static replay
resolved to keep both sides). An independent review of the PEB golds
(`briefs/PEB_REVIEW.md`, sections A, B, C and "Other findings") found three gaps in the HR engine's member and joint
checks that let auto-sized members at 0.99–1.00 pass when they are overstressed. The gaps are in the engine, so they
affect every HR job, not only the PEB ones. This branch closes them and two small items. Gold cfgs are not edited: the
job owners re-size their golds on this engine (the gold-impact table below says what moves).

Four follow-ups are plain commits on top of the round-1 head 711cc38:
- **Follow-up 1:** the lead's first ruling, the Section 12 class gates with N, the panel-zone doubler fy and the
  member-wind artefact.
- **Follow-up 2:** the independent review (`briefs/ENG_REVIEW.md`), the lead's two rulings (Pd under axial
  compression alone; Steltic ruling D-T11 for the web under N + My) and review findings 4–13.
- **Follow-up 3:** the lead's rulings on open points 1 (side walls) and 2 (the Section 12 gates in the hinge state of
  the earthquake combinations), the review's R-1 (the PEB buckling section's area) and its gable-triangle note (every
  wall area reaches a member), and a facade-step fix the per-wall totals found.
- **Follow-up 4:** the lead's rulings on the brace hinge (accepted) and on IS 18168 Table 2 Ca (the earthquake records
  only).
- **Re-check 2** (`briefs/ENG_REVIEW.md`, at 10b3ae6): R2-1 (no earthquake record is never a silent pass), R2-2 (the
  facade step by shared height), R2-3 (cite 7.3), R2-4 (a WARN for an unmatched hand-built pattern), R2-5 (docs).

The code is final at bca766e.
- The full gold A/B ran on 0482f9a.
- 4e051ce changes only the IS 18168 Ca (and the sizer's copy of it). Its own A/B covers every gold with an IS 18168
  Table 2 column row.
- 10b3ae6 is text only.
- 9353828 / 0f8fd18 / bca766e (re-check 2) move no gold. IN_Ex9 was re-run, and that re-run caught one regression
  in 9353828, fixed by 0f8fd18 (Re-check 2 below).
- Later commits are docs only. Nothing is pushed.

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
  - the member check (`d_t11_axial_row`, `:2234`, called in `member_check_is800`), in every combination;
  - not in the Section 12 gates or the sizer's 12.11.3.1 screen since follow-up 3: they judge the hinge state of the
    earthquake combinations (the lead's ruling on open point 2, `D_T11_GATE_CITE`; Follow-up 3 (b) below). Between
    8b2ffbf and follow-up 3 they used this rule, which made the PEB SMRF columns fail 12.11.3.1 in wind records.
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
| 7 | Sizer 12.11.3.1 screen at N = 0 | Classified with each record's N and D-T11 | `peb_autosize.py:1370` | `test_DT11_section12_gate_and_sizer_screen_…` |
| 8 | Other Pd paths on the mid-depth row | Ruling 1's default in `compression_capacity` | `india_is800.py:2949` | `test_R_axial_only_checks_take_the_axial_compression_row_too`; mutation R1b |
| 9 | Wind posts only in custom builds, silently | The package says why none was found (`wind_post_Ka_note`: parametric storey forces, or no wall column with a pinned top) | `static_model.py:1285`, `design_pipeline.py:1479` | gold packages (A/B) |
| 10 | Doc figures / Ka tag / stale comment | Fixed: the "only two ratios move" sentence, the IN_Ex2 wind column tag (B only: its own Ka factor is 1.000), the `member_check_is800` comment | this file, ENG_RESULT4, `india_is800.py` | — |
| 11 | IN_Ex21 under c23c056 | Explained below (gold impact) | — | IN_Ex21 e2e tests |
| 12 | Column LLT_sag / LLT_hog | A cfg giving a column different lengths is rejected with a plain message | `design_pipeline.member_override` `:634` | `test_F12_…`; mutation F12 |
| 13 | Suite red on the contract lint | `panel_zone_doubler_grade` / `_fy_MPa` named in the contract | `contract/README_AGENT.md:103` | `test_fix_D05_contract_lint.py` |
| — | (found by the suite after the rulings) The sizer proposed a column base section that did not fit the declared base plate, so the full run failed the plate-outline gate | `LocalModel._base_outline_fails` screens such sections (L ≥ 0.95 d, B ≥ 0.95 bf) | `peb_autosize.py:1561` | `test_peb_levers_2026_10.py::test_autosize_passes_and_is_deterministic` |

## Follow-up 3 (2026-11-06): the lead's rulings on open points 1 and 2, review R-1 and the gable triangle

Plain commits on 557a8d9: 845ffb3 (b), d901ba2 (R-1), 14a707a (a and the gable triangle), 0482f9a (the facade step the
per-wall totals found), c837ac6 (a test). The code is final at 0482f9a; the final A/B and the suite ran on it.

### (a) The side walls take their IS 875-3 Table 5 Cpe (open point 1)

- **The rule, as ruled.** Every member-wind pattern loads the columns and posts of the two side walls (the walls
  parallel to the wind) with:
  - the side-wall Cpe of Table 5 with each ±Cpi of the pattern, F = (Cpe − Cpi) A pd (7.3.1);
  - the tributary width of the member's own wall;
  - the Ka of a wind post's own side-wall area (7.2.2.1 (b)), as for the windward and leeward walls; frame columns
    keep the pattern's frame Ka.
- **Zones: what the corpus's Table 5 says.**
  - The table (`documents/standards/IS_875_Part_3_2015/markdown/pages_recovered/page_015.md`, clause 7.3.3.1) gives
    one average Cpe for each of the four walls: "the wind at θ = 0° blows onto wall **A**; **B** is the opposite wall;
    **C** and **D** are the two side walls (at θ = 90° the wind blows onto **C**)."
  - It has no zones by distance from the windward edge. Its only edge band is the local Cpe strip of width 0.25 w,
    and 7.3 (the general text of Pressure Coefficients) keeps local coefficients off members: "Coefficients for the local effects should only be used for
    calculation of forces on these local areas affecting roof sheeting, glass panels, and individual cladding units
    including their fixtures. They should not be used for calculating force on entire structural elements such as
    roof, walls or structure as a whole."
  - So each side-wall member takes its wall's Cpe over its whole tributary, and no tributary spans two zones. Zones
    A / B / C by distance from the windward edge are the EN 1991-1-4 scheme; they are not in IS 875-3:2015, and the
    engine does not introduce them.
  - Table 5 has C = D at θ = 0 and A = B at θ = 90 in every row. In the golds: C / D −0.5 to −0.7, A / B −0.5.
- **Where.**
  - `india_wind_tables.lowrise_member_wind` writes `wall_side_kNm2` = (Cpe − Cpi) pd, `wall_cpe` (the Table 5
    surface and Cpe of each wall) and `pd_kNm2` on every pattern; `india_combos` carries them to the static model.
  - `static_model.side_wall_pressure` takes the pattern's value. For a pattern without it (IN_Ex6's hand-built
    patterns) it derives the Cpe from Table 5 at the model geometry: θ = 0 for wind onto the longer face, checked
    against the windward / leeward Cpe the pattern's own pressures imply. If they are more than 0.05 from both
    angles, the record carries a WARN (re-check 2, R2-4). A pattern whose side walls cannot be loaded is a FAIL in
    the package check (`consistency.member_wind_side_wall_issues`), never silent.
  - The side walls are found by the same wall scan as the windward and leeward walls, run across the wind
    (`wall_wind_pieces`: first exposed line per strip, the roof envelope, the own wall's width). The parametric
    nodal fallback loads them too. Text: `SIDE_WALL_CITE`.
  - Record: `member_wind_wall_scan.patterns[p]` lists every loaded member with its wall (windward / leeward / side_lo
    / side_hi), Table 5 surface, Cpe, Cpi, q and width; the side-wall pressure record and its source; the side
    walls' sheltered pieces. `wind_post_Ka` has one record per post and wall.
- **Girts** are designed by the CFS engine (owner decision D-T5) on the worst of all four walls' Table 5 Cpe at θ 0 and
  90 plus the local strips (`steltic_CFS_india` `india_cfs_members.member_pd`, face 'wall', zone 'all'). Side walls
  were already covered there; nothing changes.
- **The frame-level wind cases** (the static replay of the storey forces W_X / W_Y) apply the net along-wind force
  per level (Cf, or the windward − leeward Cpe difference). The two side walls' forces are equal and opposite
  (C = D, A = B), so they add no net force and no torsion; nothing is left out there. The totals table below shows
  side_N = 0.000 kN for every gold and pattern. The side walls' member effects (the columns bending under the suction)
  are in the member-wind cases.

### (b) The Section 12 gates in the earthquake combinations, in the hinge state (open point 2)

- **As ruled, part of D-T11** (`D_T11_GATE_CITE`, `india_is800.py:2224`; `table2_class_by_combination`,
  `india_is800_s12.py:245`):
  - 12.11.3.1 and the other Section 12 class requirements (12.7.2.4, 12.8.2.5, 12.8.4.1) are about the plastic hinge
    that forms under earthquake. The gate is judged in the earthquake combinations only: the Table 4 rows with EL and
    the 12.2.3 rows (`earthquake_record`; `section12_model_data` now writes each record's `lateral_kind`). The wind,
    gravity and service records are not judged; the record counts both.
  - In each earthquake record the web is classified in the hinge state, major-axis plastic bending with that
    combination's N: the "generally" rows with its r1 / r2 (the mid-depth row with no N). D-T11's "axial compression"
    row is not used there; it stays for the member resistance checks in every combination.
  - A member with no earthquake record is not judged (re-check 2, R2-1, below): not applicable under `no_seismic`,
    otherwise not evaluated and open.
- **Braces (the lead's ruling, 2026-11-06, part of D-T11).** A brace's plastic hinge is its buckling hinge, about the
  axis of the larger KL/r (`brace_hinge_axis`).
  - About the major axis the brace takes the same "generally" rows.
  - About the minor axis (or on a tie) the web lies on that hinge's neutral axis and carries the uniform N, so it
    keeps the axial row. Reading major-axis bending into a minor-axis buckling hinge would be unconservative.
  - No gold brace moves: every gold I / box brace passes on either row (the generally rows are never stricter than
    the axial row, with the 42ε floor).
- **The sizer's 12.11.3.1 screen** does the same (`LocalModel._class_with_N`, `peb_autosize.py:1370`): earthquake labels
  from the run's `load_combinations`, the generally rows.
- **IS 18168 Table 2 (ii) Ca** (follow-up 4, the lead's ruling): from the earthquake records only, as the gates
  (Follow-up 4 below).

### R-1: the PEB buckling section takes the segment's effective area (review, blocking)

- `peb_buckling_section` scaled the buckling section's Pd by the area of the segment it was given. The Section 12
  tapered-column path passes the gross segment. So Pdz was Ag fcd,z even for a segment slender on the 42ε row.
- On IN_Ex1's main column WI862X225X12X8 that was 2,696 kN, against the member check's 1,709 kN (Ae 7,672 of 12,104
  mm²).
- It now takes the area from `comp["effective_section"]["A_eff_mm2"]` when present, so every caller gets Ae; the
  record states it (`A_segment_mm2`, `buckling_basis`). The member check is unchanged: it passed the 42ε props already.
- No gold row moves. The largest PEB 12.5.1 trigger P/Pd at the head is 0.16 (the IN_Ex3 sandbox), under 0.4, so no
  12.5.1.1 row switches on.

### Every wall area reaches a member (the review's gable-triangle note)

- **What was missing.** The wall scan loads each column piece over its tributary width × its own length. Where a
  wall's top follows a sloping member, three kinds of area went wrong:
  - the wall above a line's top within its strip carried nothing: the corner columns end at the eave below the gable
    rafter, and IN_Ex21's posts end at 8.0 m below the end truss's top chord;
  - a post's rectangle reached above the rafter on its down-slope side;
  - on IN_Ex9 (end frames with no posts) the whole gable triangle above the eave carried nothing.
- **The rule** (`static_model.envelope_residuals`, `ENVELOPE_RESIDUAL_BASIS`). In a wall plane with a sloping envelope
  member (gable rafter, end-truss top chord):
  - the wall at each point along it runs up to that member, and the column line whose tributary strip holds the
    point carries it;
  - the strip's area above or below the line's loaded height goes to the line's upper end, as a nodal force at the
    top node of its top piece;
  - a wind post's Ka area includes it.
- **IN_Ex21.** The gable is 137.25 m², and 135.00 was loaded before.
  - The review's triangle over the posts' tops (y 6–12 m, 8.0 to 8.75 m, 2.25 m²) is balanced inside the posts'
    strips: each post's 3–9 m strip holds 48 m² of wall, exactly its 6 m × 8.0 m rectangle.
  - What was really missing is the two triangles above the eave next to the corners, 1.125 m² each. Each corner column
    now carries its triangle at its eave node: up to 0.58 kN (1.125 m² × 0.515 kN/m², the windward gable
    of WM90−) and 0.53 kN as a side wall (× 0.4721, WM0+).
- **The PEB golds** have posts up to the rafter.
  - Their residuals net to zero on every gable (each corner +, the posts −), so their totals equal the hand total as
    before.
  - The posts give up the part of their rectangle above the rafter, and the corner columns take their triangles.
- **IN_Ex9.** Each corner column of the two portal gables takes half of the 36 m² triangle above the eave
  (18 m² at its eave node).

### A facade step (found by the per-wall totals)

- On IN_Ex9 (a flat lean-to beside the hall) the scan gave a piece half the distance to the next strip at its height,
  even where that strip's wall stands on another plane.
  - The hall's corner column (12, 60) took 6 m toward the lean-to over its 8 m, a wall that does not exist at y = 60.
  - The lean-to's end wall next to wall B (x 6–12 m at y = 30) had no member.
  - The +Y face carried 270 m² below the eave line against 252.
- `wall_wind_pieces` now ends a wall at its line when the neighbouring strip's wall lies behind it. When the
  neighbouring wall stands in front and a column of this plane stands at the neighbour's line (the re-entrant corner),
  that column carries the other half, piece by piece over the height each of its pieces shares with the wall (re-check
  2, R2-2). The record lists the steps (`stepped_facade`).
- No other gold has a step.

### D-T11: the lead's acceptance of the two readings (stated as rulings)

- "Compression" in D-T11 means P > `p_comp_tol` = max(1 N, 10⁻³ Ag fy).
- "Mdz" in the 0.05 Mdz threshold is the section's 8.2.1.2 bending strength without axial force
  (`mdz_without_axial_force`), not the LTB Mdz of 9.3.2.2. It is the larger value, so more combinations go to the axial
  row: the stricter side.

### Known limits

- A slender welded box now has a Pd (`effective_area_box_axial`), but its bending capacity is not coded. So its member
  check is "not evaluable" in any combination where it is slender: a visible failure, the lead's ruling to keep. No
  gold has one.

## Follow-up 4 (2026-11-06): the lead's decisions on the follow-up 3 open points

- **Brace hinge: accepted.** A brace's hinge is its buckling hinge; on a minor-axis hinge (or a tie) the web keeps the
  axial row. Stated under D-T11 (Follow-up 3 (b), `D_T11_GATE_CITE`).
- **IS 18168 Table 2 (ii) Ca from the earthquake records only** (4e051ce):
  - The rule: Ca = Pu / (Py / γm0) is the axial ratio at the seismic ductility demand. So `_ca_governing`
    (`india_is800_s12.py:329`) takes Pu from the earthquake records only (`earthquake_record`: the Table 4 EL rows and
    the 12.2.3 rows), as the Section 12 gates.
  - The wind, gravity and service records are not judged, and the record counts both (`CA_EQ_BASIS`, `:324`). A
    member with no earthquake record has no Ca, never 0: its row is not judged (re-check 2, R2-1).
  - The sizer's Table 2 screen follows (`LocalModel._Ca`, `peb_autosize.py:1390`).
  - The Table 2 (ii) web limit falls with Ca, so this can only relax a column whose largest Pu was a wind or gravity
    record.
- **Gust ratio:** for the PEB owner. The lead tells them that the side walls take the same factor as the other walls
  in each pattern.
- **Slender box bending:** a known limit (Follow-up 3).
- **Gold A/B of the Ca change** (`gold/results/eng6`, `results/compose_ca.md`, `gold/tools/compose_ca.py`):
  - It covers every gold whose package has IS 18168 Table 2 (ii) column rows, 19 runs at 4e051ce against eng5 at
    0482f9a. That is the SMF golds too (the PEB IN_Ex2 / Ex4 SMRF, IN_Ex8, IN_Ex9, IN_Ex12 and its units, IN_Ex16,
    IN_Ex18), not only the EBF / SCBF / OCBF ones: Ca reaches every IS 18168 column.
  - Result: no Table 2 (ii) dc and no ok moved, no other member, connection or Section 12 row moved, and every status
    is equal.
  - Ca from the earthquake records can only be at or below Ca from every record, and the web limit falls with Ca, so
    a row can only relax. None did by more than the digests' precision.

## Re-check 2 (2026-11-06, `briefs/ENG_REVIEW.md` at 10b3ae6): R2-1 to R2-5

- **R2-1 (medium): no earthquake record is never a silent pass.** Before, a member with no earthquake record was
  classified at N = 0 by the Section 12 class gates and passed, and its IS 18168 Table 2 (ii) Ca defaulted to 0 (the
  loosest web limit). Now (`no_earthquake_record`, `table2_class_by_combination`, `_ca_governing`,
  `_table2_column_row`, `india_is800_s12.py`):
  - **`no_seismic` declared** (no earthquake family; `section12_model_data` passes it): the gate rows and the Table 2
    (ii) column row are not applicable, with ok None, the reason and `not_applicable`. The design status does not count
    them (`_screen_findings`, `india_seismic_gates.py`; `capacity_check_entry`, `design_pipeline.py`), since no
    seismic detailing applies.
  - **A job with a Section 12 seismic system** but no earthquake record for a member the gate covers: the rows are not
    evaluated, with ok None and a plain message ("no earthquake combination among the member's N force records in a
    job with a Section 12 seismic system: a model / cfg error ..."). They count as open reasons.
  - Ca is never 0 in either case. The sizer's 12.11.3.1 and Table 2 screens skip such a member instead of using the
    N = 0 class or Ca 0.
  - **Gold check:** every gate and Ca row of the 30 golds has at least one earthquake record (for braces, a Table 4
    EL row; from each run's `member_combo_forces.json` and `load_combinations`). No gold declares `no_seismic`, and
    every gold has earthquake combinations. So no status can move. The IN_Ex9 re-run at 9353828 is below.
- **R2-2 (low): the facade step by shared height.** Every piece of the re-entrant line now takes width × the height it
  shares with the stepped wall's piece, spread over its own length. So lines split at different heights load the wall
  once. The reviewer's two IN_Ex9 variants (the lean-to corner column split at 2.5 m; the hall column in one piece
  0–8 m) gave 318 / 306 m² and now give 288 m².
  - 9353828 took the shared height over the stepped piece's whole length. On IN_Ex9's −X face (the across-ridge wind)
    the hall column (12, 37.5), one piece 0–8 m, then gave the re-entrant line's upper piece (5–8 m) a share it already
    carries with its own width: 11.25 m² twice. The IN_Ex9 status re-run caught it (2 member ratios moved).
  - 0f8fd18 limits the share to the step band, the heights where the neighbouring strip's wall stands in front. A test
    pins both IN_Ex9 faces across the ridge at 480 m².
  - bca766e lists the steps of both scans in the package (`stepped_facade`, `side_stepped_facade`).
- **R2-3:** the local-coefficient sentence is IS 875-3 7.3 (the general text of Pressure Coefficients), not 7.3.1,
  in `SIDE_WALL_CITE`, the generator's record and this file. 7.3.1 stays for F = (Cpe − Cpi) A pd.
- **R2-4:** a hand-built pattern whose own windward / leeward Cpe are more than 0.05 from both Table 5 wind angles gets
  a WARN in its side-wall record and in `member_wind_wall_scan.warnings`. IN_Ex6's patterns match.
- **R2-5:** the IN_Ex7 row in the gold table now gives the governing record's forces (element 1: P 3.5 kN, Mz 320.7
  kN·m, My 217.0 kN·m).
- **Status check at bca766e.** None of the 30 gold statuses changes:
  - IN_Ex9 re-run (`gold/results/eng8`) equals 0482f9a: PARTIAL (4), with none of its 12 members, 12 connections or
    50 Section 12 rows moved. At 9353828 two member ratios had moved: R2-2's regression, fixed by 0f8fd18.
  - No gold lacks earthquake combinations or declares `no_seismic`, so there is no no-seismic gold to re-run.
  - R2-1 cannot move a gold (the row check above).
  - The per-wall member-wind totals of the 17 golds at bca766e are identical to 0482f9a's and equal the hand totals
    on every wall (`gold/results/wind_totals2`).

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

`tests/test_engine_checks_2026_11_followup.py` (follow-ups 1 and 2, and the follow-up 3 gate and R-1 tests; 34 tests):

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

Follow-ups 3 and 4 and re-check 2 (`tests/test_engine_checks_2026_11_followup3.py`, 19 tests, and in `test_engine_checks_2026_11_followup.py`;
new fixtures `IN_Ex4_smf_column_e13_s12.json` (an IN_Ex4 SMRF column piece and its 189 records from the eng4 run),
`IN_Ex9_wall_wind_geometry.json`, `IN_Ex20_scbf_column_e126_s12.json`; the IN_Ex13 fixture gains each record's
`lateral_kind`):

| Item | Unit tests | End-to-end on a real gold piece |
|---|---|---|
| (b) Section 12 gates | `test_DT11_gate_web_beyond_the_generally_limit_at_an_EL_combination_still_fails` (NPB600 at 0.45 Py in a Table 4 EL row: semi-compact, fails; wind / gravity records only: not judged), `test_1_class_by_combination_takes_each_axial_force` / `…_smf_and_scbf_column_gates_…` (updated: judged / not-judged counts), `test_1_brace_gates_judge_the_buckling_hinge_in_the_table4_EL_records` (minor-axis hinge: axial row, slender; major-axis hinge: generally rows, plastic), `test_DT11_section12_gate_and_sizer_screen_use_the_same_rule` (the member check slender on D-T11's row; the gate compact in the hinge state; the sizer skips a wind record and classifies an earthquake one on the generally rows) | `test_DT11_gate_e2e_IN_Ex4_column_failing_only_in_a_wind_record_now_passes`: IN_Ex4 WI636X250X20X14 (d/tw 42.57 > 42ε = 36.56), slender at 8b2ffbf in 0.9DL+1.5W_Y; plastic in all 136 earthquake records; `test_1_e2e_IN_Ex13_…` (updated: 104 earthquake records judged, the generally rows) |
| R-1 | — | `test_R1_e2e_IN_Ex1_section12_tapered_segment_takes_its_effective_area`: both paths give the member check's Pdz 1,709 kN (was 2,696 on the Section 12 path); the 12.5.1 trigger uses it |
| (a) side walls | `test_side_wall_pressure_from_the_generator_IN_Ex21` (C / D −0.6 at θ 0, A / B −0.5 at θ 90, q = (Cpe − Cpi) pd), `test_side_wall_pressure_derived_for_a_pattern_without_it_IN_Ex6` (2 cases: θ from the plan, checked against the pattern's own Cpe), `test_side_walls_not_loadable_is_a_consistency_failure` | `test_integration_mini_PEB_side_walls_and_gable_residual` (member_wind_loads on the PEB test shed: both gables 75.6 m² as side walls, equal and opposite; every side member loaded along X with its surface and Cpe recorded), `test_integration_mini_PEB_side_wall_post_takes_the_Ka_of_its_own_side_area`, `test_e2e_IN_Ex21_long_walls_as_side_walls_under_the_along_ridge_wind` (IN_Ex21's geometry: 234 m² each, the gable posts above the eave not on the long wall) |
| Every wall area | (the mini-shed test: corners +0.45 m², the post −0.9 m² at their top nodes) | `test_e2e_IN_Ex21_every_gable_area_reaches_a_member`: IN_Ex21's gables 135.00 → 137.25 m², each corner column's 1.125 m² triangle at its top |
| Facade step | — | `test_e2e_IN_Ex9_lean_to_facade_step`: both gable faces 288 m², the hall's corner 12 m wide, the re-entrant column 6 m |
| Re-check 2 | `test_R2_1_no_earthquake_record_in_a_seismic_job_is_not_evaluated_and_open` (2 cases: the reviewer's noeq_probe, wind only and gravity only; with an EQ record judged), `test_R2_1_no_seismic_job_marks_the_gates_not_applicable` (column and brace; no open reason), `test_R2_4_derived_side_wall_warns_when_the_pattern_matches_neither_angle` | `test_R2_2_facade_step_with_offset_splits_loads_the_wall_once` (2 variants on IN_Ex9's geometry, the reviewer's step_probe), `test_R2_2_IN_Ex9_across_the_lean_to_each_wall_once` (both faces 480 m²) |
| IS 18168 Ca (follow-up 4) | `test_Ca_from_the_earthquake_records_only` (the largest Pu, 0.6 Py, is a wind record: Ca 0.3 from the EL row; wind / gravity only: Ca = 0), `test_Ca_sizer_screen_from_the_earthquake_records_only` | `test_Ca_e2e_IN_Ex20_column_whose_largest_Pu_is_a_wind_record`: IN_Ex20 SCBF column e126 WPB320X300X126.66, largest Pu 243.5 kN in 1.5DL−1.5W_Y+1.5W_Y_across (Ca 0.0693, web limit 58.19 at 0482f9a); now Ca from its 104 earthquake records, the web limit higher, the row's dc on the flange unchanged |

Mutation check of follow-ups 3 and 4 and re-check 2 (`/home/claude/wt/ENG/tools/mutate3.py`; logs
`logs/mutation3.txt` at c837ac6, `logs/mutation4.txt` at 4e051ce, `logs/mutation5.txt` at 9353828 / 0f8fd18, 23 of
23): every reverted fix fails its tests.

| Mutation (reverted in a scratch copy) | Tests that fail |
|---|---|
| G1: the gates judge every record again (no earthquake filter) | 3 |
| G2: the gates back to D-T11's axial row | 1 |
| G3: a brace's hinge always major | 1 |
| G4: the sizer screen judges every record again | 1 |
| G5: the sizer screen back to D-T11's axial row | 1 |
| R-1: the PEB buckling section back to the gross segment area | 1 |
| S1: no side-wall scan | 2 |
| S2: the generator's side walls take A / B at θ 0 | 1 |
| S3: the derived side-wall Cpe from the windward surface | 2 |
| S4: a side wall that cannot be loaded passes the package check | 1 |
| S5: a side-wall post keeps the frame Ka | 1 |
| E1: the envelope residual not computed | 3 |
| E2: the residual computed but not applied | 1 |
| F1: a wall runs on past its corner at a facade step | 1 |
| F2: no re-entrant corner column | 1 |
| Ca1: IS 18168 Table 2 Ca from every record again | 2 |
| Ca2: the sizer's Ca from every record again | 1 |
| R21a: every member with no earthquake record not applicable (silent, never open) | 2 |
| R21b: Ca back to 0 with no earthquake record | 4 |
| R21c: a not-applicable row counted as open again | 1 |
| R22: the step's re-entrant share by width, not width × shared height | 2 |
| R22b: the step's share over the whole shared height, not the step band (9353828's double count) | 1 |
| R24: no warning for a pattern matching neither angle | 1 |

Full HR suite, under heavy:
- the merged head 1414ba4: 1,281 passed, 5 skipped, 0 failed (main e927f35: 1,258 / 5 as the lead reports; main
  41fb2f7, run here before any change: 1,200 / 5);
- 1ddb6d1 (the reviewer's run): 1 failed, the contract lint (finding 13);
- 8b2ffbf: 1,306 passed, 3 failed, 5 skipped (`logs/suite_eng_review.txt`). The three failures were record-layout
  assertions that pinned 17 fields (finding 4 adds `Mmaj_hog_min`); eccfc95 extends them;
- eccfc95 (the follow-up 2 head): 1,312 passed, 5 skipped, 0 failed (`logs/suite_eng_final2.txt`);
- c837ac6 (code 0482f9a, the follow-up 3 head): 1,324 passed, 5 skipped, 0 failed (`logs/suite_eng_f3.txt`);
- 10b3ae6: not run here (the batch was stopped for re-check 2); the reviewer's run there is 1,327 passed, 5 skipped;
- bca766e: 1,332 passed, 2 failed (the two existing tests above, updated in 3dc1c5b), 5 skipped
  (`logs/suite_eng_r2.txt`);
- **the final head 3dc1c5b (code bca766e): 1,334 passed, 5 skipped, 0 failed, 1 warning (a third-party
  starlette/httpx deprecation), 443.5 s under heavy** (`logs/suite_eng_r2b.txt`).

Existing tests changed, each because a review finding changes the value it pins:
- `test_peb_levers_2026_10.py::test_rods_refused_outside_zone_II_ocbf`: rod Td at 240 MPa (finding 6);
- `test_span_moment_fix.py::test_record_layout_and_combo_forces` and the two `test_third_wave_peb.py` layout tests:
  REC_FIELDS[13:17] plus `Mmaj_hog_min` (finding 4);
- this branch's own round-1 `test_B_axial_row_only_without_any_bending_in_the_member_check`: rewritten to D-T11
  (ruling 2);
- follow-up 3: this branch's own Section 12 gate tests in `test_engine_checks_2026_11_followup.py` (the gates now judge
  the earthquake records in the hinge state: the records carry `lateral_kind`, the expected rows and counts follow).
- re-check 2: `test_fix_H05.py::test_box_column_smrf_zone_iv_checked_with_box_row` gives its box column one
  earthquake record with N = 0 (its Table 2 (ii) row is not judged with none, R2-1; the limits it pins are at Ca 0 as
  before); `test_fix_IN_min_dc_sense.py::test_capacity_design_flattening_keeps_sense` checks the sense through
  `capacity_check_entry`, where the copy now lives.

## Gold impact (final A/B: main e927f35 against the head 0482f9a; every HR gold run once per engine)

**Setup.**
- Engines:
  - main e927f35 (a worktree at `/home/claude/wt/ENG/base`; the digests are in `results/main`);
  - the branch at four points, to tag each move with its fix: 1414ba4 (round 1, `results/eng`), c23c056
    (follow-up 1, `results/eng3`), 8b2ffbf (follow-up 2, `results/eng4`) and 0482f9a (the head's code, follow-up 3,
    `results/eng5`; c837ac6 changes only tests and docs). Each was run from `/home/claude/wt/ENG/engrun` with the CFS
    repo symlinked.
- Harness: a copy of the gold harness with `W` / `RR` from the environment (`/home/claude/wt/ENG/gold/harness`).
- Jobs: copies of every job folder, run under heavy with `PYTHONHASHSEED=0`, one slot at a time:
  - `/home/claude/gold/jobs_hr`: all 20 jobs and the units IN_Ex11/workshop, IN_Ex12/unitB_link, IN_Ex12/unitC_gym,
    IN_Ex19/stem;
  - the PEB sandbox golds `/home/claude/wt/PEB/gold/jobs_hr` IN_Ex1–Ex5 (snapshot 2026-11-06 10:35);
  - IN_Ex21 `/home/claude/wt/MSME/gold/jobs_hr` (snapshot 13:11).
- Results: `/home/claude/wt/ENG/gold/results/{main,eng,eng3,eng4,eng5}/<set>/<job>.digest.json`; the table below is
  `results/compose_f3.md` (`gold/tools/compose_f3.py`). All 30 runs ended rc 0.

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
- Follow-up 3:
  - **SW**: member wind on every wall: the side walls' Table 5 Cpe, every wall area reaching a member, the facade step;
  - **G**: D-T11 for the Section 12 gates (the earthquake records, in the hinge state);
  - **R-1**: the PEB buckling section's area on the Section 12 path (no row moves).

| Set | Job | Status main → 8b2ffbf → head | Worst member main → head (check) | Worst connection main → head | Above 1.0 at the head (main → 8b2ffbf → head; tags), and follow-up 3's moves |
|---|---|---|---|---|---|
| PEB sandbox | IN_Ex1 | COMPLETE → PARTIAL (8) → PARTIAL (10) | lateral_col-WI862X225X12X8 0.996 → lateral_col-WI200X160X12X4 1.133 (9.3) | 0.991 → 1.062 knee-WI975X225X12X8-WI975X250X14X6 | WI200X160X12X4 (gable corner column) 0.911 → 0.965 → 1.133 (round 1; SW); WI862X225X12X8 0.996 → 1.063 (B); WI938X225X12X8 0.958 → 1.002 (B); knee 0.991 → 1.062 (C) |
| PEB sandbox | IN_Ex2 | COMPLETE → PARTIAL (62) → PARTIAL (10) | roof-WI408X190X12X5 0.999 → gravity_col-WI225X280X18X4 1.285 (9.3) | 0.994 → 1.076 knee-WI725X230X22X14-WI575X260X22X16 | WI225X280X18X4 (corner post) 0.990 → 1.085 → 1.285 (Ka ×1.080; D-T11; SW); canopy root WI408X190X12X5 0.999 → 1.211 (A); wind column WI400X220X20X4 0.993 → 1.052 (B; R1); knee 0.973 → 1.076 (C); **the 52 `smf_column_class` rows that failed at 8b2ffbf pass (G)**; 16 column bases 0.93 → 0.936 (SW) |
| PEB sandbox | IN_Ex3 | PARTIAL (2) → PARTIAL (6) → PARTIAL (6) | lateral_col-WI475X220X16X5 0.994 → gravity_col-WI200X190X12X4 1.178 (9.3) | 1.024 → 1.096 knee-WI475X220X16X5-WI675X225X12X6 | WI200X190X12X4 (corner post) 0.911 → 1.179 → 1.178 (Ka; D-T11); WI475X220X16X5 0.994 → 1.083 (B; R1); knee 1.024 → 1.096 (C) |
| PEB sandbox | IN_Ex4 | COMPLETE → PARTIAL (92) → PARTIAL (4) | gravity_col-WI475X190X12X4 0.994 → gravity_col-WI200X220X16X4 1.242 (9.3) | 0.984 → 1.083 knee-WI650X250X20X14-WI575X250X18X16 | WI200X220X16X4 (corner post) 0.970 → 1.243 → 1.242 (Ka ×1.063; D-T11); knee 0.973 → 1.083 (C); **the 88 `smf_column_class` rows that failed at 8b2ffbf pass (G)**; 4 column bases 0.911 → 0.917 (SW) |
| PEB sandbox | IN_Ex5 | PARTIAL (59) → PARTIAL (61) → PARTIAL (63) | lateral_col-WI862X225X12X8 1.132 → 1.214 (9.3) | 1.091 → 1.091 (rafter splice) | WI200X160X12X4 (gable corner column) 0.911 → 0.965 → 1.158 (round 1; SW); tapered columns / rafters up to 1.214 (B; R1, as at 8b2ffbf); knee 0.991 → 1.062 (C); 18 rafter splices 1.090–1.091 (unchanged) |
| MSME sandbox | IN_Ex21 | COMPLETE → COMPLETE → COMPLETE | truss_diagonal-ISA70X70X6 0.960 → 0.960 (Table 3) | 0.964 → 0.964 truss_vertical-ISA60X60X6 | none; the eave column MB300 0.731 → 0.815 (SW: the gable's side-wall suction on the corner columns under the across-ridge wind) |
| published | IN_Ex1 | PARTIAL (2) → PARTIAL (4) → PARTIAL (4) | lateral_col-WI300X180X8X5 1.301 → 1.450 (9.3) | 0.969 → 1.033 knee-WI1000X250X14X6-WI1000X250X14X6 | WI300X180X8X5 (gable corner column) 1.301 → 1.378 → 1.450 (Ka ×1.060; SW); knee 0.969 → 1.033 (F5) |
| published | IN_Ex2 | COMPLETE → PARTIAL (52) → **COMPLETE** | roof-WI500X300X25X14 0.930 → roof-WI500X200X12X6 0.937 (9.3) | 0.974 → 0.974 lateral_col-WI700X300X22X14 | none; **the 52 `smf_column_class` rows pass (G)**; the canopy beam 0.776 → 0.937 (A); gravity column WI450X350X20X10 0.679 → 0.702 (SW) |
| published | IN_Ex3 | PARTIAL (2) → PARTIAL (2) → PARTIAL (2) | gravity_col-WI300X200X10X6 1.190 → 1.371 (9.3) | 0.948 → 0.948 lateral_col-WI550X250X16X8 | WI300X200X10X6 (corner post) 1.190 → 1.276 → 1.371 (Ka ×1.072; SW) |
| published | IN_Ex4 | PARTIAL (4) → PARTIAL (70) → PARTIAL (4) | gravity_col-WI350X250X12X6 1.207 → 1.359 (9.3) | 0.984 → 0.984 brace-WPB180X180X51.22 | WI350X250X12X6 (corner post) 1.207 → 1.284 → 1.359 (Ka ×1.063; SW); WI450X200X10X6 1.091 → 1.076 → 1.078 (Ka < 1; R1; SW); **the 66 `smf_column_class` rows pass (G)** |
| published | IN_Ex5 | PARTIAL (13) → PARTIAL (17) → PARTIAL (17) | lateral_col-WI300X180X8X5 1.301 → 1.473 (9.3) | 0.969 → 1.033 knee-WI1000X250X14X6-WI1000X250X14X6 | WI300X180X8X5 (gable corner column) 1.301 → 1.378 → 1.473 (Ka; SW); WI972 / WI781 / WI869 / WI956 rafters 1.03–1.14 (B, as at 8b2ffbf); knee 0.969 → 1.033 (F5) |
| published | IN_Ex6 | COMPLETE → COMPLETE → COMPLETE | floor-NPB600X220X122.45 0.887 → 0.887 | 0.919 → 0.919 | none (the side walls derived from Table 5 for its hand-built patterns move no ratio by more than 0.002) |
| published | IN_Ex7 | COMPLETE → COMPLETE → **PARTIAL (2)** | lateral_col-WPB600X300X211.92 0.953 → 1.154 (9.3) | 0.838 → 0.838 lateral_col-NPB750X270X202.49 | **WPB600X300X211.92 0.953 → 0.953 → 1.154 (SW)**: element 1, an end-frame column (0–8.5 m), under 1.5DL+1.5WM0+R: P 3.5 kN compression, Mz 320.7 kN·m (hogging at the base), My 217.0 kN·m about its minor axis from the gable's side-wall suction ((−0.7 − 0.5) pd = −2.0 kN/m² over half the 21 m gable; the reviewer's hand check gives 1.1536); NPB750 0.941 → 0.956 (A; R1, as at 8b2ffbf) |
| published | IN_Ex8 | COMPLETE → COMPLETE → COMPLETE | roof-WPB500X300X155.08 0.804 → 0.818 (9.3) | 0.893 → 0.893 | none; the roof beam 0.804 → 0.818 and BOX400 column 0.584 → 0.594 (SW) |
| published | IN_Ex9 | PARTIAL (4) → PARTIAL (4) → PARTIAL (4) | gravity_col-WPB200X200X42.26 2.081 → 2.081 | 0.897 → 0.897 | WPB200X200X42.26 2.081, WPB200X200X61.3 1.120 (unchanged); the BOX450X400 column 0.404 → 0.353 (SW: the facade step, the hall's corner no longer loaded over the lean-to's width) |
| published | IN_Ex10 | COMPLETE → COMPLETE → COMPLETE | roof-WPB450X300X139.76 0.920 → 0.920 | 0.786 → 0.786 | none; the WPB320 column 0.446 → 0.494 (SW) |
| published | IN_Ex11 (+ workshop), Ex13–Ex17, Ex19 (+ stem), Ex20 | COMPLETE → COMPLETE → COMPLETE | unchanged | unchanged | none |
| published | IN_Ex12 (+ unitB_link, unitC_gym) | COMPLETE → COMPLETE → COMPLETE | floor-NPB700X250X143.42 0.983 → 0.983 | 0.979 → 0.979 | none; 8 panel zones 0.926 → 0.946 (PZ, as at 8b2ffbf) |
| published | IN_Ex18 | COMPLETE → COMPLETE → COMPLETE | floor-NPB750X270X174.54 0.889 → 0.889 | 0.930 → 0.930 | none; 6 panel zones 0.932 → 0.923 (PZ, as at 8b2ffbf) |

Follow-up 3 in short:
- **(b), G:** every Section 12 class-gate failure of 8b2ffbf is gone. That is 52 + 88 rows in the PEB sandbox IN_Ex2 / Ex4
  and 52 + 66 in the published ones; all were wind records on D-T11's axial row. The published IN_Ex2 is COMPLETE
  again, and the published IN_Ex4 is back to main's 4 open items (its corner posts). No gate fails at the head.
- **(a), SW:** the side walls load the columns and posts on the gables under the across-ridge wind and on the eave
  walls under the along-ridge wind:
  - the PEB corner posts and gable corner columns rise 5–20 %: IN_Ex2 1.085 → 1.285; IN_Ex1 / Ex5 WI200X160X12X4
    0.965 → 1.133 / 1.158; published IN_Ex1 / Ex3 / Ex4 / Ex5 posts to 1.450 / 1.371 / 1.359 / 1.473 (+5 to +7 %);
  - IN_Ex7 newly fails (WPB600 end-frame columns 1.154);
  - smaller moves on IN_Ex8, IN_Ex10, IN_Ex21 (its corner columns 0.731 → 0.815, a minor-axis moment of 12.4 kN·m
    from the gable's suction) and the PEB bases (+0.3 to +0.8 %).
  - The IN_Ex3 / Ex4 sandbox corner posts stay at 1.178 / 1.242: their governing case is still the along-ridge wind
    on their own gable (N + My on D-T11's axial row), which the side walls do not change.
- **R-1:** no row moves. The Section 12 path's PEB Pd is lower now; the largest PEB 12.5.1 trigger P/Pd is 0.16 (the
  IN_Ex3 sandbox), under 0.4, so no 12.5.1.1 row switches on.

Reading it (the moves of rounds 1–2, up to 8b2ffbf; follow-up 3's are above):
- **IN_Ex6–Ex20 and the units** kept their status and their worst ratios up to 8b2ffbf (at the head, IN_Ex7 fails on
  the side walls, above).
  - The moves above 0.5 % are IN_Ex7's NPB750 crane column (A, then R1), the published IN_Ex2 canopy beam (A) and
    the IN_Ex12 / IN_Ex18 panel zones (PZ).
  - Several gravity columns and one floor beam move by 0.01–0.6 %: IN_Ex12 WPB300X300X117.03 0.8212 → 0.8233,
    IN_Ex13 WPB300X300X88.34 0.9567 → 0.9579, IN_Ex15 floor NPB750X270X145.29 0.6058 → 0.6094 (finding 4: an in-span
    hogging case), and IN_Ex15 / Ex16 / Ex18 / Ex19-stem box and WPB gravity columns by 1e-4 to 1e-3.
  - No Section 12 class gate moves on these golds: their rolled and box sections stay stocky under every record's N.
    For example, IN_Ex13 SCBF column e1 is governed by a 12.2.3 record (at the head on the "generally" rows, G) and is
    still plastic.
- **The PEB golds (sandbox and published)** all failed at 8b2ffbf (at the head the published IN_Ex2 is COMPLETE again).
  - D-T11 moves the corner posts: IN_Ex3 0.977 → 1.179, IN_Ex4 1.032 → 1.243, IN_Ex2 1.060 → 1.085. These are
    welded posts with d/tw just above 42ε, carrying N and My with little Mz.
  - D-T11 also made the SMRF columns of IN_Ex2 and IN_Ex4 fail 12.11.3.1 "plastic or compact" at 8b2ffbf; the lead's
    ruling on open point 2 (G) clears them all:
    - IN_Ex2 WI725X230X22X14 has d/tw 48.6 against 42ε = 36.6. Its interior columns are on the axial row in most
      records.
    - IN_Ex4 WI552X250X20X14 has d/tw 36.6 against 36.56. It fails by a hair in 1–3 wind records where the column
      moment passes through zero.
  - R1 adds 2–4 % to the tapered columns whose webs are above 42ε: IN_Ex3 1.075 → 1.083; IN_Ex5 WI562 / WI638 /
    WI712 now over 1.0; IN_Ex1 WI788 0.967 → 0.998.
  - F5 puts the published IN_Ex1 / Ex5 knee (an 8 mm E250 doubler on a 6 mm E350 web) at 1.033.
- **IN_Ex21** stays COMPLETE (the truss is unchanged at the head).
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

## Member-wind totals: every wall, side walls included, against the hand total (follow-up 3)

For every gold with member wind (17 jobs, the IN_Ex12 gym unit included) and every pattern in both directions,
`gold/tools/wind_totals.py` builds the job's static model and sums what `static_model.member_wind_loads` applies, wall
by wall, on main e927f35 and on the branch at 0482f9a (`gold/tools/wind_totals_batch.sh`; results
`gold/results/wind_totals2/`, full table `compose_wind3.md`).

**The hand total** is IS 875-3 7.3.1 F = (Cpe − Cpi) A pd with the pattern's pressures, wall by wall:
- across the ridge: the windward and leeward eave walls (length × eave height, the outer planes of a multi-span roof)
  and the two gables as side walls;
- along the ridge: the two gables as windward and leeward walls (span × eave height + span × rise / 2 per plane) and
  the eave walls as side walls;
- a flat-roof model from its grid (width × height);
- IN_Ex9 plus its lean-to's end walls, 12 × 5 m at y = 0 and y = 30 m (60 m² on each gable face).

**Check:** every wall of every gold and pattern, 144 pattern rows × 4 walls. The branch's loaded area equals the hand
area, and its force at the pattern pd equals the hand force: the largest difference is 0.0000 %
(`compose_wind3.py`). The branch's own force differs from the pattern-pd figure only by the wind posts' own Ka
(7.2.2.1 (b)).

The table gives the Cpi + patterns of one direction (the reverse direction is the mirror, the Cpi − patterns differ
only in q). The kN figures are signed along the axis; one side wall is shown, the other is equal and opposite.

| Set | Job | Pattern (axis) | Along-wind walls, kN: main / branch / hand | One side wall, kN: branch / at the pattern pd / hand (main 0) | Areas, m²: windward / leeward / side / side (branch = hand) | Envelope residual, m² (lines) | Net side force, kN | Roof, kN: main / branch |
|---|---|---|---|---|---|---|---|---|
| MSME sandbox | IN_Ex21 | WM0+ (Y) | 117.4 / 95.4 / 95.4 | -64.2 / -64.8 / -64.8 | 234.00 / 234.00 / 137.25 / 137.25 | 4.500 (4) | 0.000 | -326.4 / -326.4 |
| MSME sandbox | IN_Ex21 | WM90+ (X) | 43.3 / 46.7 / 47.1 | -100.4 / -100.4 / -100.4 | 137.25 / 137.25 / 234.00 / 234.00 | 4.500 (4) | 0.000 | -342.0 / -342.0 |
| PEB sandbox | IN_Ex1 | WM0+ (Y) | 300.7 / 302.5 / 300.7 | -150.5 / -149.7 / -149.7 | 750.00 / 750.00 / 322.50 / 322.50 | 0.000 (6) | 0.000 | -1117.8 / -1117.8 |
| PEB sandbox | IN_Ex1 | WM90+ (X) | 108.9 / 109.5 / 108.9 | -318.4 / -316.5 / -316.5 | 322.50 / 322.50 / 750.00 / 750.00 | 0.000 (6) | -0.000 | -1081.0 / -1081.0 |
| PEB sandbox | IN_Ex2 | WM0+ (Y) | 1484.8 / 1493.4 / 1484.8 | -1268.5 / -1260.8 / -1260.8 | 1404.00 / 1404.00 / 1363.20 / 1363.20 | 0.000 (6) | 0.000 | -10836.2 / -10836.2 |
| PEB sandbox | IN_Ex2 | WM90+ (X) | 1134.7 / 1141.7 / 1134.7 | -1306.0 / -1298.5 / -1298.5 | 1363.20 / 1363.20 / 1404.00 / 1404.00 | 0.000 (6) | -0.000 | -10721.4 / -10721.4 |
| PEB sandbox | IN_Ex3 | WM0+ (Y) | 424.3 / 427.5 / 424.3 | -214.5 / -208.3 / -208.3 | 600.00 / 600.00 / 254.40 / 254.40 | 0.000 (6) | -0.000 | -1261.9 / -1261.9 |
| PEB sandbox | IN_Ex3 | WM90+ (X) | 151.5 / 156.0 / 151.5 | -450.0 / -446.7 / -446.7 | 254.40 / 254.40 / 600.00 / 600.00 | 0.000 (6) | 0.000 | -1225.4 / -1225.4 |
| PEB sandbox | IN_Ex4 | WM0+ (Y) | 922.9 / 927.8 / 922.9 | -384.0 / -381.6 / -381.6 | 945.00 / 945.00 / 337.50 / 337.50 | 0.000 (6) | 0.000 | -3267.3 / -3267.3 |
| PEB sandbox | IN_Ex4 | WM90+ (X) | 277.6 / 279.3 / 277.6 | -976.6 / -971.5 / -971.5 | 337.50 / 337.50 / 945.00 / 945.00 | 0.000 (6) | 0.000 | -3151.2 / -3151.2 |
| PEB sandbox | IN_Ex5 | WM0+ (Y) | 367.1 / 369.3 / 367.1 | -150.5 / -149.7 / -149.7 | 750.00 / 750.00 / 322.50 / 322.50 | 0.000 (6) | 0.000 | -1117.8 / -1117.8 |
| PEB sandbox | IN_Ex5 | WM90+ (X) | 108.9 / 109.5 / 108.9 | -318.4 / -316.5 / -316.5 | 322.50 / 322.50 / 750.00 / 750.00 | 0.000 (6) | -0.000 | -1081.0 / -1081.0 |
| published | IN_Ex1 | WM0+ (Y) | 300.7 / 302.5 / 300.7 | -150.5 / -149.7 / -149.7 | 750.00 / 750.00 / 322.50 / 322.50 | 0.000 (6) | 0.000 | -1117.8 / -1117.8 |
| published | IN_Ex1 | WM90+ (X) | 108.9 / 109.5 / 108.9 | -318.4 / -316.5 / -316.5 | 322.50 / 322.50 / 750.00 / 750.00 | 0.000 (6) | -0.000 | -1081.0 / -1081.0 |
| published | IN_Ex2 | WM0+ (Y) | 1481.1 / 1489.6 / 1481.1 | -1268.5 / -1260.8 / -1260.8 | 1404.00 / 1404.00 / 1363.20 / 1363.20 | 0.000 (6) | 0.000 | -10836.2 / -10836.2 |
| published | IN_Ex2 | WM90+ (X) | 1134.7 / 1141.7 / 1134.7 | -1306.0 / -1298.5 / -1298.5 | 1363.20 / 1363.20 / 1404.00 / 1404.00 | 0.000 (6) | -0.000 | -10721.4 / -10721.4 |
| published | IN_Ex3 | WM0+ (Y) | 424.3 / 427.5 / 424.3 | -214.5 / -208.3 / -208.3 | 600.00 / 600.00 / 254.40 / 254.40 | 0.000 (6) | -0.000 | -1261.9 / -1261.9 |
| published | IN_Ex3 | WM90+ (X) | 151.5 / 156.0 / 151.5 | -450.0 / -446.7 / -446.7 | 254.40 / 254.40 / 600.00 / 600.00 | 0.000 (6) | 0.000 | -1225.4 / -1225.4 |
| published | IN_Ex4 | WM0+ (Y) | 922.9 / 927.8 / 922.9 | -384.0 / -381.6 / -381.6 | 945.00 / 945.00 / 337.50 / 337.50 | 0.000 (6) | 0.000 | -3267.3 / -3267.3 |
| published | IN_Ex4 | WM90+ (X) | 277.6 / 279.3 / 277.6 | -976.6 / -971.5 / -971.5 | 337.50 / 337.50 / 945.00 / 945.00 | 0.000 (6) | 0.000 | -3151.2 / -3151.2 |
| published | IN_Ex5 | WM0+ (Y) | 367.0 / 369.2 / 367.0 | -150.5 / -149.7 / -149.7 | 750.00 / 750.00 / 322.50 / 322.50 | 0.000 (6) | 0.000 | -1117.8 / -1117.8 |
| published | IN_Ex5 | WM90+ (X) | 108.9 / 109.5 / 108.9 | -318.4 / -316.5 / -316.5 | 322.50 / 322.50 / 750.00 / 750.00 | 0.000 (6) | -0.000 | -1081.0 / -1081.0 |
| published | IN_Ex6 | WMX+ (X) | 253.2 / 253.2 / 253.2 | -164.9 / -164.9 / -164.9 | 288.00 / 288.00 / 162.00 / 162.00 | 0.000 (0) | 0.000 | -586.4 / -586.4 |
| published | IN_Ex6 | WMY+ (Y) | 121.6 / 121.6 / 121.6 | -270.2 / -270.2 / -270.2 | 162.00 / 162.00 / 288.00 / 288.00 | 0.000 (0) | -0.000 | -594.4 / -594.4 |
| published | IN_Ex7 | WM0+ (X) | 1381.9 / 1381.9 / 1381.9 | -483.7 / -483.7 / -483.7 | 828.00 / 828.00 / 241.50 / 241.50 | 0.000 (0) | 0.000 | -3190.2 / -3190.2 |
| published | IN_Ex7 | WM90+ (Y) | 322.4 / 322.4 / 322.4 | -1381.9 / -1381.9 / -1381.9 | 241.50 / 241.50 / 828.00 / 828.00 | 0.000 (0) | -0.000 | -3181.5 / -3181.5 |
| published | IN_Ex8 | WM0+ (Y) | 447.0 / 447.0 / 447.0 | -331.1 / -331.1 / -331.1 | 288.00 / 288.00 / 192.00 / 192.00 | 0.000 (0) | 0.000 | -1745.3 / -1745.3 |
| published | IN_Ex8 | WM90+ (X) | 298.0 / 298.0 / 298.0 | -496.7 / -496.7 / -496.7 | 192.00 / 192.00 / 288.00 / 288.00 | 0.000 (0) | 0.000 | -1706.3 / -1706.3 |
| published | IN_Ex9 | WM0+ (X) | 603.0 / 603.0 / 603.0 | -418.9 / -418.9 / -418.9 | 480.00 / 480.00 / 288.00 / 288.00 | 72.000 (4) | -0.000 | -2890.4 / -2890.4 |
| published | IN_Ex9 | WM90+ (Y) | 280.9 / 304.7 / 304.7 | -634.8 / -634.8 / -634.8 | 288.00 / 288.00 / 480.00 / 480.00 | 72.000 (4) | 0.000 | -2935.1 / -2935.1 |
| published | IN_Ex10 | WM0+ (Y) | 460.6 / 460.6 / 460.6 | -238.8 / -238.8 / -238.8 | 855.00 / 855.00 / 570.00 / 570.00 | 0.000 (0) | -0.000 | -2585.7 / -2585.7 |
| published | IN_Ex10 | WM90+ (X) | 307.0 / 307.0 / 307.0 | -358.2 / -358.2 / -358.2 | 570.00 / 570.00 / 855.00 / 855.00 | 0.000 (0) | 0.000 | -2693.4 / -2693.4 |
| published | IN_Ex12/unitC_gym | WM0+ (Y) | 107.0 / 107.0 / 107.0 | -83.2 / -83.2 / -83.2 | 136.00 / 136.00 / 136.00 / 136.00 | 0.000 (0) | 0.000 | -227.4 / -227.4 |
| published | IN_Ex12/unitC_gym | WM90+ (X) | 107.0 / 107.0 / 107.0 | -83.2 / -83.2 / -83.2 | 136.00 / 136.00 / 136.00 / 136.00 | 0.000 (0) | 0.000 | -202.2 / -202.2 |

Reading it:
- **Side walls.** They now carry (Cpe − Cpi) pd × their full area on every gold. Main loaded none. The two side walls
  balance in every pattern (net 0.000 kN), so no storey force changes.
- **IN_Ex21.**
  - Across the ridge the walls stay at the hand total, 95.4 kN (main 117.4: the c23c056 artefact).
  - Along the ridge they carry 46.7 kN against a hand total of 47.1. The 0.4 kN is the posts' own Ka (×0.986); at the
    pattern pd the branch is exactly 47.1. The gable is 137.25 m² with the corner triangles now loaded (envelope
    residual 4 × 1.125 m², of which the review's triangle above the posts' tops is the balancing part).
- **IN_Ex9.** Along the ridge it is now 304.7 kN (hand 304.7), against 280.9 / 271.4 on main for the two directions:
  - main left out both 36 m² gable triangles above the eave (end portals without posts; now 18 m² at each corner's
    eave node);
  - main mis-loaded the lean-to step (the hall's corner over-wide, the lean-to's end wall half unloaded; Follow-up 3,
    "A facade step").
- **The PEB golds.** The walls along the wind are 0.5–3.0 % above main = hand, from the round-1 wind-post Ka (IN_Ex3
  along the ridge +3.0 %). The side walls are 0.5–3.0 % above the pattern-pd figure for the same reason: on the gable
  the posts take the Ka of their own side-wall area (IN_Ex3 +3.0 %). Their gable residuals net to zero.
- **Roof.** Unchanged by follow-up 3: main = branch for every job and pattern.
- **Members that lost load against main:** none in follow-up 3. The only pieces with less load than on main are, as
  before, IN_Ex21's four upper gable-post pieces under the across-ridge wind (not on the long wall), and on IN_Ex9 the
  hall's corner column at the lean-to step (its 6 m toward the lean-to over the 8 m height, a wall that does not
  exist there). The PEB posts give up the part of their rectangle above the rafter, which the corner columns carry.

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

The open points of follow-ups 2 and 3 are closed by the lead's rulings:
- side walls (Follow-up 3 (a): one Cpe per wall);
- the Section 12 gates and the brace hinge (Follow-up 3 (b), Follow-up 4);
- IS 18168 Ca (Follow-up 4);
- the gust ratio (for the PEB owner);
- slender box bending (a known limit).

What remains:
1. **Merging with `fix/2026-10-third-peb-golds`** (trial merge at 711cc38, not committed): one conflict, in
   `india_connections.base_plate_design_biaxial`, where the PEB branch made the same minor-axis outline fix. Keep
   either side. The sizer has changed since (the base-outline screen, the 12.11.3.1 and Table 2 screens, the
   web-strip and member-web fy), so a fresh trial merge is advised.
2. **Gold owners re-size on this engine.**
   - Side walls now load every portal's corner columns and gable posts across the wind (the A/B above): the PEB
     corner posts, IN_Ex7's end frames.
   - The knee stiffener rows: the web doubler is at its own (E250) fy. A job with E350 doublers declares
     `knee_panel.doubler_grade`; a Section 12 joint declares `doubler_grade` in its `beam_column` spec.
   - The golds with Section 12 doublers declare no doubler grade. They are at E250 now: IN_Ex12 (48 mm, 230 MPa),
     IN_Ex16, IN_Ex18 and IN_Ex9 (20 mm, 240 MPa).
3. **The cfg band helpers** listed above, to switch to `fy_is2062` (the lead takes this list).
