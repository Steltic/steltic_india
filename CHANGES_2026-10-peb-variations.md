# steltic-india — 2026-10: PEB variations study (PEB-LEVERS)

Branch `feat/2026-10-peb-variations` (from main, with `fix/2026-10-first-wave` merged in up to 54e7463). It adds the switches a
design engineer needs to see how each current Indian PEB practice or code reading changes the steel of a shed, a
deterministic auto-sizer that re-sizes a PEB job under any set of switches, and the study runner that tabulates the
result for the four PEB golds (IN_Ex1 … IN_Ex4).

**Existing jobs are unchanged.** Every switch defaults to the owner ruling of the PEB release. The four PEB golds
re-run with the defaults give a `calc_package.json` identical to the reference engine (`fix/2026-10-first-wave`,
6bb60cc and again at 54e7463) and an identical `bom.csv` (no report, `PYTHONHASHSEED=0` on both sides so that ties
between equal combinations break the same way).

## Switches: `cfg['peb_rules']` (`steel_engine/peb_levers.py`)
| Switch | Default (gold ruling) | Alternative | Status of the alternative |
|---|---|---|---|
| `joint_demand` | `1.2Mp` (D-T7) | `deliverable`: IS 800 12.10.2.1, min(1.2 Mp, 1.2 x the largest factored joint moment over every strength combination incl. the 12.2.3 rows); `deliverable_factor` 1.0 gives min(1.2 Mp, M) | compliant, OMF only; SMRF / IS 18168 joints unchanged |
| `ltb_c1` | `unity` (D-T1) | `gradient`: IS 800 Table 42 C1 (K = 1) from the end moments of each restrained length, per combination and sign | compliant |
| `sway_limit` | `H240_brittle_dado` | `H150_with_dado_check` (+ `dado_height_mm`): eave H/150, column displacement at the dado top <= dado height / 240; `H150_no_dado_check` (market) | compliant; the second not compliant |
| `base_shear_key` | `1.2Vd` (O1) | `analysis`: the case's own factored base shear (12.2.3 rows included) | a reading the O1 ruling rejected |
| `bracing` | `compression` (D-T4) | `tension_rods`: round bars ROD<d>, tension only | Zone II OCBF only; NOT compliant with IS 800 12.1 / 12.7.2.1 / 12.7.2.3 |
| `purlins` | `IS811_Fy240` | `thin_G350`: generic thin lipped zeds, IS 277 grade 350 (CFS `cfs_generic_sections`) | compliant |
| `collateral_in_uplift` | `False` (first wave: collateral / PV out of the 0.9 DL rows) | `True`: folded into `D_roof` (the old treatment) | unconservative |

Brief-level variants of the study (not engine switches): the seismic route `OMRF_R3` (ordinary frames R 3 / R 4, no
IS 18168) with its code status from `peb_levers.seismic_route_status` (Zone II permitted; Zone III I <= 1 permitted by
IS 800 12.10.1.1 but not by IS 1893 Table 9 Note 1 — flagged; Zone IV-V not compliant), and the market-practice
bundle `peb_levers.MARKET_PRACTICE` (NOT COMPLIANT).

## Engine hooks (each marked `PEB-LEVERS:`; no effect without `peb_rules`)
- `peb_checks.knee_records` / `splice_records`: the deliverable joint demand at the knees and the apex (both signs).
- `design_pipeline`: the deliverable moment on the Section 12 OMF joint (`max_deliverable_moment_Nmm`, which
  `india_is800_s12` already honoured); the per-combination C1 map; the rod brace check; `peb_rules` passed to the
  Section 12 cfg; an opt-in dump of the element inputs (`design/peb_element_inputs.json`) for the auto-sizer.
- `india_is800.member_check_is800`: a per-combination, per-sign C1 (`c1_by_combo`) when given.
- `india_is800_s12.base_checks`: no 1.2 Vd floor under `base_shear_key` 'analysis'.
- `engine3d`: the Table 6 row under `sway_limit`; the dado-top displacement (Hermite interpolation of the column
  station nodes) and its gate.
- `peb_checks.tonnage`: a rod's take-off (the analysis bar is half the rod area: the X pair with both diagonals active
  has the stiffness of the one tension rod that acts).
- `pipeline.design_and_report`: validates the switches; `collateral_in_uplift` True folds collateral / PV into D_roof.

## Auto-sizer (`steel_engine/peb_autosize.py`) and study (`scripts/peb_lever_study.py`, `scripts/peb_lever_jobs.py`)
- Full runs in a child process (cfg.py executed with its section constants rewritten — an AST rewrite, so every
  derived quantity follows — the connection plates patched, the switches set; no report; design_status evaluated).
- Local sizing with the forces of the last run frozen: the exact member / station checks of every element (the
  engine's own functions on the dumped inputs), the knee / apex / splice end plates, the knee-zone column flange
  plate, the knee stiffeners and the base shear keys sized for the switch's demand, IS 18168 Table 2 / 12.11.3.1 /
  6.2 under route B, the sway / lambda_cr / rafter deflection predicted by a virtual-work flexibility ratio; coordinate
  descent over the tied plate dimensions (standard plates, the briefs' fabrication limits). A full run verifies every
  proposal; a failure tightens the margin of what failed.
- Purlins and girts: the job's CFS script re-run (child process, CFS engine first on the path) for the lightest passing
  zed of the family (IS 811 LZ at Fy 240, or the generic thin zeds `thin_Z_G350` of `cfs_generic_sections`).
- Strengthen-only mode (`autosize(..., floor=True)`): start from the gold, no plate dimension below the gold's, a gold
  joint (knee, splice, shear key) or purlin / girt kept while it passes, else the lightest that passes and is not
  thinner. The study's solar-ready variant (IN_Ex1 with cfg `D_roof_pv` 0.15 kN/m²) uses it, so its change from the
  gold is a strengthening of the published design, with the changed members listed.
- Study variants: the strict design (auto-sized from the gold under the owner rulings), each lever alone (from the
  strict design), the cumulative ladder (one lever added per step, each step from the previous one, in the order
  compliant levers / readings / not compliant / market loads; the last compliant step is "all compliant levers", the
  last step the market-practice bundle), and the solar-ready variant. A lever that does not apply is 'n/a'.
- Outputs per job: `study.json`, `study.csv`, `study.html` (self-contained, dark theme of the site, a stacked bar per
  variant and a waterfall of the cumulative ladder); `index.html`, `study_all.json` and `study_tables.md` over the
  jobs. The secondary-design results are cached per job (`secondary_cache.json`) so a resumed study does not redo them.

## Tests
- `tests/test_peb_levers_2026_10.py`: switch registry and validation; defaults change nothing (the mini portal with
  and without the default switches); each frame switch changes what it should (knee / apex / 12.10.2.1 demand, member
  D/C only, Table 6 row and dado check, base shear, rod check and take-off); the cfg rewrite; the auto-sizer's end
  plate equals the golds' helper; the local member and knee checks equal the engine's; on a small job the sizer
  returns a passing design no heavier than the start, the same on a second run; the strengthen-only floor (no step
  below the floor; under an added roof load a passing design with nothing lighter than the gold); the study's variant
  list and cumulative ladder.
- `tests/fixtures/peb_levers_mini/cfg.py`: the mini portal as a job script.

## Not in this release
- Base plates, anchors and base gussets are not resized (only shear keys); the taper layout, splice positions,
  purlin spacing and fly-brace layout are the job's.
