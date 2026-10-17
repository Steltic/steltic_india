# steltic-india — 2026-10 first wave (industry-alignment review)

Branch `fix/2026-10-first-wave`, based on main e340df8. Scope: items 1–8 and 11 of the 2026-10 review of the published
India examples against Indian practice. This repo carries items 2–8; item 1 (nonlinear verdicts) is in
steltic_nonlinear_india and item 11 (thin cold-formed sections) in steltic_CFS_india. Owner decisions for this wave:
the golds stay code-strict (the owner rulings D-T1, D-T2, D-T4, D-T7, O1 and H/240 with a brick dado are kept);
lighter readings are switches for a separate variations study, not changes to the golds.

## Results that change for existing jobs

- **Collateral and solar PV are non-permanent dead loads** (item 5). They are declared as `D_roof_collateral` and
  `D_roof_pv` (kN/m² of plan) apart from the permanent `D_roof`. They take the dead-load factor where they add to the
  effect and are left out of the IS 800 Table 4 0.9 DL rows: they cannot be relied on to resist uplift or overturning.
  Both still count in the IS 1893 7.4 seismic weight. The PEB golds Ex1–Ex5 declare them this way. Uplift cases on
  purlins, rafters and bases are now more onerous where the collateral used to help.
- **IS 18168:2023 6.2 is checked** (item 6): the unbraced length of the compression flange of an SMRF beam,
  Lbr/ry ≤ 25 within 2 db of the beam-to-column connection and ≤ 0.10 E/(Ry fy) elsewhere.
  - PEB rafters (`peb_checks.is18168_6_2_records`): from the fly-brace points, with the end bays measured from the
    column face. IN_Ex4 now has fly braces at every purlin (1.5 m); every second purlin failed 6.2 beyond 6 m.
  - Prismatic SMRF beams (`india_is800_s12.is18168_6_2_beam_checks`): from `cfg['beam_lateral_bracing']`. An
    undeclared job cannot be COMPLETE. `{'provide_at_required': True}` adopts the 6.2 spacings as a drawing
    requirement and prints them per beam. Ex8, Ex9, Ex12 (+ units B and C), Ex16 and Ex18 declare it.
- **Section 12 slenderness uses the declared member lengths** (`member_overrides` Lz_mm / Ly_mm) for every member,
  not only PEB members, so IS 18168 7.2 and the member check use one unbraced length.
- **IN_Ex9 effective lengths** (gold): the engine applies Ky to the element length, so the stated 3.0 m fly-brace
  spacing had become 1.55 m on the half-rafter and 1.875 / 1.125 m on the split columns. The stated restraints are
  now absolute lengths (`member_overrides` Ly_mm). The 7.5 m roof struts take K = 1.0. The lean-to SMF columns get a
  fly brace at mid-height from the wall girt (2.5 m), because K = 1.0 over 5 m fails IS 18168 7.2 (KL/r 99 > 75).
- **Flexible deck over a rigid model** (item 6, IN_Ex10): a diaphragm declared flexible but analysed with the rigid
  constraint is compared line by line with the tributary shares (`india_diaphragm.rigid_vs_tributary`). The lateral
  members' strength ratios are scaled by the worst line ratio. A scaled ratio above 1.0 is an open reason. IN_Ex10:
  the worst line takes 6.7 % more under tributary sharing and the largest scaled strength ratio is 0.25, so it is
  covered.
- **Crane bracket** (item 2): `cfg['crane']['bracket']` adds `conn-crane-bracket` (`crane_bracket.py`). It checks the
  bracket section under the seat forces, the fillet weld group at the column face, and the column web opposite the
  bracket compression flange (IS 800 8.7.4). Detail assumed: girder seated on the top flange, girder top flange tied
  to the column at rail level. IN_Ex3 and IN_Ex7 declare their brackets. IN_Ex7 gets a WI500X270X16X10 E250 bracket
  with 10 mm fillets (D/C 0.80, weld governing).

## Report (items 3, 4, 6, 7)

- Chapter 3: dead-load breakdown (permanent, collateral, PV and the 0.9 DL rule); wind base shear in the governing
  lateral load table (it was "—" on wind-governed jobs); the IS 875-2 3.2.1 reduction per column storey where
  applied; single-storey sheds no longer show floor rows.
- Chapter 6: crane runway (crane data, IS 875-2 6.3 impact / surge / traction, gantry girder demands and checks,
  bracket, crane sway); steel take-off in kg/m² for every job (non-PEB: modelled members by group, declared secondary
  members and brackets, with what is not included); for IS 18168 PEB jobs a note on where the ductile-design premium
  comes from.
- IN_Ex5: the PV answer at the top of the report: capacity as built, the governing check, the capacity under the
  H/150 reading and on strength alone (`pv_check.py --bisect-readings`), the before / after table and the reactions.
- Status block: non-blocking points for the checking engineer are printed (D-T9, anchorage notes), so COMPLETE never
  hides an open reading. D-T9 is listed as an open item in the PEB rulings table. The rulings table shows D-T2 only
  where IS 18168 is applied.
- Clean-up: code editions (IS 875 (Part 4):2021, IS 2062 (Part 1):2025, IS 801:1975 reaffirmed 2021, IS 18168 where
  applied); "design engineer" instead of "EOR" in new and printed text; "Building type" instead of "Archetype"; plain
  occupancy text instead of JSON; plan extents over all levels; R per direction; "Steel (rolled sections and welded
  plates)"; the diaphragm as analysed. Connection rows without a strength ratio say why ("no joint (continuous
  member)", "no splice (continuous)", "CJP full strength: deemed to comply") instead of "not designed". Demand units
  (counts are not printed as kN; bearing forces in kN). The literal "&mdash;" in PEB tables is gone. Appendix C prints
  the log file name, not a build-machine path, and counts the failed standards look-ups once instead of listing each
  look-up service fault.

## STAAD.Pro export (item 8)

`staad_loads.py` records the loads the engine itself applies, by wrapping `ops.load` / `ops.eleLoad` while
`static_model` applies them, and converts them to STAAD global member and joint loads on the exported stepped model.
The file now has one primary load case per engine basic case:

- dead (permanent)
- collateral + PV
- floor / roof imposed
- snow per pattern
- crane per pattern
- member wind per pattern
- storey forces at the master, with the IS 1893 7.8.2 torsion as separate cases
- vertical earthquake
- IS 800 4.3.6 notional loads per combination

It has one LOAD COMBINATION per engine combination. Response-spectrum combinations carry the equivalent static storey
forces of the same direction, and the file says so. The parse-back test checks that each case's parsed resultant
equals the engine's recorded total.

## Tests

- `tests/test_first_wave_2026_10.py` (new): the 0.9 DL rule, the seismic weight, the crane bracket, 6.2 declared /
  undeclared / adopted, the rulings and D-T9, rigid versus tributary, Appendix C, the STAAD recorder, the report
  sections.
- `tests/test_peb_2026_10.py::test_staad_parse_back`: rewritten for the full export.
- `contract/AGENT_START.md` documents `D_roof_collateral`, `D_roof_pv`, `crane.bracket` and `beam_lateral_bracing`.

## Gold re-runs

See the table at the end of this file (filled in from the re-run of every gold).
