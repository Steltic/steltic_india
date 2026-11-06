# steltic-india — 2026-10 third wave: Indian section families for IN_Ex7 … IN_Ex20 (agent SECT)

Branch `fix/2026-10-third-sections`, based on main 44b74de. On the lead's instruction it merges
`fix/2026-10-column-span-moment` (28831f8: IS 800 Table 18 uniform-loading Cm / CmLT for columns with a span load,
both signs, end-moment-only connection demands, 17-field records). The provisional cherry-pick of the first cut
(2cb42ff) was reverted first. It then merges origin/main three times: c4bf49b (PR #29 span fix, PR #30), 56909e3
(PR #31 MSME shed, PR #32 engine-check fix) and e45a65d (PR #33: the consistency fix and each group's strength line
printed from its worst-strength element; no design result moves). Every job was sized, and every sized design verified, against the merged
checks.

Two passes (coordinator, 2026-11-06):
- **First pass** on main as of PR #30. Not published.
- **Final pass** on main 56909e3 with the engine-check fix (`CHANGES_2026-11-engine-checks.md`). It starts from each
  job's first-pass design (IN_Ex19 from the published one) and re-sizes what fails, plus the re-size this brief asks
  for. These are the results below. Each move is tagged with the fix behind it, using the tags of
  `CHANGES_2026-11-engine-checks.md` (A, B, R1, D-T11, G, PZ, SW ...); "re-size" marks a move the sizer made for
  weight with nothing failing.

Scope (owner decisions of 2026-10-30):
- re-size IN_Ex7 … IN_Ex20 and their units (Ex11 workshop, Ex12 unit B and unit C, Ex19 stem) to Indian section
  families: IS 808 MB / WB / HB, MC, ISA and IS 1161 CHS by default, and E350 for heavy columns;
- report before and after kg/m² for every job;
- IN_Ex6 and the cold-formed jobs keep their sections.

The golds stay code-strict under the existing rulings (D-T1, D-T2, D-T4, D-T5, D-T7, O1, H/240 with a brick dado,
D8).

## Brace families (owner confirmation, 2026-11-01)

- **OCBF jobs (IN_Ex7, IN_Ex11 and the Ex11 workshop): IS 1161 CHS braces** (YSt 310, hot-finished seamless).
- **SCBF and EBF jobs: IS 808 HB / WB / MB braces in IS 2062 E250 B0.** IS 1161 tubes cannot be used there:
  - IS 800:2007 12.8.2.1 requires the braces of a special concentrically braced frame to be IS 2062 E250B steel;
  - where IS 18168:2023 governs (Zones III–V), 5.2(b) admits other steels only with an elongation of at least 22 %,
    and IS 1161 Table 2 gives 10–20 % (YSt 210 20 %, YSt 240 17 %, YSt 310 14 %, YSt 355 10 %);
  - the engine already enforces this (`india_is800_s12.material_gate`).
- The CHANGES tables and the reports state this basis.

## P3 (HR side): tied combinations give the same label run to run

- `design_pipeline._top_records` used to rebuild the per-element combination dict from a Python set, so its order
  followed the hash seed.
  - Fix: it now keeps the order of the combination list. On a tie, the first combination in that list governs.
  - Proof: IN_Ex13 run with PYTHONHASHSEED 1 and 2 gives byte-identical `calc_package.json`, csv and md files and
    `report.html`. Before the fix there were 86 differences.
  - The printed tie labels can differ from the published golds; no ratio changes.
  - Since PR #32 (merged here at 56909e3), the member checks see every combination in the order of the records
    (`design_pipeline.member_check_records`; `_top_records` is now an alias), so the property holds by
    construction. The merge took main's version of that block.
- Test: `tests/test_third_wave_sections.py`, run in subprocesses with four hash seeds.
- **Shared frame builder (`frame_build.py`, lead request 2026-11-01, found by the CFS agent).** The moment lines
  were read from a set, so a column on both an X and a Y moment line took the orientation of whichever line the hash
  seed put first. With main's builder, seeds 0 and 7 gave Y and seeds 1, 2, 3 and 11 gave X for the same corner
  column. The lines are now kept in their declared order.
  - **Column orientation rule (`col_strong`):** the strong axis resists the direction of the first declared moment
    line through the column. Else it resists the direction of the first braced (X or EBF) bay that uses the column,
    in the order listed (storey 1 upwards). Else it uses `default_strong`, which defaults to X. This is the rule the
    CFS runner now uses.
  - Test: the orientation of every column of a 3 × 2 plan, with a corner on two moment lines, is the same for five
    hash seeds and follows the rule.
  - No HR gold uses `frame_build`, so no gold changes.

## The general sizer (`steel_engine/hr_autosize.py`, new)

- A job is sizable when its cfg.py declares these at the top level (the job uses `SECTIONS[...]` wherever it picks a
  section):
  - `SECTIONS` (member group → section label);
  - `SIZING_GROUPS` (role, families, built-up fallback, notes);
  - `GRADE_BY_SECTION`;
  - `CONNECTIONS` (the declared connection geometry, a literal).
- The sizer rewrites only those literals (AST spans, so the comments are kept).
- **Order of preference** per group:
  1. rolled E250 of the group's families (lightest first);
  2. rolled E350 (columns);
  3. a built-up welded box (columns) or welded plate I (beams, links), from IS 2062 plates. The golds' label
     convention is kept: `BOX<D>X<B>X<t>`, `WI<D>X<bf>X<tf>X<tw>`.
- **Loop:**
  1. A probe maps each element to its group: one execution of the cfg with a clone label per group.
  2. A full pipeline run without the report, in a child process with PYTHONHASHSEED 0. It captures the exact
     member-check inputs of every element and the Section 12 model data.
  3. Local sizing with the forces frozen. Every element must pass the IS 800 member checks
     (`india_is800.member_check_is800`) within the group's margin. The group's own Section 12 rows (IS 18168
     Table 2, brace slenderness and class, IS 18168 7.2 column KL/r, link rules) must also pass. A proportional
     drift / sway / deflection predictor keeps the stiffness the last run needed.
  4. The whole proposal goes through the engine's Section 12 checks with the frozen forces. Any group that a
     member- or joint-level row fails (SCWB, for example) is stepped up.
  5. The connections are re-designed for the new sections:
     - fin plates (one or two bolt lines, then double fins, then a sand-blasted faying surface) and brace ends
       (slotted CHS, or rolled I with CJP flange welds), checked with the engine's own capacity functions;
     - cover-plate and CJP moment joints from the section;
     - base plates and splices adapted from the previous design, then stepped up from the failing rows of the
       verification run (plate, bearing, anchors, embedment, stiffeners; splice bolts and plates; panel-zone
       doublers, cover plates).
  6. A full verification run. A failure tightens the margin of the failing group or steps up the failing
     connection.
  7. The loop stops when a passing design no longer changes. The lightest passing design in the target families
     is kept.
- **One rule with the engine.**
  - The worker records the exact (member, combination forces) of every call the pipeline makes to
    `india_is800.member_check_is800` for an element, and the local check evaluates exactly those. Whatever
    combination filter, web-class axial force or fy band the engine applies, the sizer sees the same.
  - The sizer's plate fy is the engine's IS 2062:2025 band function (`india_is800.fy_is2062`: E250 is 240 MPa
    above 16 mm). It no longer has its own table.
- **Details the local step uses so that it predicts the full run:**
  - every member-check call of an element is kept. The IS 1893 7.11.2 check of a gravity column calls the member
    check a second time for the same element; before, that call replaced the strength check's forces;
  - declared secondary members (`cfg['secondary_members']`) whose section is a sized group, such as the IN_Ex9 lean-to
    roof beam under snow drift and ponding, are checked with the engine's own functions;
  - brace ends are designed under the braced part of a combined system (`SMRF+SCBF` → SCBF), as
    `section12_checks` checks them;
  - since the engine checks every combination with both signs (fix A), an element of a tall job carries 100+
    combinations. An element with more than 48 is predicted on a short list:
    - the 24 with the largest linear stress index |P|/A + |Mz|/Zz + |My|/Zy at its current section;
    - plus the two largest of each force, of each sign.

    The list is computed once per run, and the full run still checks every combination. On IN_Ex19, the local step
    had grown past 40 minutes a pass with 93–141 combinations per element. On 60 IN_Ex19 elements the short list gives
    the same ratio as the full one;
  - two more changes for speed, neither of which alters a result:
    - a candidate is checked on its group's elements most loaded first, so a failing candidate is rejected early;
    - the member ratios are memoised per (element, label, grade), and Section 12 candidates use a copy of the model
      data that shares the forces (a deep copy of the IN_Ex19 data took 2.8 s).
- **Groups without frame elements** are sized from their own checks: the IN_Ex7 gantry girder
  (`design_pipeline.gantry_girder_checks`, with its MC cap) and groups used only by declared secondary members.
  No IS 808 MB / WB section passes the IN_Ex7 gantry (WB600 × 145 kg/m: vertical deflection 1.40 of the Table 6
  limit), so welded plate girders are its fallback. The deflection under the static wheel loads scales with 1 / Ix
  and screens the candidates.
- **Torsional irregularity (IS 1893 Table 5(i), Amd 2).** The worker records Δmax / Δavg for each loading direction.
  When a run is torsionally irregular (above 1.2), the frames of the other plan direction and the lateral columns
  keep at least their stiffness × (ratio − 1) / (1.164 − 1) from then on, since ratio − 1 grows with K_d / K_θ.
  This was found on IN_Ex9: lighter portal frames raised the ratio under Y loading from 1.14 to 1.24, and the
  torsional mode became the second mode.
- **Brace fallback.** SCBF and EBF braces (IS 808 families, E250 B0) fall back to a compact welded I made from
  IS 2062 E250 B0 plates when no rolled section passes. On IN_Ex10 (17.8 m X-braces), the rolled sections with
  enough radius of gyration fail the IS 18168 Table 2 brace flange limit, and the compact ones fail KL/r. CHS
  (OCBF) braces have no built-up fallback.
- **Connections that drive a member size.**
  - A beam whose end shear connection (V + N resultant of a collector) does not fit its section is stepped up. The
    demand is kept for later passes (IN_Ex14, IN_Ex20).
  - Beam groups that share a label get the connection of the largest demand (IN_Ex18).
  - Moment-joint web plates are designed for the IS 800 12.11.2.2 joint shear (1.2DL + 0.5LL + 2 × 1.2 Mp / L') of
    the new beam, and are stepped up from failing rows (IN_Ex16).
  - Panel-zone doublers declare their grade (`doubler_grade`; the engine checks a doubler at its own grade, E250
    when none is declared). The grade is E350 B0 when every column that the label's beams frame into is E350, since
    the doubler is the same plate as the column web it is welded to. Otherwise it is E250 B0. The doubler thickness
    is stepped up from the engine's own panel-zone rows. A design written to a cfg states every doubler's grade:
    a design kept from an earlier pass gets E250 B0, the grade its verified run checked it at.
- **A label that fails Table 3 slenderness in its own full run** is barred for its group. The limit depends on
  whether the member carries compression, which the frozen forces cannot show. On the IN_Ex12 gym, a roof beam
  picks up axial force only in its own run.
- **Global checks the local step cannot see** are answered with stiffness requirements that are kept from then on:
  - IS 1893 Table 6(i) soft storey (K_i < K_i+1, which drops the drift limit to 0.2 %): the columns of that storey
    keep their stiffness × (K_i+1 / K_i) / 0.97;
  - IS 1893 Table 6(vii) modal mass (first three translational modes below 65 % in a direction): the torsional
    system of that direction is stiffened by 25 %;
  - IS 875-3 9.1(b) first-mode period above 1 s, which calls for a dynamic wind response the job does not declare:
    the frames of that direction keep stiffness × (T / 0.97)²;
  - the drift factor is capped at 1.35 per pass, so a stepped limit is answered where it arises.
- **Section 12 rows that the full run fails** although the frozen forces passed them get a margin for their group
  (−0.04 per pass, down to 0.80). Example: the IS 18168 12.3.2.2 EBF brace axial force at the link overstrength.
  EBF brace ends are designed for the brace's expected strength, 1.1 Ry fy Ag (IS 18168 10.4.1a), which caps the
  connection force.
- **Bases at the thickness limit.** A fixed base whose plate has reached 150 mm and still fails in bending gets gusset
  stiffeners (IS 800 7.4.2, the IN_Ex12 detail), which are then stepped up by their ratio. Designed bases and
  splices are cached per column label, so a label that comes back keeps its stepped-up base.
- **Storey stiffness and capacity coupling.**
  - Lateral column groups over storey ranges (`_1_3` / `_4_6`, `_0` / `_1`, `_lo` / `_hi`) stay monotone up the
    height in their own stiffness measure (Ix for moment-frame columns, A for braced-frame columns). Where the
    sizing made a lower group less stiff, that group is sized again with the upper group's value as its minimum.
    It never takes a section that fails its own checks. IS 1893 Table 6(i) requires this (IN_Ex16: 58.19 kg/m²
    after the rule, against a spiral above 90 kg/m² before it).
  - A soft braced storey is stiffened through its braces; a soft moment-frame storey through its columns.
  - IS 1893 Table 6(vii), Zones IV and V: when Tx and Ty are less than 10 % apart, the frames of the stiffer
    direction are stiffened further (the IN_Ex12 gym).
  - IS 18168 7.2 column KL/r, where K follows the beam-to-column stiffness ratio (IS 800 Annex D, the IN_Ex12 gym),
    is answered first by stiffer moment-frame beams. Stepping up the column raises its own share of the stiffness,
    and K with it.
  - Section 12 margins are kept per group and row kind, so a KL/r failure no longer tightens the Table 2 rows.
- **EBF links.** Every brace, beam outside the link, column and base is designed for the link overstrength
  1.1 Ry Vp (IS 18168 12.3.2.2 / 12.3.4.5). On IN_Ex15, links made larger for stiffness had raised it to 4.96. So:
  - links are sized for their shear and the IS 18168 link rules only, and get no stiffness step-ups;
  - they are held after the first two passes. Their own failing members, or an end connection that does not fit,
    release them, and the step-up is the smallest link that takes the connection;
  - among the passing candidates of the lightest passing link's tier (rolled stays rolled), within 1.3 × its mass,
    the link with the least web shear strength Vp = 0.6 fy (d − 2 tf) tw is taken.
- **Beam-end fin plates with three or four bolt lines** are tried only when no one- or two-line plate (single or
  double fin) takes the demand. This is the published IN_Ex19 collector-fin detail: 4 lines × 3 rows of M24 in
  double shear. Before this, the IN_Ex19 link beams were deepened to fit two lines, which raised Vp and with it the
  whole capacity-design chain.
- **Base gussets** stay within the IS 800 Table 2 outstand limit (h / t ≤ 13.6 ε). Past it, one more gusset is added
  on each face, up to 6.
- **Unused groups.** Groups that no member of the model takes (IN_Ex11 corner and perimeter columns: every corner
  column is braced) are left out of the eligibility test and marked `unused` in `SIZING_GROUPS`.
- **Preflight** (`preflight.chs_brace_grade_declared`): CHS braces are declared by either the
  (`brace_grade`, `brace_process`) or the (`tube_grade`, `tube_process`) pair. The member grade lookup takes the tube
  pair first. IN_Ex11 keeps `brace_grade` for rolled braces and declares YSt 310 / HFS as the tube pair.
- **Fixed column bases on a new column** (no stiffeners) are laid out again as a perimeter ring of anchors (the
  IN_Ex8 detail) for the new column: plate = column + 2 × projection, n anchors on each face, edge 1.7 d0
  (IS 800 10.2.4.2), pitch ≥ 2.5 d (10.2.2). They are then stepped up from the failing rows of the verification run:
  plate thickness up to 150 mm, anchor number and then diameter, bearing projection, embedment.
  - Pinned bases keep their projections. When the plate is no longer square they get the minor-axis anchor pattern
    (`f_y_mm`, `n_tension_y`) that `base_plate_design_biaxial` needs for My.
  - A base note that states the plate and anchors (IN_Ex14) and the bond sentence of an embedment record ("bond
    length 600 mm … = 79 kN per M30 anchor") are re-stated from the new geometry.
- **Mass:** the engine's take-off of the modelled members (`design/takeoff.json`). Connections are not in the
  kg/m², as in every hot-rolled gold.
- **CLI:**
  - `python steel_engine/hr_autosize.py size <job> --work <dir>` (resumable from `state.json`);
  - `python steel_engine/hr_autosize.py write <job> --work <dir>`.

## Migration of the gold cfgs (sandbox tool, not in the repo)

- Every job cfg was moved to the sizable format by a token-level rewrite: label literals became `SECTIONS["group"]`,
  and the hand-built `cfg["connections"]` became the `CONNECTIONS` literal taken from the gold run's
  `design/cfg_snapshot.json`.
- Before any sizing, each migrated cfg was re-run against the original gold cfg on this branch (`--no-report`,
  PYTHONHASHSEED 0). Results:
  - 17 of 18 calc packages are identical;
  - IN_Ex7 differs only in the gantry girder's capped-flange properties: they are now computed from the IS 808
    properties (Iy 1.0763e8, Zpy 9.858e5) instead of the gold's rounded hand values (1.08e8, 9.86e5), and the
    gantry ratio moves by 2.7e-5.

## Handoff P8

- **IN_Ex7 eave struts.** They are sized as struts (role `strut`): axial force of the longitudinal load path plus
  self weight, IS 800 Table 3 KL/r.
- **IN_Ex18 wind limits.** The gold's limits are the IS 800:2007 Table 6 rows for other buildings, lateral, wind:
  building with brittle cladding Height/500, inter-storey drift storey height/300 (corpus, IS 800 p. 31). The
  podium office facade (glazing and masonry) is brittle cladding. The basis now prints with the wind limits
  (`cfg['cladding_basis']`).
- **IN_Ex20 wind limits: corrected.** The cfg declared no cladding class, so the engine applied the elastic-cladding
  row, Height/300. An 18-storey office facade (glazed curtain wall and panels) is brittle cladding, so the limit is
  now Height/500, with storey height/300 for the inter-storey drift. The basis is printed. The design status was
  unchanged before re-sizing (wind top ratios 0.35 / 0.52).
- **IN_Ex20 context and fire.** Two new boxes print after the framing box (`report_second_wave.context_html`):
  - a "Practice context" box: an 18-storey office of this slenderness would usually have an RC core or frame; here
    the steel SCBF is the only lateral system, to show the checks a slender braced tower needs;
  - a "Fire resistance" box: the design is at ambient temperature. The fire resistance level is set under IS 800:2007
    16.2 (as prescribed in IS 1641 / 1642 / 1643, or the building specifications or city ordinance; IS 1641–1643 and
    the National Building Code are not in the corpus). The protection must give a period of structural adequacy at
    least equal to it (16.1.1). Fire protection is not in the steel quantities.
- **IN_Ex7 gable triangles (engine review, 2026-11-06).** The rafters are modelled flat at the eave, so the wall
  scan loaded each gable only up to the eave (241.5 of 252.5 m²). Each 11.03 m² triangle above the eave is now added
  in the cfg as member-wind nodal loads at the corner columns' eave nodes, half per corner. This is the engine's own
  rule for a sloping gable with no posts. The pressures are the pattern's own: windward / leeward gable along the
  ridge, side wall across it. The roof slope is not modelled. The job's SOLUTION.md records this.
- **IN_Ex9 lean-to.** Not modelled as a part level: the engine has no part-level model. The IS 1893 Table 6 screens
  read consecutive levels as storeys. The second-wave note stays, and the flags' requirements stay applied (RSA and
  the 0.2 % drift limit), which is conservative.

## Lead request (2026-11-01): raw dict in the IN_Ex17 report

- The design-engineer assumptions table printed an across-wind value recorded per direction as
  `{"X": 0.002, "Y": 0.002}`. `report_second_wave.value_words` now prints "0.002 (X) and 0.002 (Y)" (lists read
  "a, b and c").
- `report_public.leaks` has a new kind, `raw dict` (a quoted key followed by a colon). Page `<style>` and `<script>`
  blocks are not scanned.
- A scan of the 24 published reports finds exactly that one row (IN_Ex17).

## Results

Final pass on main 56909e3 (PR #31 MSME, PR #32 engine-check fix); the final runs and reports on main e45a65d
(PR #33). Every job was run on the SECT gold copies
(`/home/claude/wt/SECT/gold/jobs_hr`) with PYTHONHASHSEED 0, and its report built. "Old" is the published gold as
published (`/home/claude/gold/jobs_hr`). kg/m² is the engine's take-off of the analysis members per m² of floor;
connections are not included.

| Job | kg/m² old → new | change | worst strength ratio old → new (governing, new) | drift / wind ratio, new | status old → new |
|---|---|---|---|---|---|
| IN_Ex7 | 73.79 → 64.90 | -12.0 % | 0.953 → 0.945 (lateral_col-BOX500X500X14, IS 800 9.3 interaction / mem) | 0.141 / 0.712 | complete → complete |
| IN_Ex8 | 72.06 → 55.56 | -22.9 % | 0.804 → 0.861 (roof-WI550X275X18X14, IS 800 9.3 interaction / mem) | 0.084 / 0.261 | complete → complete |
| IN_Ex9 | 52.81 → 74.76 | +41.6 % | 0.810 → 0.811 (roof-WI500X325X22X12, IS 800 9.3 interaction / mem) | 0.062 / 0.073 | complete → complete |
| IN_Ex10 | 29.56 → 26.33 | -10.9 % | 0.920 → 0.935 (roof-WI300X175X12X8, IS 800 9.3 interaction / mem) | 0.020 / 0.014 | complete → complete |
| IN_Ex11 | 42.36 → 31.92 | -24.6 % | 0.947 → 0.943 (gravity_col-HB250, IS 800 9.3 interaction / mem) | 0.341 / 0.096 | complete → complete |
| IN_Ex11 workshop | 50.01 → 35.28 | -29.5 % | 0.947 → 0.935 (floor-WB600, IS 800 9.3 interaction / mem) | 0.043 / 0.056 | complete → complete |
| IN_Ex12 | 63.79 → 54.84 | -14.0 % | 0.984 → 0.941 (floor-WI800X300X16X8, IS 800 9.3 interaction / mem) | 0.892 / 0.220 | complete → complete |
| IN_Ex12 unitB_link | 64.52 → 50.08 | -22.4 % | 0.984 → 0.941 (floor-WI800X300X16X8, IS 800 9.3 interaction / mem) | 0.726 / 0.164 | complete → complete |
| IN_Ex12 unitC_gym | 116.36 → 112.55 | -3.3 % | 0.960 → 0.736 (roof-WI1000X225X16X10, IS 800 9.3 interaction / mem) | 0.083 / 0.083 | complete → complete |
| IN_Ex13 | 58.07 → 73.76 | +27.0 % | 0.970 → 0.949 (roof-MB300, IS 800 9.3 interaction / mem) | 0.040 / 0.008 | complete → complete |
| IN_Ex14 | 69.43 → 51.75 | -25.5 % | 0.864 → 0.975 (brace-WI250X250X16X8, IS 800 9.3 interaction / mem) | 0.233 / 0.039 | complete → complete |
| IN_Ex15 | 66.20 → 54.99 | -16.9 % | 0.999 → 0.945 (floor-WI550X325X22X14, IS 800 9.3 interaction / mem) | 0.300 / 0.064 | complete → complete |
| IN_Ex16 | 74.49 → 58.19 | -21.9 % | 0.774 → 0.937 (floor-WI550X225X18X14, IS 800 9.3 interaction / mem) | 0.848 / 0.784 | complete → complete |
| IN_Ex17 | 62.43 → 50.72 | -18.8 % | 0.932 → 0.945 (gravity_col-BOX350X350X10, IS 800 9.3 interaction / mem) | 0.536 / 0.154 | complete → complete |
| IN_Ex18 | 79.91 → 82.70 | +3.5 % | 0.889 → 0.918 (gravity_col-WB600X145.06, IS 800 9.3 interaction / mem) | 0.897 / 0.542 | complete → complete |
| IN_Ex19 | 87.98 → 87.98 | +0.0 % | 0.972 → 0.972 (floor-WPB400X300X155.26, IS 800 9.3 interaction / mem) | 0.362 / 0.080 | complete → complete |
| IN_Ex19 stem | 105.29 → 79.68 | -24.3 % | 0.947 → 0.983 (floor-WI550X275X18X14, IS 800 9.3 interaction / mem) | 0.332 / 0.137 | complete → complete |
| IN_Ex20 | 88.29 → 91.00 | +3.1 % | 0.967 → 0.942 (lateral_col-BOX250X250X22, IS 800 9.3 interaction / mem) | 0.307 / 0.470 | complete → complete |

Reading the table:
- **Every job and unit is COMPLETE with 0 reasons** on the fixed engine.
- **IN_Ex6** keeps its sections. Its cfg now takes `fy_is2062` and it stays COMPLETE.
- **Lighter:** the Indian families save weight on most jobs, between 3 % and 30 %.
- **Heavier:**
  - IN_Ex9 (+41.6 %): the SMF portal columns become welded boxes, BOX600X600X32 in place of WPB600X300X211.92. No
    IS 808 rolled section passed the SMF Table 2 limits, the IS 18168 7.2 column KL/r and the torsion and
    mode-separation checks of this Zone IV shed together. The lean-to columns go to WB600 sections.
  - IN_Ex13 (+27.0 %): the SCBF braces. The lightest IS 808 rolled E250 brace that meets the IS 18168 brace limits
    (owner decision 1) is HB450X92.19, in place of WPB200X200X50.92, in every bay and storey.
  - IN_Ex18 (+3.5 %) and IN_Ex20 (+3.1 %).
- **IN_Ex19**: see below.

**Final-pass moves.** Each job's SOLUTION.md lists its own moves under "Final pass on the fixed engine". Tags are those
of `CHANGES_2026-11-engine-checks.md`.
- Moved for an engine fix:
  - IN_Ex8 rafter (A: the hogging extreme of the uplift combination, 0.895 → 1.107);
  - IN_Ex10 braced-bay columns (B, with SW and R1: 0.873 → 1.114);
  - IN_Ex14 storey 6–8 braced-bay columns and IN_Ex20 cl_5 / ch_5 (G: SCBF columns plastic in the hinge state of
    the earthquake combinations, 4 and 6 rows). On IN_Ex20 the monotone-stack and soft-storey rules carry the move
    down to cl_4 / cl_3 and brace_1.
- Moved for weight, with nothing failing (re-size): IN_Ex12, IN_Ex14 (beams and braces), IN_Ex15 and the IN_Ex19
  stem, through the least-overstrength link rule and the three- or four-line fin plates.
- Moved for a connection that cannot fit: the IN_Ex8 eave strut WB150 → MB225 (a sizer rule, not an engine move).
- Rose but still pass: IN_Ex7 end-frame columns 0.687 → 0.928 (SW, with the gable triangle); gravity WB600 columns of
  IN_Ex17 / Ex18 / Ex19 stem (R1); the IN_Ex8 ordinary frame's roof 0.743 → 0.988 (B / R1).
- The other jobs pass on the fixed engine as sized in the first pass.

**Panel-zone doublers.** Every doubler states its grade.
- IN_Ex12: E350 B0 (all three doubler specs sit on E350 box columns).
- IN_Ex9, IN_Ex12 unit B / unit C, IN_Ex16 and IN_Ex18: E250 B0. They pass at their own grade (PZ).

**Gold cfg helpers.** The hand-coded IS 2062 bands now call `fy_is2062` (sandbox tool `tools/fy_helpers.py`):
- IN_Ex6 (1 helper), IN_Ex8 (2) and its ordinary-frame copy (2), IN_Ex11 (1) and the workshop (1);
- IN_Ex14 (1), IN_Ex15 (2), IN_Ex16 (5), IN_Ex17 (4), IN_Ex18 (3), IN_Ex20 (1);
- IN_Ex19 (3) and the stem (3).

No hand-coded band is left in Ex6–Ex20. The IN_Ex13 gusset literal (20 mm at 240) is inside the band.

**IN_Ex8 cost of compliance** (`compliance_comparison.json`): SMRF 55.56 kg/m² against an ordinary frame at 41.85, a
difference of 13.71 kg/m² (+32.8 %). Wind governs the shed.

**Reports.** The leak scan (`report_public.leaks`) finds nothing in the 19 SECT reports (IN_Ex6–Ex20 and the four
units). The published set has one hit, the IN_Ex17 raw dict, which is fixed here.

**HR suite** (this branch, merged main e45a65d): (pending the last run).
