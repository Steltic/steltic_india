# steltic-india 0.3.0 — 2026-09 review fixes

Branch `fix/2026-09-review`, based on the delivered 0.2.2 tree. Scope rows H01–H52 (P0/P1), X01–X07 (phase-2 capabilities), D01–D05 (docs, briefs, contract lint) and RR-BUG-1..6 (defects found by re-running the 30 reference jobs on the fixed engine). Rulings R1–R12 applied as recommended in the fix scope (R12 was met with fly and knee braces in the CFS repo, because no heavier IS 811 column exists).

## Results that change for existing jobs

These are intended. The old results were unconservative or wrong.

- **Seismic weight W rises.**
  - Partitions: max(0.5, partition allowance), per R1.
  - Self-weight is assigned by elevation.
  - `nodal_masses` / `nodal_dead_loads` are included.
  - The crane bridge and crab are 100 % in W; the lifted load is excluded.
  - Cladding uses the envelope at or above each level.
- **V-bar_B per direction** is taken as the larger of the engine value and the agent value. Per-direction R_x and R_y are applied in ESM and RSA.
- **Earthquake combinations** no longer apply the IS 875-2 imposed-load reduction.
- **IS 18168 applies by occupancy (1.2 list) in Zones III–V**, per R8, with the `apply_is18168` override. Where it applies:
  - Table 2 width-thickness checks are always live, including built-up boxes.
  - Column splices follow IS 18168 (tie force, bearing option, CJP deemed-to-comply per R4).
- **Braces and gussets** use per-axis K. The gusset buckling demand rises.
- **SFRS column bases** are checked per load case and biaxially. The capacity moment is used with seismic cases only.
  - Pinned braced-frame bases now take 1.2 Vd (IS 800 12.12.2). This is an open item for an owner ruling.
- **Table 3 slenderness** is always part of member D/C. When it governs, the record's value and limit are KL/r (RR-BUG-5).
- **Across-wind gate** (R10): the job stays PARTIAL unless there is an evaluated Mc or an EOR record.
- **Flexible-diaphragm gate** (Table 5(ii)): passes only from an engine run (X01) or a complete EOR record.
- **Completion authority:** one authority, `design_status`, which now includes rag evidence and the pairing of found:false rows with EOR records.
  - Jobs without stored rag hits or EOR assumptions become PARTIAL.
- **Declared corpus Ka** below the IS 875-3 Table 4 value at the loaded area is replaced by the Table 4 value (RR-BUG-6).
- **Importance factor:** Table 8 keywords are matched on word boundaries and ignore negated phrases. Owner ruling D8 is labelled as a ruling.

## New capabilities (opt-in)

- **X01** — IS 1893 Table 5(ii) flexible-diaphragm 3-D dynamic analysis, enveloped with the rigid case (`diaphragm_stiffness`, `flexible_diaphragm_analysis`).
- **X02** — true-slope pitched roofs and region roofs (`roof_planes`, `roof_regions`).
- **X03** — stiffened (gusseted) and embedded column bases; 9.3.1.2 Mpc by section form.
- **X04** — `pipeline.design_units`: several seismically separated units in one job, with 7.11.3 joint checks.
- **X05** — IS 875-3 10.3 across-wind load cases and 10.4 simultaneity rows.
- **X06** — shared JSON frame builder `steel_engine/frame_build.py`, used by the CFS repo, plus an EBF reference example.
- **X07** — erection sequence: braces connected after the dead load.

New cfg keys are documented in `contract/AGENT_START.md` and `README.md`. The D05 lint test fails if any key the engine reads is undocumented.

## Environment

- `RAG_API_URL`: URL of the corpus server, e.g. `http://127.0.0.1:8765`. Start the server with `python3 scripts/serve_http.py --host 127.0.0.1 --port 8765` in engineering_rag_india.
- `INDIA_CORPUS_ROOT`: path to an engineering_rag_india checkout. If unset, a sibling checkout is used.

## Tests

`python3 -m pytest tests -q -p no:cacheprovider` gives 906 passed and 1 skipped (the fastapi-only test). The X01 corpus-quote test also skips when no corpus checkout is found.

## Additions from the gold-standard round (2026-09-26/27)

The 30 examples (34 runs) were taken to COMPLETE as a gold set, and checked twice by an independent auditor. The engine defects found along the way are fixed here.

- **Owner rulings.**
  - **O1:** IS 800 12.12.2 stays literal. Pinned braced-frame bases take 1.2 Vd.
  - **O2:** gantry and crane-girder weight goes in `nodal_dead_loads`. Strut elements are listed in `self_weight_in_nodal_loads`, and double counting is a preflight ERROR.
  - **O3:** the CFS framed area falls back to `geometry.floor_area_m2`.
- **GOLD-1:** minimum-type check rows (`sense: '>='`) are no longer mis-read by consistency.
- **GOLD-2:** deck stiffness can be set per level (`diaphragm_stiffness.by_level`).
- **GOLD-3:** rafter deflection with `roof_planes` uses the analysed frame over the full span.
- **GOLD-4:** a declared shear key is checked. It takes all shear beyond friction; there is no sharing with the anchors (lead decision).
- **GOLD-5:** beam-end connections are checked for the V+N resultant, including collector, chord and deck axial forces.
- **GOLD-6:** a beam that bounds no bay gets no imposed-load tributary.
- **GOLD-7:** a CJP-only splice gate is accepted without a D/C.
- **AUD-1:** the evidence gate is stricter. Each row needs its own `hit_file` + `quote`, or a matching stored query.
- **AUD-2:** plate fy is taken from the IS 2062:2025 thickness band (`plate_grade`, `n_plates`, splice `t_mm`). A declared fy above the band is reduced.
- **AUD-3:** the 7.6.4 record reports the computed classification and warns when the declared label contradicts it. A rigid light deck with no stiffness basis also warns.
- **AUD-4:** anchorage can use a derived bond form, π d L τbd, with τbd from IS 456 26.2.1.1 as an EOR input (plain bars get no ×1.6). A `concrete_breakout` record needs a `delegated_design` item. The asserted capacity form now needs `source` + `cite`.
- **GOLD-764:** the 7.6.4 classification is code-literal: chord deviation ÷ average displacement of the entire diaphragm. The storey-drift ratio is kept as information.
- **GOLD-COLL:** flexible-diaphragm collectors accumulate along the line to the vertical elements. The X01 axial forces are used for the flexible earthquake case. Diaphragm labels can be set per level (`diaphragm_by_level`).

**Result changes:** every item is stricter, or corrects a reading to the code text. None relaxes a check.

## Commits (oldest first; subjects only — hashes change when the branch is replayed onto GitHub)
- H17: no IS 875-2 imposed-load reduction in earthquake combinations (IS 875-5 8.1, CFS-C-09)
- H15: IS 875-3 Table 6 FH -0.8 (30/60 deg mid band), Table 5 printed band edges, EOR Cpe path; corpus-diff test (HR-E-25, L-15, C3)
- H31: consistency false positives -- governing child D/C, geometry/boolean gates, structured delegated/vibration records (HR-A-05, HR-D-11, HR-E-12, E8 part, HR-A-16, HR-D-16, HR-E-24)
- H01: flexible-diaphragm gate only from an engine run or a complete EOR record; Table 5(ii) 15 % projection test (HR-B-18, CFS-B-01, CFS-C-02, CFS-D-01, E1)
- H21, H47: cyclone-belt wind structure class required, hospital k1 warning; one site-proxy policy (E7, HR-A-12, HR-C-10, ruling R5)
- H37: filter bolt kwargs to the capacity signature; guard each connection row (HR-B-17, HR-C-16)
- H33 H34 H38: finite D/C at P >= Nd; Table 3 always in member D/C; channel LTB via E-1.1
- R01 R02 R03 R04 L-08(part): standards search tool -- errors, exact hits, evidence files, aliases
- H20: IS 1893 Table 8 importance factor -- word-boundary keywords, residential precedence, explicit class flags, D8 labelled as ruling (CFS-C-11, L-14, ruling R2)
- H02, H06: engine V-bar_B per direction (max of engine and agent, preflight ERROR > 2 % low); per-direction R_x/R_y in ESM/RSA; EBF link chain for any EBF component (E2, HR-E-17)
- H32: free-text note leaves exempt from the EXAMPLE label scan (HR-D-09)
- H30: one completion authority -- design_status folds in rag evidence, literal D/C and found:false EOR pairing (L-04, HR-E-04)
- H05 H52: IS 18168 Table 2 live whenever IS 18168 applies, box rows; applicability by 1.2 occupancy (E4, HR-C-14, CFS-A-17)
- H07: per-axis K in S12 brace compression, KL/r and gusset buckling; OCBF/SCBF brace demand from Table 4 (L-02, HR-B-03)
- H43: package and provenance -- load_plan.json every run, whole load_plan, governing LTB record, wind_serviceability always (L-03, HR-A-08, HR-C-08, HR-E-18)
- H03, H51: R9 torsional / translational mode identification with the modes recorded; Table 5(i) ratio from lateral displacements only; drift for +F and -F (CFS-B-10, CFS-C-08, CFS-D-02, HR-E-20, HR-D-17)
- H44: hygiene -- STATUS.engine.md, residue word boundaries, IS-only grounding credit, OMF 12.10.2 labels, pipeline docstring (E9, E10, L-06, HR-B-14, HR-E-19, L-07)
- H09: box-column panel zones count both webs and are checked in the second frame direction (HR-A-04, HR-D-05)
- H04: one floor mass-moment-of-inertia helper with the true plan extent in modal_props, _modal_impl, example_build and the static accidental torque; builder J and cfg['Jm_by_level'] kept (HR-B-11, E3, NEW-5)
- H45: multi-unit jobs -- sanitised figure names, basename titles, 7.11.3 D1 at the matching level (HR-C-06, HR-D-13)
- H12: across-wind gate passes only with an evaluated IS 875-3 10.3 result (found:true + numeric Mc_kNm, or EOR {value, source, cite}) per ruling R10 (HR-A-03, HR-B-09, HR-C-12)
- H36: IS 18168 12.3.4.4 only where a brace / gusset frames into the beam-column joint (CFS-D-05)
- R01: stop the ladder once the corpus says the document is not in it
- H46: IS 18168 5.5(1) gamma_LL 0.25 for imposed load <= 3 kN/m2; SCWB Pu basis stated (HR-E-22, HR-A-07, HR-D-07)
- H16, H22, H50 (W part): seismic weight completeness -- self-weight by z, nodal_masses / nodal_dead_loads / crane bridge + crab in W and modal mass, envelope cladding, grid(cfg, 0) = present[0]; partitions max(0.5, allowance) + preflight WARN (R1); roof_levels (HR-E-10, HR-B-13, HR-B-08, HR-E-21)
- H11, H13, H14, H50: snow as roof imposed load, secondary-beam decks, member-level wind distribution, roof levels / nodal imposed loads
- H35: floating_columns skips columns founded on a support / declared stepped base; floor_beam_gaps honours omit_beams_at and support pairs (CFS-D-03)
- H19: per-member overrides (K, LLT incl. columns, Lz/Ly, grade, process); brace grade kept; CHS/NB tube grade for any kind (HR-E-15, CFS-A-16, CFS-D-11, HR-B-05, HR-E-14)
- H08: SFRS base demand per case, biaxial, capacity moment only with seismic cases (HR-B-06, HR-B-15, HR-D-04, HR-C-07, HR-E-11, CFS-B-04)
- H48: crane sway model option cfg['crane']['sway_model'] in {building, single_frame}; single_frame (the loaded bracket frame rebuilt alone as a plane frame) is the default unless the roof is a rigid diaphragm with declared cfg['roof_bracing'] (HR-E-09)
- H49: flexible-diaphragm line shears use each level's own footprint as the mass extent (no half-bay padding, not level 1 for every level); collector rows keep their flexible 7.6.4 cite (HR-D-15, NEW-4)
- H42: engine switches to SI automatically for N-mm / metre cfgs and India jobs; India-worded unknown-section error (L-05)
- H18: preflight pitched-roof guard -- sloped beams and zero-tributary roof beams are ERRORs (HR-E-05, NEW-1)
- H11: vertical-EQ (ELZ leading) rows keep the roof imposed term (fLr = fL, snow when snow > Lr)
- H08: biaxial base - no corner anchor tension while the resultant is inside the kern; corner bearing check
- H10 H41: IS 18168 column-splice rules, concurrent P/Mz/My, bearing option, flange share, CJP gate (HR-A-06, HR-B-04, HR-C-20, HR-D-12)
- H39: EBF link role, links out of the beam-to-column shear demand, EBF moment-connection row, engine3d.add_link (HR-B-19, HR-C-15)
- H40: construction-stage check per floor-beam element and direction, half-bay on edge beams, element grade (HR-C-05, HR-D-06)
- H05 H10: re-size the IN_Ex1 test fixture's SFRS members and SFRS splices for the live IS 18168 rules
- H52 H05: Section 12 advisories state the IS 18168 applicability basis and list Table 2 / splices as live
- R02: recognise an exact table reply by the table's own caption title
- Integration: Ex1 core test reads the interior girder shear after H13 half-bay edge tributary
- L-08: india_omega_is18168.corpus_root falls back to a sibling engineering_rag_india checkout
- X05: IS 875-3 10.3 across-wind load case W_X_across / W_Y_across, 10.4 simultaneous rows (HR-B-09, HR-C-12)
- X06: shared JSON frame builder steel_engine/frame_build.py (from CFS india_cfs_frame_build), EBF reference example, package-finalize helpers (E11, HR-B-20)
- X04: pipeline.design_units -- several seismically separated units in one job with IS 1893 7.11.3 joint checks (HR-D-13, HR-C-06)
- X07: optional erection sequence -- braces connected after the dead load (HR-C-19)
- X03: IS 800 7.4.2 stiffened (gusseted) and embedded column bases, 9.3.1.2 Mpc by section form (HR-A-09, HR-C-17, HR-D-04(b), E8)
- X02: true-slope pitched roofs (cfg['roof_planes']) and region roofs (cfg['roof_regions']) (HR-E-05, HR-A-15, HR-B-16, CFS-A-15)
- X01: IS 1893 Table 5(ii) (Amd 2) flexible-diaphragm 3-D dynamic analysis, enveloped with the rigid case
- X01/X02 integration: move roof-plane zeroLength spring tags to 7,000,000 (8M = flexible-diaphragm deck, 9M = sub-elements)
- X02/X01 into the shared frame_build: roof planes (apex nodes, rafters, free eave spread), roof regions, flexible-diaphragm note
- D02: retire IN_Ex12_EOR_inputs_EXAMPLE.json to usa_reference/; rename the stale 'Ex13' OCBF Zone II fixture (HR-D-18, B12, B13)
- D01: brief corrections B1-B11 + brief lint (HR-E-23, HR-A-12, L-14; rulings R2, R5, R6, R7, R10)
- D03: HR contract + README document the phase-1/2 cfg keys and behaviours (HR-B-20, HR-D-16, HR-B-05, HR-D-13, HR-D-17, HR-A-13, HR-B-04, L-15)
- D05: contract lint -- every cfg key the HR engine reads is named in contract/*.md or README*.md
- RR-BUG-1: IS 1893 Table 8 importance-factor keywords ignore negated phrases
- RR-BUG-2: guard off-diaphragm beams (tag level > NF) in the one-way gravity helpers
- RR-BUG-5: name the governing check when IS 800 Table 3 slenderness governs the member D/C
- RR-BUG-4: order design_status reasons by class, group per-check element rows, never drop a class
- RR-BUG-6: a declared corpus Ka is per direction or area-checked against Table 4
- X01: corpus-quote test finds INDIA_CORPUS_ROOT or sibling engineering_rag_india checkout
- O1: IS 800 12.12.2 stays code-literal on pinned braced-frame bases (owner ruling O1, 2026-09-26)
- O2: gantry weight as nodal dead loads, never also as element self-weight (owner ruling O2, 2026-09-26)
- GOLD-1: minimum-type check rows carry sense '>=' (dc = limit / value) (IN_CFS_Ex13, IN_CFS_Ex7)
- GOLD-2 (X01): deck stiffness per level for the Table 5(ii) flexible-diaphragm run (IN_CFS_Ex9)
- GOLD-3: IS 800 Table 6 rafter deflection of roof_planes portals from the analysed frame over the full span (IN_Ex15)
- GOLD-4: declared column-base shear key gets a check row with source and cite (IN_Ex8)
- GOLD-5: beam-end connections of collector / chord beams carry the axial force with the shear (IN_CFS_Ex6)
- GOLD-6: imposed-load deflection of a beam bounding no floor bay uses a zero tributary (IN_CFS_Ex14)
- GOLD-7: HR consistency accepts a connection whose checks are all passing gates (CJP splice) without a D/C
- AUD-1: evidence gate -- a quote-less found:true row is backed only by a stored hit for its own query
- AUD-2: plate yield stress by thickness per IS 2062:2025 Table 3 in every plate check
- AUD-3: 7.6.4 record reports the computed diaphragm classification; label contradiction and unsupported light-deck rigid declarations are WARNs
- AUD-4: anchorage transparency -- derived bond embedment, asserted capacity needs source + cite, concrete breakout record
- GOLD-764: IS 1893 7.6.4 diaphragm classification on the code-literal ratio (IN_CFS_Ex9)
- GOLD-COLL: flexible-diaphragm collectors follow the load path; per-level diaphragm labels; X01 axial is the flexible case (IN_CFS_Ex9)
