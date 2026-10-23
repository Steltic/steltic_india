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

## Second wave (2026-10): first wave merged, the study run on the first-wave golds

`origin/main` (db62c44: the whole first wave, with 9f3cd6f and 64e5b3e) is merged into this branch (14762fe, no
conflicts). The four PEB study jobs in the study area were replaced by copies of the first-wave golds (collateral /
PV declared apart, IN_Ex1 two sag-rod lines, IN_Ex2 purlins at 1.05 m, IN_Ex4 purlins and fly braces at 1.25 m,
IN_Ex3 crane bracket), and the study was run on them. Each problem a study run hit is fixed here with a test.

### Study runner (`scripts/peb_lever_study.py`)
- `--stop-after-min N`: no new variant is started after N minutes, so a long study runs as resumable chunks under the
  2 h limit of a background command (`--resume` continues; `study.json` records `stopped_before`).
- `--ladder short`: strict, each lever alone, every compliant lever together (from the strict design), the market
  bundle (every lever and the market loads, from the compliant design) and solar-ready. The one-lever-at-a-time
  cumulative steps are dropped; the waterfall and the tables show the three-step ladder. A resumed study keeps its
  ladder. Used for the second-wave run (the full ladder was estimated at more than 12 h on the shared box; see Results).
- `--control`: the strict rules again from the strict design. What the sizer still finds with no lever is its
  resolution; a lever's change smaller than that is within the sizer's noise.
- The solar-ready variant is sized on a copy of IN_Ex1 with the IN_Ex5 wind basis appended (`JOB_SPECS[...]['solar']`):
  with the PV mass the first transverse mode drops below 1.0 Hz, and IN_Ex5 then applies the IS 875 (Part 3):2015
  10.2 gust-factor along-wind load (9.1 (b)). Sized on IN_Ex1 alone (no gust factor) it was instead stiffened to stay
  above 1.0 Hz, a different basis from the PV check it sits beside in the IN_Ex5 report.
- The ordinary-frame route outside Zone II sets `cfg['study_allow_banned_system']` (below), so the R = 3 comparison
  of IN_Ex2 (Zone III) and IN_Ex4 (Zone IV) produces a design; before, the preflight blocked the run.

### Auto-sizer (`steel_engine/peb_autosize.py`), each found by a study run
- Two resized constants on one label (IN_Ex1: gable corner and wind columns both at the lightest plates) stopped the
  next frozen-force model, which maps members to constants by label: such a proposal is now infeasible.
- Declared secondary struts on a resized section (IN_Ex1 / IN_Ex3: the gable rafter is also the roof-girder chord,
  `cfg['secondary_members']` kind 'strut') are checked locally with the candidate section and the engine's
  `secondary_strut_checks`; secondary members enter the governing list of a full run and a failed strut tightens its
  own margin.
- The market bundle takes the sheeting as the purlin's free-flange brace; the first-wave CFS engine's IS 801 8.2
  brace rows divide by the brace interval (ZeroDivisionError on every candidate). With the sheeting as the brace those
  rows are not produced for the purlin; a CFS error row now reads as 'no result' and the 'no purlin passes' message
  carries the first CFS error.
- IS 875-3 9.1 (b): without a gust factor the first transverse mode must stay at or above 1.0 Hz (dynamic_wind
  gate). The local model predicts it from the frame flexibility (f1 / sqrt(flexibility ratio), mass held) and a
  failed gate tightens its margin. IN_Ex1's strict design is at 1.03 Hz; the market bundle found nothing lighter
  until this was in.
- A check the variant waives (the compression row of a tension-only rod, D/C about 134) is neither the governing
  check nor fed back as a failure.
- Strengthen-only mode keeps the knee diagonal stiffener at least the gold's (it came out 6 mm against 16 mm).
- SMRF jobs (IN_Ex2, IN_Ex4): the IS 800 12.11.3.2 strong-column / weak-beam rows and the 12.11.2.3 / 12.11.2.4
  panel-zone rows of a run are re-checked locally with the candidate face sections (the engine's own helpers, the
  run's column axial load, column shear and doubler) and each failure tightens its own margin. Before, every full run
  of the IN_Ex2 strict sizing failed one of them and only a generic margin moved.

- A joint bolted to a column flange (IN_Ex2's canopy-beam root) checks the column flange at the bolt rows with the
  candidate column (peb_checks.splice_records' own row) in the local splice sizing; before, a lighter column failed
  that row in every full run.
- A failed sway tightens its margin by the overshoot (at least 0.03) instead of 0.03 a run.
- `--init-margins` (study) / `init_margins` (autosize): starting margins for a job whose full runs keep overshooting
  the local predictions.
- The ordinary-braced-frame brace sizing (OMRF_R3 route) skips IS 808 sections with no warping constant in the table
  (WPB200X200X37.34: the engine cannot evaluate the brace's LTB, the run stayed open); the local model registers the
  end-station label of a candidate taper before reading it (a KeyError stopped the IN_Ex2 OMRF_R3 sizing).
- The market bundle keeps the job's compression bracing where the rods alone found no passing design (IN_Ex3: with
  rods the shed is torsionally irregular and its torsional mode is not below the first X mode, IS 1893 Table 5(i)
  (Amd 2)); its note says so.

### Engine (`steel_engine/pipeline.py`)
- `study_zone_ban_as_warning`: `cfg['study_allow_banned_system'] = '<why>'` turns only the preflight zone-ban ERROR
  (IS 1893 (Part 1) Table 9 Note 1, IS 800 12.7.1.1 / 12.10.1.1) into a 'STUDY ONLY' warning, so a cost-of-compliance
  run of an ordinary frame in Zone III-V goes through the analysis. Nothing else is relaxed: the design status keeps
  the ban and the Section 12 zone gate fails, so such a run is never COMPLETE. No job sets the key.

### Results (second-wave run, 2026-10-23)

Study area `/home/claude/gold_var` (not in the repo): jobs `jobs_hr/` (copies of the first-wave golds), study
`study/` (`index.html`, `study_all.json`, `study_tables.md`, per job `study.html`, `study.csv`, `study.json`),
CFS engine `cfs_sw2/` (steltic_CFS_india origin/main 1e7220e). Short ladder with the control variant, every variant
verified by a full engine run. kg/m² of plan (primary + bracing + crane + canopy + purlins / girts + connection
plates); in brackets the change from the strict design.

| | gold | strict | control | C1 gradient | deliverable joints | H/150 + dado | thin G350 | keys: analysis V | collateral in 0.9DL | rods | R = 3 | all compliant | market bundle | solar-ready |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ex1 | 34.55 | 31.54 | 31.18 (-0.36) | 31.10 (-0.44) | 30.23 (-1.31) | 31.70 (+0.16) | 29.97 (-1.57) | 30.79 (-0.75) | 31.18 (-0.36) | 30.53 (-1.01) | n/a | 29.57 (-1.97) | 25.57 (-5.97) | 36.89 (+2.34 on the gold) |
| Ex2 | 56.17 | 50.71 | 50.71 (+0.00) | 50.71 (+0.00) | n/a | 60.07 (+9.36) | 49.22 (-1.49) | 50.71 (+0.00) | 48.74 (-1.97) | n/a | 50.97 (+0.26) | 59.31 (+8.60) | 42.01 (-8.70) |  |
| Ex3 | 56.97 | 50.20 | 50.10 (-0.10) | 50.10 (-0.10) | 49.68 (-0.52) | n/a | 49.91 (-0.29) | 49.49 (-0.71) | 49.97 (-0.23) | no pass | n/a | 49.35 (-0.85) | 46.21 (-3.99) |  |
| Ex4 | 63.78 | 55.63 | 55.06 (-0.57) | 54.91 (-0.72) | n/a | 55.06 (-0.57) | 54.95 (-0.68) | 55.63 (+0.00) | 54.55 (-1.08) | n/a | 49.54 (-6.09) | 54.79 (-0.84) | 46.84 (-8.79) |  |

- The strict design is the gold re-sized by the sizer under the owner rulings; its distance from the gold (Ex1
  -3.0, Ex2 -5.5, Ex3 -6.8, Ex4 -8.2 kg/m²) is the sizer's lightening, not a lever. The control shows the sizer's
  resolution on each job (Ex1 0.36, Ex3 0.10, Ex4 0.57 kg/m²; Ex2 0: the sizer stops at the first heavier passing
  design, so on Ex2 it often keeps the strict sizes); a lever inside it is not a clear effect.
- Ex2's H/150 + dado-top reading is heavier, not lighter: with fixed bases and a 13 m eave the column moves more at
  the 3 m dado top than dado height / 240 (1.08 on the strict design), and the sizer stiffened the frame to pass it.
  Its +9.36 kg/m² (and the +8.60 of 'all compliant', which includes it) is an upper bound: the sizer's flexibility
  predictor is for the eave sway, not the dado-top displacement of a fixed-base column, and it over-stiffened.
- Ex2's ordinary-frame route: in three attempts the sizer found no lighter ordinary frame than the SMRF sizes (every
  lighter proposal, down to 490 t against 526 t, failed H/240 sway at the brick dado or a rafter splice in the full
  run), so the R = 3 row is the SMRF sizes with ordinary braced frame braces (+0.26 kg/m², KL/r <= 120). The SMRF-only
  checks were binding in the SMRF baseline (panel zone 0.997, SCWB 0.994, IS 18168 7.2 0.982), so some saving is
  likely; this sizer does not resolve it on the multi-span frame.
- Ex3: tension rods give no passing design (torsional irregularity, IS 1893 Table 5(i) (Amd 2), and the 7.7.1
  dynamic-analysis requirement that follows); the market bundle keeps the compression bracing. The H/150 + dado and
  R = 3 levers do not apply (no dado; ordinary frames as briefed).
- Solar-ready (IN_Ex1 + 0.15 kN/m² PV, strengthen-only, IN_Ex5 wind basis): +2.34 kg/m² on the gold (5.25 t):
  deeper main columns, haunches and rafter bodies, 50 mm knee end plates and shear keys, LZ230X75X20X2.3 purlins.
- IN_Ex8 (not a PEB job, not sized by this auto-sizer): `/home/claude/gold_var/r3/ex8_r3.py` re-runs the gold as an
  ordinary moment frame (R = 3, no IS 18168) and searches the lightest sections of the same families group by group,
  for both routes: lightest SMRF 69.34 kg/m² (only the eave beam lighter, MB125; SCWB 12.11.3.2 holds the box column
  at 25 mm and IS 18168 Table 2 the rafter), lightest ordinary frame 48.27 kg/m² (BOX400X400X14, WPB600X300X128.79,
  MB150); gold 72.06 kg/m².
- Report-side files written for the HR reports (schemas in the second-wave brief): `compliance_comparison.json` in
  the IN_Ex2, IN_Ex4 and IN_Ex8 gold folders and `strengthening_option.json` in IN_Ex5 (writer:
  `/home/claude/gold_var/r3/item13.py`).
- Ex1 and Ex3 were sized before the SMRF-only fixes (SCWB, panel zone, canopy root), which do not apply to them;
  every row is a design that passed its full run.
- Run time of the final variants: Ex1 42 min, Ex2 121 min, Ex3 32 min, Ex4 58 min of one slot (plus the attempts
  the fixes above replaced). The short ladder was chosen after timing IN_Ex1, when Ex2 / Ex4 were estimated at about
  four times IN_Ex1 per variant and the box was shared by three other agents (an estimate above 12 h of wall time);
  measured, the one-lever-at-a-time cumulative steps would add about 2.5 h of slot time and can be run with
  `--ladder full` in a fresh study folder.

### Tests (second wave)
- `tests/test_peb_levers_second_wave.py` (27 tests): the time budget and resume, the short ladder (variants,
  waterfall, tables, caption, no switch on resume), the control variant, the shared-label refusal, the local strut,
  SCWB and panel-zone checks against the engine's own functions, the canopy-root column flange, the market purlin
  bracing patch and CFS error rows, the frequency predictor and its feedback, waived checks out of the governing
  check, the knee diagonal floor, the OCBF brace without Cw, the taper station labels, the sway overshoot feedback,
  the starting margins, the solar job and its IN_Ex5 wind block, the study zone-ban key and the OMRF patch.
- `tests/test_peb_levers_2026_10.py`: the strengthen-only floor test also checks the knee diagonal stiffener.
