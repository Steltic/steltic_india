# steltic-india — 2026-10: PEB release (welded and web-tapered portal frames)

Branch `fix/2026-10-peb-tapered`. It ships in one PR with the 2026-10 brief renumbering commit before it
(`CHANGES_2026-10-peb-briefs.md`, prepared as `fix/2026-10-peb-briefs`, which was never pushed on its own).
This release makes the five PEB briefs (IN_Ex1 … IN_Ex5) runnable. Their gold solutions are in the gold pack.
Scope: `docs/PEB_TAPERED_SCOPE.md`.

**Existing jobs are unchanged.** The 19 HR gold runs and the 15 CFS gold runs of the 2026-09-27 pack were re-run on
this branch. Every one of them reproduces:
- `design_status` and the number of reasons;
- the governing member and connection D/C;
- every Section 12 D/C and ok flag;
- W and the analysis gates.

The only differences are run-to-run tie-breaks between equal combinations, which a second run of the same engine
also shows. The evidence is in the gold pack, `REGRESSION_2026-10.md`.

## Owner decisions applied (2026-10)
| Decision | Ruling | How the engine applies it |
|---|---|---|
| D-T1 stability of tapered members | accepted | LTB segment by segment between restraints, each station with its own section, C1 = 1.0 (conservative; the moment-gradient C1 is not used). Major-axis buckling over the member length (base to knee, knee to apex) with the smallest section of the member. lambda_cr of the stepped model by IS 800 4.6.2(b) |
| D-T2 Zones III-V | route B: IS 18168:2023 adopted voluntarily | `cfg['apply_is18168'] = True`. E350 B0 allowed (5.2(a)), Table 2 limits, Ry, 9.3 fixed bases (1.1 Ry Mpc), 6.5 splices, 8.4 knees at 1.1 Ry Mp (`peb_checks.knee_records`; the general Section 12 row stays at the IS 800 1.2 Mp) |
| D-T3 monosymmetric sections | doubly symmetric only | `welded_I` / `tapered_I` have one flange size |
| D-T4 tension-only rods | not used in the golds | CHS / WPB braces designed for compression |
| D-T5 purlins and girts | CFS engine (IS 801) | Lapped zed purlins in steltic_CFS_india; the governing rows are imported as `cfg['peb_secondary']` (re-hashed every run) |
| D-T6 scope of 12.4.2 | connection welds only | CJP at end plates, gussets and base stiffeners; flange-to-web welds are fillets |
| D-T7 Mp at a tapered joint face | the section at the joint face | Knees and apex are designed for 1.2 Mp of the face section in either sign; rafter splices for the factored moment of both signs (x 1.80 under IS 18168 6.5) |

## Engine
- **`sections.py`**
  - `custom_sections` types `welded_I` (`WI<D>X<bf>X<tf>X<tw>`) and `tapered_I` (`TI<D0>-<D1>X<bf>X<tf>X<tw>`).
  - Properties come from the plates, with a `plates` record.
- **`peb_build.py` (new): the stepped model.**
  - `column` (with per-chain `restraints`), `rafter_line` (from the roof-plane keys `rafter_members`,
    `rafter_members_by_line`, `gravity_lines`, `braced_lines`), `beam` (canopy cantilevers) and the station nodes.
  - Restraint overrides from `cfg['flange_braces']` (D-T1), splice records, and the face section at each joint.
- **`peb_checks.py` (new): the PEB checks.**
  - Splices: apex, rafter splice, canopy root, gravity-line end plates (HSFG, 12.4.1), in both signs of moment.
    `end_plate_layout` gives the bolt rows of a declared pattern (`symmetric` or one-sided) and the reverse-sign rows.
  - Knees, at the connection demand (D-T7 1.2 Mp; IS 18168 8.4 1.1 Ry Mp under route B): the end plate in both
    signs, the column flange at the bolt rows as a T-stub flange (`column_flange_t_mm`, the knee-zone flange plate)
    with the column web feeding the inner rows, and the column stiffeners at the rafter flange levels.
  - Apex under IS 18168: not less than 1.80 x the analysis moment (6.5).
  - The splice spec is looked up by section first (a gable-line apex), then by joint kind.
  - Flange (fly) braces: the IS 800 8.3.2 restraint force and the 7.5.1.2 angle check.
  - Frame stability: lambda_cr by 4.6.2(b), from three P-Delta solves.
  - Knees: panel shear with the diagonal stiffener, and flange stiffeners.
  - Steel take-off by group (primary, bracing, crane, canopy, secondary, connections). A `secondary_members` record
    may name its `group`.
- **`peb_outputs.py` (new): the four deliverables (scope 5.7).**
  - `design/reactions.csv`: unfactored, per basic case and support.
  - `design/bom.csv`: members, end plates (with their grade) and bolts counted from the bolt patterns, splices
    grouped by the spec that designs them, declared extra plates (`bom_plates`: rib stiffeners, knee-zone flange
    plates), base plates, anchors and shear keys, secondary members, then the take-off by category and kg/m2.
  - `design/anchor_bolt_plan.svg`, drawn to scale.
  - `model.std`: STAAD.Pro, in mm and kN, containing:
    - stepped TAPERED members, supports and releases;
    - the roof diaphragm as SLAVE commands to the level master;
    - DL and LL member loads, and EQ joint loads;
    - every engine combination made of DL, LL and EQ.
    - Member wind, crane and notional loads are not exported, and the file says so.
- **`peb_report.py` (new):** the PEB chapter of the report. It covers owner rulings, members, stations, restraints,
  knees and splices, stability, secondary members, tonnage and the deliverables.
- **`design_pipeline.py`**
  - Station checks for every stepped element, and the D-T1 overrides.
  - Face sections at the joints.
  - Import of the CFS secondary members.
  - The PEB block (`calc_package['peb']`).
  - The optional shear `V_N` on secondary struts (crane brackets).
  - `_combo_record`, shared by the package and the STAAD export.
  - Secondary struts may declare `LLT_mm`, the LTB length of a chord that the purlins hold in sagging.
- **`india_is800.py`**
  - The IS 800 3.7.2 (d) effective section used for compression of slender (class 4) sections.
  - Welded-section defaults.
  - `peb_buckling_section`.
- **`india_connections.end_plate_moment_capacity`**
  - The prying force is never negative (Q = a (Te - K) >= 0): thick plates no longer lose capacity.
  - Optional web tension (`web_t_mm`, `web_fy_MPa`, `hf_mm`): a row inside the flange is capped at be tw fy /
    gamma_m0. Only PEB end plates declare it; no existing gold uses an end plate.
- **`india_is800_s12.py`**
  - `material_gate`: IS 18168 5.2(a) for E275 to E350 where IS 18168 applies. E250 keeps the IS 800 E250B row
    unchanged.
  - Joint checks use the face section.
  - `joints_from_model` skips released column ends.
  - Column checks use the PEB member lengths.
- **`engine3d.py`**
  - Column end releases (`add_column(..., releases=)`).
  - Crane rail spread (opt-in, `cfg['crane']['check_rail_spread']`): the change of the rail gauge against the IS 800
    Table 6 limit, reported in `crane_sway.rail_spread` (not a gate).
  - The build resets the PEB registry.
  - Lifted purlin lines are excluded from `floor_beam_gaps`.
- **`roof_geometry.py`**
  - The rafter-member hooks and the `braced_lines` tie.
  - `TIES`: the last diaphragm tie per level, read by the STAAD export.
- **`static_model.py`, `india_combos.py`:** a member-wind pattern may carry `nodal_loads` (the attached-canopy wind,
  with the sign it belongs to); they are applied with the pattern.
- **`report_india.py`:** inserts the PEB chapter after chapter 6.
- **`contract/AGENT_START.md`:** the PEB cfg keys, including the joint specs: the end-plate dict (tension-half rows,
  web tension keys), the apex / splice / canopy-root lookup with `symmetric`, `plate_b_mm`, `bom_plates` and the
  column-flange keys, the knee end plate under `beam_column`, `knee_panel`, and the demand of each joint.

## Documents
- `docs/PEB_LIMITATIONS.md` (new): the modelling assumptions, what IS 800 and the corpus do not cover and how each
  gap is handled, and the owner decisions.

## Briefs and pickers
- **IN_Ex1:** the length is 75 m (11 frame lines at 7.5 m make 10 bays; the brief said 72 m).
- **IN_Ex2 and IN_Ex4:**
  - Base fixity and the purlin and girt spacing are the design's choice, stated with the reason. Under route B the
    pinned bases of the first wording sway past H/240.
  - The R5 site-proxy route is stated for the zone and Vb.
  - The seismic method is the one IS 1893 7.7.1 requires; the ESM is not permitted in Zones III and IV.
  - IN_Ex2 also checks the first mode against IS 875-3 9.1.
  - IN_Ex2: end plates E250, or E350 B0 where a moment end plate needs it (IS 18168 5.2(a)).
- **IN_Ex3:** the rail is 0.75 m inside the column line. A 22.5 m crane in a 24 m grid gives 0.75 m; the brief said
  0.50 m.
- **Pickers:** `frontend/index.html` offers in1 … in20; `test_buildings/README_INDIA.md` and
  `RENUMBERING_2026-10.md` are updated.

## Tests
- `tests/test_peb_2026_10.py` (24 tests) runs a small tapered portal (`tests/_peb_fixture.py`) through the whole
  pipeline in about 3 s, with and without declared connections. It covers:
  - labels and properties;
  - the effective section;
  - the IS 18168 material gate, with E250 unchanged;
  - tonnage groups;
  - stations, splices, lambda_cr and the D-T1 restraint lengths;
  - the schedule, reactions, BOM and anchor plan;
  - a STAAD parse-back: joint and member counts, and the DL and LL member loads equal the roof plan load to 0.1 %;
  - end-plate patterns (symmetric, one-sided, shared rows) and the reverse-sign demand;
  - the knee rows at the connection demand (end plate both signs, column flange, stiffeners), the splice reverse
    rows, and the BOM bolt and plate counts;
  - the end-plate web-tension cap and the no-negative-prying rule;
  - the opt-in crane rail spread.
  An autouse fixture runs each test in N-mm: welded and tapered sections are mm-only, and a kip-in preflight test
  elsewhere in the suite leaves the unit system switched.
- `tests/test_india_contract.py`: the picker now lists in1 … in20.

## Not in this release
- The variations study on IN_Ex1 (scope deliverable 7.4): the hub's PEB templates exist; the study has not been run.
- Nonlinear analysis of tapered frames (scope section 9). The variations metrics mark them not representable.
- The STAAD export leaves member wind, crane and notional loads to the user.
