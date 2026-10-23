# steltic-india — 2026-10 second wave (industry-alignment review, report-only)

Branch `fix/2026-10-second-wave`, based on main db62c44 (the first wave merged). Scope: the first-wave leftovers
and the part of the second wave that changes only what the reports say (review items 9, 12, 13, 14 and 16, plus
leftovers of the Group B / C findings). No design changes: the golds stay code-strict (owner rulings D-T1, D-T2,
D-T4, D-T7, O1 and H/240 with a brick dado are kept), soil stays Type II for Kolkata, Kochi and Guwahati, and Ex9,
Ex10, Ex12 and Ex19 stay. Every new text is in `steel_engine/report_second_wave.py`; `report_india.py` only hooks it
in. `design_pipeline.py`, `engine3d.py`, `india_is800.py`, `india_is800_s12.py`, `peb_checks.py` and `pipeline.py`
are untouched.

## The headline ratio (H1, review B_HR #4)

- The headline of every report is the **worst strength ratio** of the members (the IS 800 member resistance /
  9.3 interaction ratio). The member "D/C" used until now was the larger of the strength ratio and the IS 800
  Table 3 slenderness ratio, so Ex9's published 0.865 was the brace KL/r 155.8 against 180; its worst strength
  ratio is 0.810 (roof girder NPB600X220X154.47 under 1.5DL+1.5LL+1.5SL).
- Status block (Chapter 1): a "Headline" line (strength first, then the slenderness KL/r with its limit) and a
  "Governing ratios" table: member strength, member slenderness, Section 12 strength checks, Section 12
  slenderness limits, Section 12 width-thickness / proportioning / deformation limits, connections, secondary
  members and storey drift, each with its limit and where it occurs.
- Chapter 6 member table: separate "strength ratio" and "KL/r / limit (ratio)" columns, plus the effective lengths
  KLz / KLy the governing element was checked with.
- `design/headline.json` is written with every report (the record the site build and the gold harness read):
  `strength {dc, member, section, check, combination, clause}`, `slenderness {ratio, KL_r, limit, member,
  combination}`, `member_dc_max` (the old single figure), `section12 {strength, slenderness, detailing}`,
  `connections`, `secondary_members`, `drift`.

## Statements that move the base shear (H2, item 12)

- Every job: the soil type with its basis ("medium stiff soil (Type II) as declared in the brief: medium soil
  assumed, not from a site investigation; confirm by site investigation"), in Chapter 2 and Chapter 3, and as a
  note the Sa/g and the V_B ratio on the next softer type at the design Ta (IS 1893 6.4.2 with the 7.2.2 Table 7
  minimum, from `india_seismic.sa_over_g`). Type III would raise V_B by 1.23 where Ta is past the Type II plateau
  (Ex16, Ex18, Ex19 Y and stem, Ex20), 1.05 (Ex17 Y), 1.14 (Ex2 Y); elsewhere Ta is on both plateaus and V_B does
  not change. Designs unchanged (owner decision: Type II kept). `cfg['soil_basis']` overrides the wording.
- Moment-frame directions whose Ta is the bare-frame 7.6.2(a) formula: the facade assumption is printed (no
  masonry infill built in contact with the frame; for the PEB sheds, the brick dado is self-supporting and tied to
  the columns out of plane only) and, as a note, the 7.6.2(c) Ta = 0.09 h/√d of the same clause (the formula for a
  frame with infill, from `india_seismic.approximate_Ta`) with its Sa/g and V_B ratio: Ex16 × 2.08, Ex18 × 2.26 (X)
  / × 1.96 (Y), Ex2 Y × 1.14; Ex6, Ex7 X, Ex8, Ex9 X, Ex12 (+ units), Ex1, Ex3, Ex4, Ex5 Y × 1.00.
  `cfg['facade_basis']` overrides the wording.
- Wind: the IS 875-3 10.2 gust factor table (G per direction, f_a, β, C_f, I_h, B_s, S, E, V̄_h,d, the gust and
  static base shears, method and reference) wherever the load plan records the dynamic route (Ex15–Ex18, Ex20, Ex2,
  Ex5); the 9.1 basis where only that is recorded (Ex14, Ex19 and the stem). The first-wave wind base shear column of the
  "Governing lateral load" table is present on every job (checked on all 24 re-runs).

## Composite-deck floors (H3, item 9)

- Every job with a composite metal deck (Ex11–Ex20 and the units): Chapter 6 states that the floor beams are
  designed as bare steel to IS 800 with no composite action relied on (conservative for strength), and that
  composite action and shear connectors (IS 11384), the deck itself (as formwork and as the slab), the construction
  stage of the deck and fire protection are not designed. The steel beams' unpropped wet-concrete check (IS 800
  8.2.2), which the engine already makes, is printed with its ratio.
- The deck span is printed in the gravity table and the scope paragraph: the declared secondary / filler beam
  spacing (2.5–3.0 m on Ex11, Ex12, Ex15, Ex17–Ex20) or, with no secondaries, the full bay. A full-bay deck
  (Ex13 6.0 m, Ex14 7.5 m, Ex16 7.5 m) is a non-blocking point in the design status
  (`consistency.package_warnings`, like D-T9): the deck supplier must confirm the profile for that span (propping
  if needed) or secondary beams must be added. `cfg['deck'] = {secondary_spacing_mm | span_mm}` declares it
  explicitly; otherwise the spacing is read from the construction-stage and delegated-design records.

## Capability demonstrations (H4, item 14)

- Ex9, Ex10, Ex12 (+ units B and C) and Ex19 (+ the stem) open with their capability-demonstration title and a box
  saying what the engine shows and what Indian practice usually builds instead. Job IDs and folder names are
  unchanged. Titles and one-line descriptions for the site: `/home/claude/briefs/titles_wave2.json`
  (`report_second_wave.titles()`).

## Cost of compliance and the strengthening option (H5, item 13)

- When `<job>/compliance_comparison.json` exists, Chapter 6 prints a "Cost of compliance" section: the rows
  (design, R, steel t, kg/m², worst strength ratio, governing, status, code status), the difference, the basis
  and the source. When `<job>/strengthening_option.json` exists (IN_Ex5), it is printed inside the PV answer
  section. Schemas as in the second-wave brief; a file that cannot be read is reported, not skipped silently.

## Citations (H6, item 16)

- One style for the standards in every printed line outside the activity log: IS 875 (Part 1):1987,
  (Part 2):1987, (Part 3):2015, (Part 4):2021, (Part 5):1987; IS 2062 (Part 1):2025; IS 1893 (Part 1):2016 with
  Amendments 1 and 2; IS 875-N shorthand written as IS 875 (Part N). IS 875 (Part 1):2026 (a draft) is gone.
- IS 18168:2023 is listed in the codes table wherever its checks were evaluated. It was missing on Ex9, Ex10,
  Ex12 (+ units), Ex13, Ex14, Ex16, Ex17 and Ex18, which do not set `apply_is18168` but whose Chapter 9 carries
  IS 18168 checks.
- README: a roadmap note — BIS lists a fourth revision of IS 800 as a finalised draft (CED 7); the corpus and the
  engine's IS 800 transcriptions will be rebuilt when it is published.

## IN_Ex9 ridge (H7)

- Chapter 5 of a true-slope portal job (`roof_planes`, non-PEB: Ex9) says that the apex nodes are tied to the roof
  diaphragm along the span only, with no tie across the span at the ridge, and what holds the ridge out of plane
  (in the model: the rafters' minor-axis bending from the eaves and the pinned ridge members; in the building: the
  roof-plane bracing and the purlins tied into it). The building height reads "8.00 m to the eave, 11.00 m to the
  ridge".

## Leftovers of the review (H8)

- The design engineer's recorded assumptions (`cfg['eor_assumptions']` and found:false retrieval rows carrying
  `{value, source, verify}`) are printed in Chapter 1 for the checking engineer to confirm (Ex9 topography and
  cladding, Ex10 importance factor and map readings, Ex17 / Ex18 across-wind Cfs, Ex18 / Ex20 map readings, Ex5).
  The README already promised this.
- Snow: the load plan's snow record (zone and its basis, altitude, s0, μ, the lean-to drift μ2 and load) in
  Chapter 3 (Ex9). Wind: k3, terrain and Vb basis rows where recorded.
- Chapter 3 earthquake table: R, Sa/g and Ah per direction and the Ta formula; the IS 1893 7.2.2 / Table 7 minimum
  (ρ against (Z/2)(I/R)(Sa/g)) on every job.
- Chapter 9: Section 12 forces in kN and moments in kN·m (were N and N·mm), lengths in mm, width-thickness
  records as "b/tf 6.67, d/tw 18.89" (were Python dicts).
- Chapter 8: deformation compatibility prints the record's own reason when nothing is checked (e.g. "every column
  belongs to a lateral-load-resisting line"; "Zone II: 7.11.2 applies in Zones III-V only"), not "No non-SFRS
  member requires the check in this zone".
- Across-wind rows say "not required: IS 875-3 9.1 ..." where the load plan records that, instead of "NOT
  EVALUATED" (Ex15, Ex19 and the stem).
- A flexible-diaphragm run on a regular plan (Ex8) says why it was made (declared in the job) and that Table 5(ii)
  does not require it there.
- Chapter 2: the IS 1893 Table 9 and IS 800 Section 12 names of the declared system (e.g. "SMRF ... (IS 1893
  Table 9 (i)(d)) = SMF (IS 800 12.11)").
- "EOR" wording left in printed text (irregularity screen, across-wind basis, Ec default, assumptions) reads
  "design engineer".

Not done here (need a design or engine change, or a source outside the corpus): see the HR result file
(`/home/claude/briefs/HR_RESULT2.md`).

## Contract

- `contract/AGENT_START.md` documents the optional report-only keys `soil_basis`, `facade_basis`, `deck` and
  `report_framing` (the contract lint requires every cfg key the engine reads to be named).

## Gold harness (outside the repo)

- `/home/claude/gold/harness/run_job.py` adds to run_summary.json: `headline` (the record above), `worst_strength`,
  `worst_slenderness`, `worst_members_strength` [(strength, id, slenderness ratio, KL/r, limit)] and
  `worst_members_note`. `worst_members` is kept as it was (member D/C = the larger of the two ratios) for older
  scripts. The previous harness is saved as `/home/claude/gold/baseline_2026-10-23/run_job.py.before_second_wave`.

## Tests

- `tests/test_second_wave_2026_10.py` (new): headline ratios and their printing, headline.json, soil and Ta notes
  (Ex16 × 2.08 hand check), Ta formula parsing per direction, facade wording, gust factor, wind base shear row,
  across-wind wording, deck layout and the deck-span point, composite scope, framing and titles, the compliance and
  strengthening sections from fixtures, citations and the codes table, README roadmap, ridge line, assumptions,
  snow, Section 12 units, 7.11.2 reason, Table 7 row, system names, flexible-run reason, effective lengths and
  ridge height, and no US residue in any new text.
- Whole suite: 1,037 passed, 4 skipped (main before this branch: 1,005 passed, 4 skipped).

## Gold re-runs

Before any change the outputs of the 24 golds (run_summary.json, design/, report.html, STATUS.md, the IS 801 secondary
results) were snapshotted in `/home/claude/gold/baseline_2026-10-23/` with the md5 of every gold `cfg.py`. All 24 were
then re-run with reports and no LLM on this branch, each wrapped in `/home/claude/bin/heavy`, the five PEB jobs with
their IS 801 secondary step first (steltic_CFS_india fix/2026-10-first-wave 81e8bbe). Every run returned rc 0.

**The designs are unchanged.** For every job the member groups and sections, every member check ratio, value and
limit, the connections, the Section 12 checks, the storey drifts, the PEB members, the secondary members, the IS 801
purlin and girt results, the seismic weight, the RSA scale factors, the gates, the status and its open reasons and
the kg/m² are identical to the snapshot (compared at six decimals; one Ex13 column ratio differs by 2.5 × 10⁻¹⁰,
solver round-off). The only other differences are combination labels on checks where two combinations give exactly
the same ratio (for example 1.5DL+1.5LL and 1.5DL+1.5LL+N_X on a floor girder): the label of a tie depends on the
order the combinations are visited, not on this branch. No gold `cfg.py` was changed.

What the table shows: the headline is now the worst strength ratio. It differs from the old single member D/C only
on IN_Ex9 (0.865 was the brace KL/r 155.8 against 180; the worst strength ratio is 0.810). The new non-blocking
point (full-bay composite deck) is on Ex13, Ex14 and Ex16; it does not change their status.

| Job | Status before → after | Member D/C before (mixed) | Worst strength ratio after (member) | Slenderness KL/r / limit (ratio) | Drift D/C before → after | kg/m² before → after | New non-blocking point |
|---|---|---|---|---|---|---|---|
| IN_Ex1_PEB_factory_shed_tapered_Bengaluru | complete → complete | 0.961 | 0.961 (lateral_col-WI956X250X14X6) | 129.5 / 180 (0.719) | 0.266 → 0.266 | 34.5 → 34.5 | — |
| IN_Ex2_PEB_GradeA_warehouse_multispan_Bhiwandi | complete → complete | 0.930 | 0.930 (roof-WI500X300X25X14) | 148.8 / 180 (0.827) | 0.390 → 0.390 | 56.2 → 56.2 | — |
| IN_Ex3_PEB_crane_shed_10t_Nagpur | complete → complete | 0.849 | 0.849 (roof-WI778X220X12X6) | 129.5 / 180 (0.719) | 0.086 → 0.086 | 57.0 → 57.0 | — |
| IN_Ex4_PEB_warehouse_SMRF_Zone4_NCR | complete → complete | 0.890 | 0.890 (lateral_col-WI422X250X20X16) | 141.2 / 180 (0.784) | 0.168 → 0.168 | 63.8 → 63.8 | — |
| IN_Ex5_PEB_rooftop_solar_check_Bengaluru | partial → partial | 1.102 | 1.102 (lateral_col-WI956X250X14X6) | 129.5 / 180 (0.719) | 0.363 → 0.363 | 34.5 → 34.5 | — |
| IN_Ex6_OMRF_warehouse_mezzanine_Hyderabad | complete → complete | 0.887 | 0.887 (floor-NPB600X220X122.45) | 156.2 / 180 (0.868) | 0.301 → 0.301 | 47.6 → 47.6 | — |
| IN_Ex7_Crane_bay_OMRF_OCBF_Vizag | complete → complete | 0.953 | 0.953 (lateral_col-WPB600X300X211.92) | 146.0 / 180 (0.811) | 0.073 → 0.073 | 73.8 → 73.8 | — |
| IN_Ex8_SMF_portal_Chennai_wind | complete → complete | 0.804 | 0.804 (roof-WPB500X300X155.08) | 104.5 / 300 (0.348) | 0.046 → 0.046 | 72.1 → 72.1 | — |
| IN_Ex9_Gable_warehouse_SMF_SCBF_snow_Shimla | complete → complete | 0.865 | 0.810 (roof-NPB600X220X154.47) | 155.8 / 180 (0.865) | 0.135 → 0.135 | 52.8 → 52.8 | — |
| IN_Ex10_SCBF_bigbox_flexdiaphragm_Indore | complete → complete | 0.920 | 0.920 (roof-WPB450X300X139.76) | 159.1 / 180 (0.884) | 0.018 → 0.018 | 29.6 → 29.6 | — |
| IN_Ex11_OCBF_4levels_splitlevel_Jaipur | complete → complete | 0.947 | 0.947 (roof-NPB450X190X67.16) | 189.9 / 250 (0.759) | 0.093 → 0.093 | 42.4 → 42.4 | — |
| IN_Ex11_OCBF_4levels_splitlevel_Jaipur/units/workshop | complete → complete | 0.947 | 0.947 (roof-NPB450X190X67.16) | 187.5 / 250 (0.750) | 0.018 → 0.018 | 50.0 → 50.0 | — |
| IN_Ex12_SMF_3levels_Zplan_school_Chandigarh | complete → complete | 0.984 | 0.984 (floor-NPB700X250X143.42) | 220.8 / 250 (0.883) | 0.808 → 0.808 | 63.8 → 63.8 | — |
| IN_Ex12_SMF_3levels_Zplan_school_Chandigarh/unitB_link | complete → complete | 0.984 | 0.984 (floor-NPB700X250X143.42) | 220.8 / 250 (0.883) | 0.339 → 0.339 | 64.5 → 64.5 | — |
| IN_Ex12_SMF_3levels_Zplan_school_Chandigarh/unitC_gym | complete → complete | 0.960 | 0.960 (roof-NPB700X250X143.42) | 201.9 / 250 (0.808) | 0.090 → 0.090 | 116.4 → 116.4 | — |
| IN_Ex13_SCBF_5levels_Delhi | complete → complete | 0.970 | 0.970 (floor-NPB450X190X67.16) | 138.8 / 180 (0.771) | 0.067 → 0.067 | 58.1 → 58.1 | deck span |
| IN_Ex14_SCBF_hospital_Kolkata | complete → complete | 0.864 | 0.864 (floor-NPB450X190X92.37) | 126.4 / 180 (0.702) | 0.153 → 0.153 | 69.4 → 69.4 | deck span |
| IN_Ex15_EBF_8levels_Lplan_Pune | complete → complete | 0.999 | 0.999 (floor-WPB260X260X114.4) | 225.0 / 300 (0.750) | 0.326 → 0.326 | 66.2 → 66.2 | — |
| IN_Ex16_SMF_office_Mumbai | complete → complete | 0.774 | 0.774 (roof-NPB500X200X90.69) | 187.5 / 250 (0.750) | 0.836 → 0.836 | 74.5 → 74.5 | deck span |
| IN_Ex17_SCBF_10levels_Ahmedabad | complete → complete | 0.932 | 0.932 (floor-NPB750X270X145.29) | 220.8 / 250 (0.883) | 0.474 → 0.474 | 62.4 → 62.4 | — |
| IN_Ex18_SMF_podium_11levels_Kochi | complete → complete | 0.889 | 0.889 (floor-NPB750X270X174.54) | 214.8 / 250 (0.859) | 0.635 → 0.635 | 79.9 → 79.9 | — |
| IN_Ex19_EBF_12levels_Tplan_Guwahati | complete → complete | 0.972 | 0.972 (floor-WPB400X300X155.26) | 206.8 / 250 (0.827) | 0.362 → 0.362 | 88.0 → 88.0 | — |
| IN_Ex19_EBF_12levels_Tplan_Guwahati/units/stem | complete → complete | 0.947 | 0.947 (floor-WPB340X300X134.16) | 206.8 / 250 (0.827) | 0.276 → 0.276 | 105.3 → 105.3 | — |
| IN_Ex20_SCBF_18levels_slender_Noida | complete → complete | 0.967 | 0.967 (floor-WPB550X300X199.44) | 213.8 / 250 (0.855) | 0.341 → 0.341 | 88.3 → 88.3 | — |

Comparison script: `compare2.py` in the HR agent scratchpad; report scan: `scan2.py` (headline, wind base shear row, gust
factor, composite scope, deck point, framing, ridge, assumptions, Table 7, base-shear statements, IS 18168 row,
US residue 0 and no old citation forms on all 24 reports).
