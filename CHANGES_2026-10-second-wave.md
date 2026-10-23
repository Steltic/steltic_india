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

## Tests

- `tests/test_second_wave_2026_10.py` (new): headline ratios and their printing, headline.json, soil and Ta notes
  (Ex16 × 2.08 hand check), Ta formula parsing per direction, facade wording, gust factor, wind base shear row,
  across-wind wording, deck layout and the deck-span point, composite scope, framing and titles, the compliance and
  strengthening sections from fixtures, citations and the codes table, README roadmap, ridge line, assumptions,
  snow, Section 12 units, 7.11.2 reason, Table 7 row, system names, flexible-run reason, effective lengths and
  ridge height, and no US residue in any new text.

## Gold re-runs

(table below)
