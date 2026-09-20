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
direction (IS 1893 Table 9); bases; site: zone (Annex E), soil type, basic wind speed (IS 875-3 Annex A or
Fig. 1 at the site coordinates), terrain category, cyclone belt.

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

## 5. cfg keys (engine N-mm)
* `units` ('N-mm' or 'm'), `arch`, `NX`, `NY`, `SX`, `SY` (mm), `heights` (mm), `xcoords` / `ycoords`
  (mm, optional), `base`.
* `model` = {'bases', 'joints', 'gravity'} (hard gate); `releases` f(i, j, k, dirn) -> (relz, rely).
* `system` (IS 1893 Table 9 name), `steel_grade`, `brace_grade`, `brace_process`, `occupancy`,
  `analyses` (['RSA'] where 7.7.1 requires it), `brace_config`.
* `D_floor`, `D_roof`, `L_floor`, `Lr`, `partition_load_kNm2`, `clad`, `snow` (kN/m2);
  `floor_system` ('one-way' | 'two-way') with `deck_span` ('X' | 'Y') for one-way.
* `diaphragm` ('rigid'), `drift_exempt_stories` {story: reason}, `adjacent_units` (7.11.3).
* `crane` (see AGENT_START), `secondary_members`, `member_wind_not_required` (with reason).
* `seis`: `Z`, `zone`, `I`, `R`, `soil` — the IS 1893 values (no foreign-code site coefficients).
* `load_plan` (section 6).

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
* Section 12: per system (OCBF IS 800 12.7, SCBF IS 800 12.8, EBF with IS 18168, OMF IS 800 12.10,
  SMF IS 800 12.11, bases IS 800 12.12).
* Connections: IS 800 Section 10 and 7.4.
* Drift and serviceability: IS 1893 7.11.1.1 (0.004 h), 7.11.2, 7.11.3; IS 800 Table 6.
* Done = `design_status(...)['status'] == 'complete'`: every check numeric and passing, every input
  sourced, no example labels, consistency clean, report free of foreign-code residue.

## 8. Deliverables
`report.html` (13 chapters), `design/calc_package.json` (members, connections, capacity_design,
collectors, deformation compatibility, gates, design_status), the member schedule and combination forces,
figures, and `cfg.py`.

## 9. Caveats — state them in the report
* Elastic analysis; the Section 12 detailing makes the R-based design valid.
* Bare-centreline models run flexible (no slab or non-structural stiffness).
* Rigid diaphragm only; flexible / semi-rigid diaphragms are refused.
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
