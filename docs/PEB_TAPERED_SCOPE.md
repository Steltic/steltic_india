# Scope: tapered built-up portal sheds (PEB) in Steltic India, plus a PEB variations library

Owner: Steltic. Written 2026-10-11 for a new agent; **revision 2 (2026-10-11)** after a review against Indian practice
and the IS corpus. Read this whole file before touching code.

What revision 2 changed: the example briefs are written and renumbered (section 5.8); the PEB variations category and
building-aware filtering are already in the hub (section 6); four corrections from the corpus (sections 5.3, 5.4 and
the templates); three new owner decisions (D-T6, D-T7, D-T8) and a sharper D-T2 (section 8); four new deliverables
that PEB engineers produce every day (section 5.7).

## 1. Why this work

The most common steel building that Indian structural engineers design is the single-storey industrial shed or
warehouse, and most of them are built as pre-engineered buildings (PEB): portal frames of welded, web-tapered
I-sections (tapered columns and rafters, haunched at the knee), cold-formed Z/C purlins and girts, and light
longitudinal bracing. Evidence (sources in section 10):

* the PEB market was about ₹195 bn in FY24 and grows 11–12 % a year; the organised sector is only 40–45 % of it, so
  half the market is local fabricators and consultants;
* warehouse leasing in the top 8 cities was 36.8 mn sq ft in H1 2026, 46 % of it by manufacturing occupiers — and
  83 % of it in seismic Zones III and IV (Mumbai, Pune, Ahmedabad, Chennai, Kolkata: 67 %; NCR: 16 %; Bengaluru and
  Hyderabad, Zone II: 17 %);
* PEB design-engineer job descriptions list exactly this scope: portal frames, crane buildings, mezzanines, lean-tos,
  canopies, gantry girders, anchor bolt plans and foundation reactions, bills of materials, tonnage optimisation;
  STAAD Pro and MBS; IS 800, IS 875, IS 811 and MBMA;
* IS 800 has no PEB guidance, so the industry designs tapered frames in software built on US practice and then
  "checks against IS". A PEB designed entirely to IS, with every clause cited, is what Steltic can offer that nobody
  else does — but only if it is honest about the corpus gaps (section 8) and does not make PEBs uncompetitive by
  over-reading the code.

Steltic India today designs portals only with prismatic IS 808 rolled sections (IN_Ex6, IN_Ex7, IN_Ex8, IN_Ex9 in the
2026-10 numbering); the briefs even say "the eave haunch is a connection detail, the model rafter is prismatic". A
PEB engineer will ask about tapered members first. This scope adds them end to end, makes the five PEB example briefs
(already written) runnable, and completes the PEB category of the Design variations module so engineers can run the
optimisation studies they do in practice.

## 2. Where everything is

All four repositories are checked out side by side in one workspace folder (`india_ws`):

| Repo | Role here |
| --- | --- |
| `steltic_india` | HR engine (IS 800). Most of the work: sections, builders, analysis model, member and connection design, report, viewer, exporters. The briefs are in `test_buildings/`. |
| `steltic_CFS_india` | CFS engine (IS 801 / IS 811). Purlins and girts (`india_cfs_portal.py`, `is811_sections.py`). Interface only unless D-T5 brings it in. |
| `steltic_hub_india` | Hub. The Design variations module is bundled at `steltic_hub/catalog/steltic_variations/variations/` (`library.py`, `metrics.py`, `scoring.py`, `prompts.py`). Example-brief pickers live in the manifests. |
| `steltic_nonlinear_india` | Out of scope (see section 9). |

**The 2026-10 renumbering is already merged** (branch `fix/2026-10-peb-briefs`): the briefs are numbered most common
type first, the five PEB briefs are IN_Ex1 … IN_Ex5, the 15 older HR briefs are IN_Ex6 … IN_Ex20. Read
`test_buildings/RENUMBERING_2026-10.md` before using any document dated before 2026-10.

Work on a new branch in each repo you change, `fix/2026-10-peb-tapered`, and deliver it the way the previous
fix branches were delivered (one PR per repo, a `CHANGES_2026-10-peb.md` at each repo root).

Read first, in this order: `steltic_india/contract/AGENT_START.md`, `contract/README_AGENT.md`,
`contract/IS800_WORKED_METHOD.md`, `contract/QUERYING_IS_CORPUS.md`, `steel_engine/roof_geometry.py` (module
docstring), `steel_engine/sections.py` (custom-section registry), `test_buildings/IN_Ex1_*.txt` … `IN_Ex5_*.txt`,
`IN_Ex6_*.txt`, `IN_Ex8_*.txt`, `IN_Ex9_*.txt`, and the gold solutions of IN_Ex6, IN_Ex8 and IN_Ex9 (report, `cfg.py`,
`SOLUTION.md`; in the gold pack dated 2026-09-27 they are Ex5, Ex3 and Ex15).

## 3. Rules that still apply

* Every clause, coefficient and limit comes from the IS corpus (retrieve, cite, store in `rag/`). Do not
  invent. Where the corpus is silent, say so and raise it as an owner decision (section 8). Do not fill it with
  a foreign code silently: owner ruling D3 (no foreign design basis) stands unless the owner rules otherwise.
* IS 1893 (Part 1):2016 + Amd 1 + Amd 2 stays the seismic basis (owner decision D1). The 2025 revision with Zone VI
  was withdrawn by BIS in March 2026.
* D4: OMRF and ordinary braced frames are not permitted in Zones III–V (IS 1893 Table 9 Note 1, as amended by Amd 2).
* All 15 existing HR examples (IN_Ex6 … IN_Ex20, and the 4 sub-units) must give the same results after your change.
  Prismatic members are the special case of a tapered member with equal end depths; do not change their path.
* Engine and builder changes must keep `engine3d.build`, `static_model.build_static` and `consistency.check`
  in agreement (they build the model independently today; see section 5.2).
* SI throughout (N-mm in the engine, kN / m / kN·m in reports).

## 4. Target buildings: what a typical Indian PEB looks like

Design the feature for this envelope; reject or flag anything outside it.

* Clear span 15–40 m, or multi-span modular frames with interior columns (Grade A warehouses: spans of 20–30 m,
  widths of 60–150 m); frame spacing 6–9 m; **eave height 6–14 m** (Grade A warehouses specify 10–12 m clear height
  under the haunch); roof slope 1:10 typical (1:20 to 1:6).
* Columns: web-tapered, shallow at a pinned base and deep at the knee; prismatic where a crane bracket or fixed base
  is used; interior columns of modular frames prismatic, usually pinned at both ends.
* Rafters: haunched / tapered from the knee over roughly the first 15–30 % of the span, then prismatic or gently
  tapered to the apex; continuous over interior columns in modular frames; bolted end-plate splices at the knee, at
  one or two rafter splices and at the apex.
* Plates: IS 2062 (Part 1) E350 common for flanges and webs, E250 also used — but an SMRF designed to IS 800 12.11
  alone must be E250 B (12.11.1); webs thin (often 4–8 mm) and frequently slender; flanges 150–300 mm wide,
  6–25 mm thick. Treat these as typical ranges to design within, not as code values.
* Restraint: purlins and girts at 1.2–2.0 m restrain the outer flange; flange (fly) braces from purlins / girts to
  the inner flange restrain it at chosen purlins, especially in the knee region where the inner flange is in
  compression.
* Walls: a 230 mm brick or block masonry dado to about 3 m with sheeting above is the Indian norm; it brings in the
  IS 800 Table 6 column limit for masonry / brittle cladding.
* Roof loads: collateral (sprinklers, lighting, cable trays) 0.10–0.25 kN/m², rooftop solar PV 0.12–0.20 kN/m²
  (owner values; Grade A developers specify solar-ready roofs).
* Longitudinal: X-bracing in the end bays (rods, angles or CHS), portal bracing where doors block a bay.
* Bases: pinned (the PEB default, smaller foundations) or fixed (stiffer frame, bigger foundations).
* Options: EOT crane on column brackets, mezzanine, lean-to, dock canopy, rooftop solar PV.

## 5. Engine work in `steltic_india`

### 5.1 Section model: welded I and web-tapered I

* Extend `cfg['custom_sections']` / `sections.register_custom_sections` (today box only) with:
  * `type: 'welded_I'`: doubly symmetric plate girder `{D_mm, bf_mm, tf_mm, tw_mm, grade}`. Optionally
    monosymmetric (`bf_top`, `tf_top`, `bf_bot`, `tf_bot`) behind owner decision D-T3 (IS 18168 requires doubly
    symmetric SFRS members, so monosymmetric sections are never allowed in an SMRF under route B of D-T2).
  * `type: 'tapered_I'`: `{D_start_mm, D_end_mm, bf_mm, tf_mm, tw_mm, grade, straight_flange: 'outer'|'inner'|'both'}`;
    the depth varies linearly along the member; flanges constant per member (a flange-plate change = a new
    member at a splice).
* Section properties from the plates at any station: A, Iz, Iy, J, Iw, Ze, Zp (with the web), rz, ry, plus
  d/tw, b/tf for Table 2 classification. Weld size does not enter the properties.
* Designation strings that carry the plates so tonnage and the schedule are self-describing, for example
  `WI600X200X12X6` (D×bf×tf×tw) and `TI300-900X200X12X6` (D_start–D_end × bf × tf × tw). Mass per metre (or, for
  tapered, the mass of the whole member) is computed from plate areas at 7850 kg/m³.
* `section_type` = `'welded_I'`; IS 800 buckling class for welded I sections from Table 10 (retrieve), and
  `welded=True` everywhere `india_is800.section_class_table2` / `buckling_class` are called for these sections.
* Fabrication sanity limits declared in cfg (minimum web thickness, standard plate thicknesses and widths, maximum
  depth change per metre) with defaults the EOR can override; preflight WARN outside them.

### 5.2 Analysis model

* Model each tapered member as `n_seg` stepped prismatic `elasticBeamColumn` segments (properties at segment
  mid-length), default 8 per tapered member, set by `cfg['taper_nseg']`.
* Columns are not subdivided in the builders today (only beams in `static_model`); tapered columns must be. Do it
  in one place used by `example_build`, `frame_build`, `static_model.build_static` and `engine3d` so the
  three models stay identical, and extend `consistency.check` to compare them.
* Centroid offset of an asymmetric taper (one straight flange) is ignored in phase 1: the member axis is the
  work line through the section mid-depth. State this in the report as a modelling assumption.
* Convergence gate: rerun with `2 × n_seg` and require frame sway at the eave and apex deflection to agree
  within 2 %; record the result in the calc package (`taper_mesh_gate`).
* Knee and apex: rigid end-plate joints; offsets for the knee panel optional (declare).
* Frame stability: second-order elastic analysis (IS 800 4.4.3) or the frame buckling analysis of 4.6, using the
  elastic buckling load factor of the stepped model (retrieve both clauses and say which route was used).
* Roof geometry: keep `cfg['roof_planes']` (true slope, apex nodes); rafter segments follow the slope. Modular frames:
  interior columns pinned at both ends by default, rafters continuous over them.
* Self-weight: from the segment areas.
* Loads: no change in principle (IS 875 Parts 1–4, member-level wind on low-rise and portal buildings, crane rows);
  add collateral and solar PV dead loads as named roof dead-load components (`'collateral'`, `'solar_pv'`) so
  variations and the rooftop-solar check (IN_Ex5) can switch and scale them; add attached canopies (IN_Ex2) with
  their own uplift and down-load cases.

### 5.3 Member design (IS 800, checked at stations)

* Check every tapered member at each segment end and at the governing combination for each station, using the
  local section properties and local forces: section class (Table 2, welded), bending (8.2.1), shear including
  web shear buckling (8.4.2; `shear_capacity` already takes a stiffener spacing), combined (9.3), axial with
  buckling (7.1.2).
* **Slender (class 4) webs — correction in revision 2.** IS 800 does give a method: 3.7.2 (d) says the effective
  section of a slender section is found either by the IS 801 post-local-buckling provisions or by deducting the
  width of each compression element in excess of the semi-compact limit. Implement the deduction route (it needs
  nothing outside IS 800) for bending, axial and combined checks; keep the IS 801 route as an option only if the
  owner asks. Thin webs are what make a PEB economical — a "semi-compact or better" rule would make Steltic frames
  heavier than vendor quotes and engineers would notice. Plate girder provisions (8.6) and shear buckling (8.4.2)
  apply as retrieved. Exception: SMRF members (Zones III–V) must not be slender — 12.11.1 asks for 0.04 rad joint
  rotation, which a slender section cannot show, and IS 18168 Table 2 sets explicit limits under route B.
* Lateral-torsional buckling and member buckling of tapered members: IS 800 Annex E gives Mcr for prismatic
  members; the corpus has nothing on web-tapered members (3.7.3 (c) covers tapered flange *elements* only, by
  reference to SP 6 (Part 1)). Implement the method the owner approves in D-T1. The default proposal (no foreign
  basis): LTB checked segment by segment between restraints, using the section at the most critical station of each
  restrained length with C1 from the moment gradient (`c1_from_end_moments`), outer-flange restraint at purlins and
  inner-flange restraint only where a flange brace is declared; in-plane column buckling from the frame's elastic
  buckling load factor (section 5.2) rather than an effective-length chart.
* Flange (fly) braces: declare them per frame (`cfg['flange_braces']` = purlin / girt positions, brace section,
  angle); design the brace member and its connection for the restraint force IS 800 requires — start from 8.3.2
  (intermediate lateral restraints) and what it points to; retrieve, do not assume 2.5 %.
* Serviceability: IS 800 Table 6 for industrial buildings — rafter supporting profiled metal sheeting (span/180) or
  plastered sheeting (span/240); column lateral limit H/150 with elastic cladding and **H/240 with masonry / brittle
  cladding** (the brick dado); crane rows (gantry vertical, gantry lateral, frame lateral under crane + wind) — all
  from the stepped model and retrieved, not copied from here.

### 5.4 Connections

* Knee, rafter splice and apex: bolted extended end-plate moment connections using
  `india_connections.end_plate_moment_capacity` and the IS 800 Section 10 bolt checks, plus haunch flange and web
  checks at the connection (compression stiffener, web crippling and bearing, retrieved).
* **Section 12 applies to the portals in every zone** (12.1). Revision 2 adds:
  * bolts in the portal joints are fully tensioned HSFG bolts to IS 4000 (12.4.1) — the engine's
    `hsfg_gate` already enforces this; IS 1367 bearing bolts are not an option for these joints;
  * the joint design moment is 12.10.2.1 for an OMRF (at least 1.2 × the full plastic moment of the connected beam,
    or the maximum moment the beam can deliver, whichever is less) and 12.11.2.1 for an SMRF (1.2 Mp). Which Mp
    counts at a tapered joint face is owner decision D-T7;
  * 12.4.2 (all welds in frames resisting earthquake loads are complete-penetration butt welds, except column
    splices) is gated today on connection welds. Whether it also covers the flange-to-web welds of built-up members
    is owner decision D-T6 — read literally it would make every PEB uneconomic, so do not decide it silently;
  * fixed bases: designed for 1.2 × the column's full plastic moment (12.12.1).
* Flange-to-web fillet welds (subject to D-T6): design for the longitudinal shear (IS 800 10.5, retrieved), minimum
  size by plate thickness.
* Pinned base: base plate, anchor bolts in tension (uplift under 0.9DL + 1.5WL) and shear (thrust), shear key or
  friction where the corpus permits; fixed base where declared. Foundation stays a delegated design with the
  interface forces exported (`cfg['delegated_design']`).
* Longitudinal bracing connections (rods: turnbuckle / threaded end in tension; angles or CHS: gusset).

### 5.5 Secondary members

* Purlins and girts are designed in `steltic_CFS_india` (IS 801 / IS 811). **Recommendation for D-T5: run the CFS
  engine for the gold examples in this scope.** PEB engineers compare whole-building kg/m² (primary + secondary +
  bracing); a figure without purlins and girts will not be believed. Minimum: a hub batch step that runs the CFS
  engine on the same building and feeds purlin and girt tonnage back into the variations metrics.
* Whatever D-T5 decides, the HR job declares the purlins and girts in `cfg['delegated_design']` with spacing, span,
  loads and the restraint they provide; the HR design uses the declared spacing for flange restraint.

### 5.6 Report, schedule, viewer

* Member schedule (`design/member_schedule.csv`): one row per member with designation, plate sizes, start and
  end depth, length, and a new `mass_kg` column computed from the plates. Keep the existing columns.
* Report: a frame elevation per typical frame with the depth drawn to scale; a tapered-member table (stations,
  section class, governing check, D/C); the restraint layout; the taper mesh gate; steel tonnage and kg/m² of
  plan area, split primary / bracing / crane / canopy / (secondary when available).
* `viewer3d.py`: draw tapered members by segment so the depth reads in 3D; colour by D/C per station.

### 5.7 New deliverables PEB engineers expect (revision 2)

These are the first documents a PEB vendor issues; without them an Indian engineer will not take the package
seriously. All four are written for every portal job (and are harmless for the others).

1. **`design/reactions.csv`** — unfactored support reactions per basic load case (DL, collateral, solar PV, LL, each
   wind case, each crane case, EQ ±X / ±Y) and per column line / grid, with Fx, Fy, Fz, Mx, My in kN and kN·m, sign
   convention stated in the header; plus the governing factored envelope per support. This is what the civil
   foundation designer works from.
2. **`design/anchor_bolt_plan.svg`** (and a table in the report) — grid lines, column orientation, base plate size,
   anchor bolt count, diameter, grade, spacing and projection per base type, base type marks, and the reaction
   envelope per mark. Drawn to scale from the model, not hand-placed.
3. **`design/bom.csv`** — a bill of materials by member mark: plates (thickness × width × length per plate, grade,
   mass), rolled sections, purlins / girts when the CFS step ran, bolts (count by diameter, grade and length), with
   totals by category (primary, secondary, bracing, crane, canopy, connections) and kg/m² of plan area.
4. **`model.std`** — a STAAD.Pro input file of the analysis model (joints, members, the stepped tapered segments as
   prismatic `PRIS` properties or STAAD `TAPERED` I-section properties, supports, releases, basic load cases and the load
   combinations used), so engineers can reproduce the analysis in the tool they already trust. Unit system
   `UNIT METER KN`. No design commands (STAAD's code check is not a Steltic result). Test: parse the file back and
   compare joint and member counts and the sum of each basic load case against the Steltic model to 0.1 %.

### 5.8 Example briefs (written in revision 2)

The five PEB briefs are in `test_buildings/` (RETRIEVE style; no IS values except the occupancy's I):

| Brief | Building | What it exercises |
| --- | --- | --- |
| `IN_Ex1_PEB_factory_shed_tapered_Bengaluru` | 30 m clear span × 72 m, 10 m eave, 1:10, frames at 7.5 m, pinned tapered columns, tapered rafters, brick dado, Zone II, OMRF portals, braced end bays | The core PEB case, wind governed |
| `IN_Ex2_PEB_GradeA_warehouse_multispan_Bhiwandi` | 96 × 108 m, 4 × 24 m modular frames at 9 m, 13 m eave (12 m clear), 1:20, dock canopy, sprinklers, solar-ready roof, Zone III (map reading) | The flagship: the biggest Indian market, multi-span, D-T2 route, canopy uplift |
| `IN_Ex3_PEB_crane_shed_10t_Nagpur` | 24 m span × 60 m, 10 t EOT crane on brackets, prismatic welded columns, fixed bases, Zone II | Crane rows, bracket, gantry girder, fatigue, crane-frame limits |
| `IN_Ex4_PEB_warehouse_SMRF_Zone4_NCR` | 30 m span × 90 m fulfilment warehouse, Farrukhnagar (KMP belt), Zone IV (map reading) | The D4 gate on a PEB: SMRF by the D-T2 route, or a documented stop |
| `IN_Ex5_PEB_rooftop_solar_check_Bengaluru` | Rooftop PV on the IN_Ex1 shed as built | Check mode (no resizing), before / after D/C, the roof's PV capacity by bisection, an adequacy note for the installer |

Each brief opens with a "PEB release" paragraph telling the agent to stop with design_status 'blocked' if tapered
sections are not supported. When this scope is delivered, change that paragraph to a one-line note, and add
`in1` … `in5` to the HR UI picker (`frontend/index.html`) and the hub manifest (`steltic_india.json`), and update
`tests/test_india_contract.py::test_frontend_lists_only_india_briefs` (it expects in6 … in20 today).

The cyclone-belt multi-span case of revision 1 (Visakhapatnam) is now variation template "Cyclone-belt site".

### 5.9 Tests

* Unit: welded I and tapered I properties at stations against hand-calculated values; Table 2 classification of
  welded webs; the 3.7.2 (d) effective section of a slender web against a hand calculation; stepped tapered
  cantilever tip deflection against the closed-form solution within 1 % at `n_seg = 16`.
* Exporters: `reactions.csv` equilibrium (sum of reactions = applied load per basic case, 0.1 %); `bom.csv` total
  = `member_schedule.csv` total; `model.std` round trip (section 5.7).
* Regression: the full existing HR test suite and the 15 gold examples (IN_Ex6 … IN_Ex20) re-run unchanged (same
  `design_status`, same member schedule, D/C within 0.001).
* Integration: IN_Ex1 and IN_Ex3 COMPLETE (design_status complete, 0 reasons, preflight clean, consistency clean);
  IN_Ex2 and IN_Ex4 COMPLETE or a documented stop as D-T2 decides; IN_Ex5 a complete check with its PV capacity.

## 6. Hub: PEB variations in the Design variations module

### 6.1 Done in revision 2

* `library.py` has the `peb` category (`applies_to: ["portal"]`) with 38 single-change templates: layout (spacing,
  spans, slope, eave), bases, the rolled-frame benchmark, grades (E250 B for IS 800 SMRF, E350), restraint, purlin
  spacing, bracing, end walls, cranes, mezzanine, lean-to, dock canopy, rooftop PV, sandwich roof, collateral, brick
  dado, Table 6 limits (H/240 masonry, span/240 plastered), terrain category 3, no Ka / Kc, dominant opening, cyclone
  belt, Zone III by both D-T2 routes, and four "(tapered frames)" templates that need this release.
* `core`, `perimeter` and `outriggers` carry `applies_to: ["multistorey"]`. `library.building_kind(brief)` classifies
  the base brief (two or more storeys → multistorey; shed / warehouse / portal / PEB words → portal), and the offline
  plan and the LLM prompt examples use only the applicable categories when the user has not ticked any. The user can
  still tick any category. `/api/library` reports `applies_to`. Tests in `tests/test_variations.py`.
* Revision-1 template fixes applied: the sway template is H/240 (Table 6, masonry / brittle cladding), not H/300;
  the Zone III template says IS 18168 is optional for industrial buildings (1.2) and offers both routes.

### 6.2 Still to do (needs the engine work)

* `metrics.py`: read `mass_kg` from the member schedule when present (tapered members carry no mass in the
  designation); report `steel_t`, split into primary frames / bracing / crane / canopy / secondary (when the CFS
  step exists); add `plan_area_m2`, `steel_kg_per_m2`, `n_frames`, `n_end_plate_joints`, `base_thrust_max_kN`,
  `base_uplift_max_kN`, `base_moment_max_kNm` (from `design/reactions.csv`), `pv_capacity_kN_m2` (IN_Ex5-type
  checks), and `sway_utilisation` / `rafter_deflection_utilisation`.
* `scoring.py`: add INR rates for `built_up_per_t` (fabricated welded plate members), `rolled_per_t`, `cfs_per_t`,
  `per_end_plate_joint`, and a foundation proxy per base (scaled by uplift and moment). Keep `DEFAULT_RATES`
  editable; mark them as placeholders the user sets.
* A PEB default equation offered when `building_kind` is portal, for example:
  `S = 0.55*(1 - cost_per_m2/cost_per_m2_max) + 0.20*(1 - foundation_proxy/foundation_proxy_max) + 0.15*sway_margin + 0.10*deflection_margin`.
* Eligibility: `representable_only` must not reject tapered designs by default for portal studies (the nonlinear
  tools cannot model them yet; see section 9) — make it a visible rule that is off for PEB studies, and say why on
  the Results tab. `revenue_proxy` (floor area × rate) is meaningless for a shed; hide it for portal studies.

### 6.3 Hub plumbing

* Add `in1` … `in5` to the HR example-brief picker in `steltic_india.json` when they run (section 5.8); the engine
  already serves `/api/example/in1` … `in20`. Admin batch syntax already accepts any `inN`.
* Re-run the hub tests (`python -m pytest tests -q`), including the test that no hub code branches on a module id.

## 7. Deliverables and acceptance

1. Branch `fix/2026-10-peb-tapered` in `steltic_india` and `steltic_hub_india` (and `steltic_CFS_india` only if
   the interface or D-T5 needs it), each with `CHANGES_2026-10-peb.md` and passing tests.
2. Gold solutions for IN_Ex1 … IN_Ex5 in the same layout as the gold pack (SOLUTION.md, cfg.py, report.html,
   viewer_3d.html, design/ with the section 5.7 files, rag/), with an updated GOLD_INDEX.md. Rename the existing gold
   pack to the 2026-10 numbers first (`python3 scripts/renumber_2026-10.py tree <old pack> <new pack>`).
3. Regression evidence: the 15 existing gold examples re-run with identical results (a table of before / after
   governing D/C and design_status, keyed by the new numbers with the old ones alongside).
4. One complete variations study on IN_Ex1 (or IN_Ex2 once D-T2 is ruled) with at least 12 of the PEB templates,
   scored with the PEB equation, `results.csv` and the selection recorded.
5. A short `PEB_LIMITATIONS.md`: what is modelled as an assumption (centroid offset, stepped segments), what
   IS 800 does not cover and how it was handled, and what the owner decided in section 8.

## 8. Owner decisions to raise early (stop and ask; do not assume)

* **D-T1 Stability basis for tapered members.** The corpus has nothing on web-tapered members (Annex E is
  prismatic; 3.7.3 (c) is about tapered flange elements). Propose the method in 5.3. Using a foreign reference (for
  example a US design guide for web-tapered frames) conflicts with D3 and needs an explicit ruling.
* **D-T2 Zones III–V (sharpened in revision 2).** OMRF and ordinary braced frames are banned there (IS 1893 Table 9
  Note 1, D4), so PEB portals must be SMRF. 83 % of the warehouse market is in Zones III–IV, so "tapered PEB in
  Zone II only" would leave most engineers out — do not offer it as the default. Ask the owner to choose:
  * **Route A — IS 800 12.11 alone:** plates E250 B (12.11.1); 0.04 rad joint rotation (so no slender elements);
    1.2 Mp joints; 12.11.3.2 strong column at every joint.
  * **Route B — IS 18168:2023 adopted voluntarily:** 1.2 makes IS 18168 mandatory in Zones III–V only for
    residential, educational, institutional, office, business and community / lifeline buildings — industrial and
    storage buildings are not listed. The engine already applies IS 18168 by occupancy (ruling R8) and takes
    `cfg['apply_is18168'] = True` as the opt-in, so route B is that override. Adopting it allows E350 (5.2) but brings the Table 2 width-to-thickness limits,
    doubly symmetric sections (6.1, 7.1), Ry overstrength and, in Zones IV–V, the 15 m height limit of 1.3; 8.2.1
    relieves the strong-column check at the roof level.
  * **Or** add IS 1893 (Part 4) (industrial structures) to the corpus if the owner holds a licence and wants it
    considered.
  The variations module already has a template for each route, so the owner can see the cost of both.
* **D-T3 Monosymmetric sections.** Allow unequal flanges in phase 1 or not (never in an SMRF under route B).
* **D-T4 Tension-only rod bracing** for longitudinal bracing in Zone II, if the corpus does not settle it.
* **D-T5 Purlins and girts.** Delegated in phase 1, or run the CFS engine from the hub in this scope
  (recommended for the gold examples, section 5.5).
* **D-T6 (new) Scope of IS 800 12.4.2.** "All welds used in frames designed to resist earthquake loads shall be
  complete penetration butt welds, except in column splices." Does this cover the flange-to-web welds of built-up
  members, or only the connection welds the engine gates today? Read literally it rules out the fillet-welded
  plate girders every PEB uses, in every zone (12.1). Ask; do not decide.
* **D-T7 (new) Joint design moment at a tapered face.** 12.10.2.1 / 12.11.2.1 size the joint for 1.2 × the full
  plastic moment of the connected beam. For a tapered rafter, is Mp taken at the joint face (deepest section), at
  the end of the haunch, or is the "maximum moment that can be delivered" route of 12.10.2.1 used? Propose one with
  its cost on IN_Ex1.
* **D-T8 (new) IS 18168 in the IN_Ex9 brief.** The Shimla gable warehouse brief (IN_Ex9, formerly Ex15) says IS 18168
  is "mandatory in Zone IV, cl. 1.2" for a general storage warehouse, which 1.2 does not list. Ask the owner whether
  to keep it as a deliberate choice (record it in the brief as `cfg['apply_is18168'] = True`, an owner opt-in) or
  correct the wording; either way the gold results should not change, because the brief already designs to IS 18168
  — confirm by re-running IN_Ex9.

## 9. Out of scope

* Nonlinear (pushover / NLRHA / DDM) of tapered frames in `steltic_nonlinear_india`. Mark tapered designs
  "not representable in the current nonlinear tools" in the variations metrics. A later scope will add tapered
  fibre sections.
* Foundations (delegated, interface forces and the reactions file only).
* Cladding, sheeting and PV mounting design.
* Curved rafters, cellular (castellated) beams, space frames.
* The website and the gold packs outside git: the owner renames them with `scripts/renumber_2026-10.py tree`.

## 10. Sources for section 1

* Crisil, via Tradejini (2024): PEB market ₹195 bn in FY24, 11–12 % growth, organised share 40–45 % —
  https://www.tradejini.com/blogs/indias-infra-growth-open-doors-for-interarch
* Knight Frank, India Warehousing Market Report H1 2026 (city volumes, occupier mix) —
  https://content.knightfrank.com/research/3131/documents/en/india-warehousing-market-report-h1-2026-12992.pdf
* PEB design engineer job description (responsibilities, software, codes) —
  https://jobs.weekday.works/design-engineer-peb-at-eco-turnkey-solutions-wkdywhpohz
* SSMB (2024), revamping India's steel construction codes (no PEB guidance in IS 800; MBMA used; seismic rules make
  light industrial buildings heavier) — https://ssmb.in/2024/12/23/revamping-indias-steel-construction-codes-for-innovation/
* ESR, warehouse specification checklist (10–12 m clear height, K115 roof sprinklers, solar) —
  https://in.esr.com/newsroom/blogs/complete-warehouse-checklist-specifications-and-green-features-for-e-commerce-retail-and-3PL
* IS 1893 (Part 1):2025 withdrawal — https://www.etvbharat.com/en/opinion/a-bold-policy-reversed-the-withdrawal-of-indias-2025-seismic-code-enn26031103638
* Code text quoted in sections 4, 5 and 8 is from the owner's IS corpus (`engineering_rag_india`): IS 800:2007 3.7.2,
  3.7.3, 4.4.3, 4.6, 8.3.2, Table 6, 12.1, 12.4, 12.10, 12.11, 12.12; IS 1893 (Part 1):2016 Table 9 and its notes;
  IS 18168:2023 1.2, 1.3, 5.2, 6.1, 8.2.1.
