# OpenSees Steel Building Design Agent — workflow guide (India)

**Audience: the LLM agent.** What you have, and the order to use it, to design ONE steel building to
IS 800:2007, IS 875 (Parts 1-5) and IS 1893 (Part 1):2016 with Amendments 1 and 2.

## 1. Mission and hard rules
Produce a code-grounded 3D model, the IS 800 member / connection / Section 12 checks and the report.
* **Loads are RETRIEVED live every job** (IS 875, IS 1893) into `cfg['load_plan']` with evidence; the
  engine never substitutes a foreign code or a remembered value.
* **Every check is grounded** in the RAG and cited by clause (IS 800 clause numbers, IS 1893 / IS 875
  clause and table numbers).
* **Units are explicit**: `cfg['units']`, N / mm / MPa in the engine, kN/m2 for area loads,
  `story_forces_units` 'N' or 'kN'.

## 2. RAG collections
| Collection | Contains | Use it for |
|---|---|---|
| `engineering_standards_IS800` | IS 800:2007 | member limit states, connections, Section 12 |
| `engineering_standards_IS808` | IS 808:2021 | section dimensions and properties |
| `engineering_standards_IS816`, `IS9595`, `IS4000` | welding, weld procedures, HSFG bolts | connections |
| `engineering_standards_IS1161`, `IS2062` | tubes, structural steel | grades, yield strength by thickness |
| `engineering_standards_IS875_P1` … `P5` | IS 875 Parts 1-5 | dead, imposed, wind, snow, combinations |
| `engineering_standards_IS1893` | IS 1893 (Part 1):2016 | zone, I, R, spectrum, analysis, drift |
| `steel_design_examples` | worked examples | method only |
| `opensees_buildings_3d`, `openseespy_documentation`, `opensees_documentation` | modelling | nearest model, API |

## 3. Workflow
**Phase 0 — scope.** Storeys and heights; plan grid; occupancy and area (I, imposed loads); lateral system per
direction (IS 1893 Table 9; per-direction R via `system_x` / `system_y`, `R_x` / `R_y`); bases; site: zone
(Annex E, else Fig. 1 at the site), soil type, basic wind speed (IS 875-3 Annex A or Fig. 1 at the site
coordinates; the ruling R5 site proxy only when the town is not tabulated), terrain category, cyclone belt and the
6.3.4 structure class. Re-entrant plan (15 % test)? Then the deck stiffness is an input. Separate units? Then
`pipeline.design_units`.

**Phase 1 — cfg and builder.** Compose `cfg` (section 5) and `cfg["custom_build"]` (copy the structure of
`example_build.py`; retrieve a similar model from `opensees_buildings_3d`). Columns strong axis in the frame
plane; girders both ways on every level.

**Phase 2 — loads.** Retrieve IS 875 / IS 1893 values; compute the seismic weight and ESM story forces from the
model (`engine3d.esm_from_model`); write `load_plan` (seismic_summary, story_forces, wind_summary,
retrieval, `combinations: "auto"`).

**Phase 3 — pipeline.** `pipeline.design_and_report(name, cfg)`: preflight, analysis gates (RSA per IS 1893
7.7.1, drift 0.004 h, 7.11.2 R x drift, serviceability), generated combinations, per-combination forces,
IS 800 member checks, Section 12 checks, report.

**Phase 4 — verify and design connections.** Check the governing results against the RAG; supply the inputs
the framework needs (LLT per moment sign, K factors, connection geometry); design every connection TYPE
with `india_connections` and write its checks.

**Phase 5 — resize, reconcile, finish.** Resize any failing group, re-run, then `consistency.check(name)`,
`report.build_report(name)`, and the closing note.

## 5. cfg keys (engine N-mm) — index
Every optional key is backward compatible; AGENT_START explains the ones with engineering consequences.
* **Job and units:** `units` ('N-mm' or 'm'), `jurisdiction` ('india'; India is also inferred from the load plan),
  `arch` (free-text description, read by the consistency rules), `notes`.
* **Geometry:** `NX`, `NY`, `SX`, `SY` (mm), `heights` (mm; `story_heights` is an alias), `xcoords` / `ycoords`,
  `skew`, `base`, `plan` f(k, NX, NY) -> present nodes, `custom_build`; `example_build` hooks `col_sec` /
  `beam_sec` f(...) -> section and `col_strong` f(i, j, NX, NY) -> strong axis; `custom_sections` (built-up
  boxes); frame_build: `gold`, `moment_lines`, `default_strong`, `col` / `beam` / `brace` fallbacks; `roof_planes`,
  `roof_regions`, `roof_levels`, `envelope`, `omit_beams_at`, `stepped_bases`; EBF `ebf_links`.
* **Model declaration:** `model` = {'bases', 'joints', 'gravity'} (hard gate); `releases` f(i, j, k, dirn) ->
  (relz, rely); `sway_frame`; `lean_gravity`; `beam_framing`; `demand_nseg`; `self_weight` (default True).
* **System and seismic:** `system` (IS 1893 Table 9 name), `system_x` / `system_y`, `R_x` / `R_y`,
  `R_source` / `R_cite` (provenance of a declared R), `occupancy` = {use | uses, persons | area_m2 +
  occupant_load_m2_per_person, educational, hospital, food_storage, assembly, lifeline, important} (Table 8;
  a list = mixed occupancy, the larger I governs), `seis` = {Z, zone, I, R, soil} (IS 1893 values only),
  `zone` / `seismic_zone` / `Z` (aliases read by the zone gate), `analyses` (['RSA'] where 7.7.1 requires it),
  `brace_config`, `diaphragm`, `diaphragm_by_level`, `diaphragm_7_6_4`, `lateral_lines`, `diaphragm_stiffness`,
  `flexible_diaphragm_analysis`, `flexible_diaphragm_eor`, `Jm_by_level`, `nodal_masses`, `extra_mass_floors`,
  `partition_seismic_kNm2`, `partitions` (False removes partitions from W), `irregular`, `regular`,
  `torsion_ratio`, `in_plane_discontinuity`, `weak_storey`, `out_of_plane_offset`, `nonparallel`,
  `soft_storey_indices`, `soft_storey_exempt`, `drift_exempt_stories`, `vertical_eq`, `long_span`, `overhang` /
  `large_overhang`, `prestressed`, `no_seismic` (a job with no earthquake family — justify it), `drift_limit`,
  `drift_limit_rag_cite`, `is1893_drift_factor`, `wind_drift_limit`, `adjacent_units` (7.11.3).
* **Gravity loads (kN/m2):** `D_floor`, `D_roof`, `L_floor`, `Lr`, `D_by_level`, `L_by_level`,
  `partition_load_kNm2`, `clad`, `snow`, `snow_partial`, `superimposed_dead_kNm2`; `floor_system` ('one-way' |
  'two-way') with `deck_span` ('X' | 'Y') and `secondary_spacing_mm`; `storage` / `storage_levels` +
  `storage_height_m` (or `storage_height_assumption_m` with `storage_height_assumption_cite`,
  `storage_height_cite`, `storage_height_source`); `column_imposed_load_reduction` (opt-in IS 875-2 3.2.1 for
  columns; never applied in earthquake combinations, IS 875-5 8.1); point loads `nodal_dead_loads`,
  `nodal_imposed_loads`, `nodal_snow_loads`; `ponding`; `notional_loads` (default True: IS 800 4.3.6).
* **Wind:** `load_plan.wind_summary` / `member_wind` (AGENT_START), `roof_pitch_deg` (low-rise / portal: member
  wind required), `ridge` = {axis, coord_mm}, `terrain_upwind_slope_deg`, `k1_class`, `wind_structure_class`,
  `cyclone_belt`, `member_wind_not_required` (with reason); building length for l/w: `building_length_m` (+
  `building_length_cite` / `length_cite`), or `building_length_assumption_m` + `building_length_assumption_cite` /
  `length_assumption_cite`, or `bay_spacing_m` / `bay_y` / `frame_spacing_m` x `n_bays_length` / `n_frames` with
  `building_length_derive_cite`. Site: `town` / `site_town` / `city`; a bare cfg `Vb` / `Z` / `zone` without its
  source record is refused; the ruling R5 site proxy may also be given as flat keys `site_proxy: True`,
  `site_proxy_town` / `proxy_town`, `site_proxy_distance_km` / `proxy_distance_km`, `site_proxy_cite` /
  `proxy_cite`, `site_proxy_source` / `proxy_source`, `site_proxy_verify`.
* **Members:** `steel_grade`, `brace_grade`, `brace_process`, `tube_grade`, `tube_process`, `grade_by_section`,
  `member_overrides`, `K_factors`, `LLT_sag_mm`, `LLT_hog_mm`, `beam_axial_negligible_ratio`,
  `secondary_members`, `composite_scope`, `composite_floor` / `composite` (declares a composite floor: the
  bare-steel scope record is then required), `construction_stage`.
* **Serviceability (IS 800 Table 6):** `building_type` ('industrial' selects the industrial rows),
  `cladding_brittle` (H/500 instead of H/300), `finishes_susceptible_to_cracking` (default True: span/360),
  `deflection_key_roof` (a Table 6 row key for roof members, e.g. 'rafter_profiled_sheeting' = span/180).
* **Connections and Section 12:** `connections` (AGENT_START), `section12_inputs` (the pipeline adds zone, I,
  `height_m`, occupancy ...), `apply_is18168`, `is18168_table2`, `scwb_pu_basis`, `eor_weld_exception`,
  `column_lateral_support_both_flanges`, `collector_basis`, `panel_zone_doubler_t_mm` (doubler already in the
  model), `end_plate_capacity_N` / `end_plate_Rn` with `end_plate_cite` / `end_plate_Rn_cite` and
  `end_plate_source` / `end_plate_Rn_source` (an EOR end-plate capacity, cited).
* **Cranes and erection:** `crane` / `cranes`, `roof_bracing`, `braces_after_dead_load`,
  `braces_after_superimposed_dead`.
* **QA records:** `delegated_design`, `vibration_screen`, `eor_assumptions`, `load_plan` (section 6).
* **Optional report figures** (off by default; set, then re-render with `report.build_report`):
  `force_diagrams`, `force_summary`, `mode_figures`, `deformed_shape_figure`, `section_color_figure`,
  `appendix_case_figures`.
* **Multi-unit jobs:** `pipeline.design_units(name, {unit: cfg}, joints=[...])` — one cfg per unit (AGENT_START).
Keys with a leading underscore are engine-private caches; never set them. Legacy (non-India) keys are listed in the
repository README.

## 6. Load plan and combinations
`load_plan = {'story_forces_units': 'N', 'seismic_summary': {...}, 'story_forces': {'EQ_X': ..., 'EQ_Y': ...,
'W_X': ..., 'W_Y': ...}, 'wind_summary': {...}, 'member_wind': {...}, 'retrieval': [...],
'combinations': 'auto'}`.

The generated set (`india_combos.expand_combinations`): IS 800 Table 4 (1.5DL + 1.5LL; 1.2DL + 1.2LL +-
1.2EL/WL; 1.2DL + 1.2LL +- 0.6WL; 1.5DL +- 1.5EL/WL; 0.9DL +- 1.5EL/WL; crane rows), both signs, IS 1893
6.3.2 orthogonal and 6.3.3.1 vertical components where required, 7.8.2 design eccentricity (two
variants), IS 800 12.2.3 (2.5 EL, columns and connections), IS 800 4.3.6 notional loads, member-level wind
patterns, crane load patterns, and serviceability rows. Each combination is analysed as one factored
second-order case (gravity by Newton P-Delta, laterals as linear increments on that state); RSA forces are
added per direction with the combination factor.

## 7. Checks and acceptance
* Members: IS 800 7.1.2, 8.2.1 / 8.2.2, 8.4, 6.2-6.4, 9.3.1 and 9.3.2.2 per combination with concurrent
  forces (sequence and hand values in `IS800_WORKED_METHOD.md`).
* Section 12: per system (OCBF IS 800 12.7, SCBF IS 800 12.8, EBF with IS 18168 11 / 12.3 on the declared
  `info['links']`, OMF IS 800 12.10, SMF IS 800 12.11, bases IS 800 12.12, splices IS 800 12.5.2 / IS 18168 7.5).
* Connections: IS 800 Section 10 and 7.4.
* Drift and serviceability: IS 1893 7.11.1.1 (0.004 h), 7.11.2, 7.11.3; IS 800 Table 6.
* Done = `design_status(...)['status'] == 'complete'`: every check numeric and passing, every input
  sourced (retrieval rows with stored `hit_file` + `quote`, found:false rows with an EOR assumption), no example
  labels, consistency clean, report free of foreign-code residue. The engine's verdict is `STATUS.engine.md`.

## 8. Deliverables
`report.html` (13 chapters), `design/calc_package.json` (members, connections, capacity_design,
collectors, deformation compatibility, gates, design_status), the member schedule and combination forces,
figures, and `cfg.py`.

## 9. Caveats — state them in the report
* Elastic analysis; the Section 12 detailing makes the R-based design valid.
* Bare-centreline models run flexible (no slab or non-structural stiffness).
* Diaphragm idealisation as declared (per level with `diaphragm_by_level`): rigid (constraint + 7.8.2 torsion) or
  flexible (tributary distribution; collectors accumulate the deck shear along each line into the braced / frame bays);
  a re-entrant plan adds the Table 5(ii) flexible-deck 3-D run with the declared deck stiffness (isotropic
  membrane; state the stiffness source).
* Pitched roofs at their true slope only through `roof_planes`; units of one job are separate models joined only
  by the 7.11.3 separation check.
* Values the corpus could not confirm are disclosed with their basis.

## 10. Connections — designed here, not delegated
Every connection TYPE: beam-to-column (shear / moment), brace-to-gusset, splice, base plate and anchors,
collector connections. Use capacity-design forces for Section 12 systems (IS 800 12.7.3.1 / 12.8.3.1 /
12.11.2.1) and record the components (bolt size, grade and number, weld size and length, plate thickness).

## 11. Optimisation — opt-in
Offer it; if accepted, resize in groups, re-run, present, and wait for the user before updating the report.

## 12. Numerical self-consistency
`consistency.check(name)` verifies that every D/C equals demand / capacity, one value per quantity, no
literal D/C, no zero-demand element, RAG evidence behind every cited value, and that the report and
contract carry no foreign-code residue.
