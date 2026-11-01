# steltic-india — 2026-10 third wave: the auto-sized PEB golds (IN_Ex1 … IN_Ex5)

Branch `fix/2026-10-third-peb-golds`, from main 44b74de. Owner decision (2026-10-30): adopt the auto-sized designs of
the PEB variations study (the "strict" variant: the owner rulings D-T1, D-T2, D-T4, D-T5, D-T7, O1, H/240 with a brick
dado, D8) as the published golds of IN_Ex1 … IN_Ex4; IN_Ex5 (rooftop PV on IN_Ex1 as built) follows the new IN_Ex1;
everything derived from them is re-based. The job folders (`cfg.py`, `secondary/secondary_is801.py`, IN_Ex5
`pv_check.py`) live in the gold area, not in this repo; this file records what changed in them.

## The new golds

How they were made: the October study's strict design of each job (`/home/claude/gold_var/study/<job>/strict/`)
re-run on this engine. With the column span moment counted (below) every one failed only on its gable wind and corner
columns, so those two constants were re-sized by the sizer with every other plate, every joint and every base plate
held (`hold_joints`, `size_base_plates: False`; a corner key follows its column under ruling O1), and each result
passed a full engine run. The design was then written into the job's `cfg.py` by hand: section constants, joint
plates and bolts, keys, the narrative cite / note texts and comments, and the plate take-off (now derived from the
sections: knee stiffener lengths, pinned gable base plates through `_base_pin`). A structural diff of the edited
`cfg['connections']` against the cfg the sizer verified shows only deliberate differences: `continuity_plate_t_mm`
set to the knee flange stiffener it describes (no check reads it for end-plate knees), the IN_Ex4 / IN_Ex2 knee CJP
web thickness set to the real 16 mm web (the sizer had kept 17), the IN_Ex3 knee shear bolts M24 like the knee bolts
(the sizer had kept M30). The purlins / girts the study chose are written into `secondary/secondary_is801.py`. Gold
runs: secondary design (CFS engine, main dcda6c2) then the harness, `PYTHONHASHSEED=0`.

| job | kg/m² old → new | worst strength ratio old → new (governing, new) | wind sway Y / limit old → new | storey drift / limit old → new | status old → new |
|---|---|---|---|---|---|
| Ex1 | 34.55 → **32.38** (-2.17) | 0.961 → 0.996 (lateral_col-WI862X225X12X8, IS 800 9.3 interaction / member resistance) | 0.939 → 0.973 | 0.266 → 0.272 | COMPLETE → COMPLETE |
| Ex2 | 56.17 → **52.69** (-3.48) | 0.930 → 1.000 (roof-WI408X190X12X5, IS 800 9.3 interaction / member resistance) | 0.891 → 0.936 | 0.390 → 0.401 | COMPLETE → COMPLETE |
| Ex3 | 56.97 → **51.50** (-5.47) | 0.849 → 0.994 (lateral_col-WI475X220X16X5, IS 800 9.3 interaction / member resistance) | 0.412 → 0.662 | 0.086 → 0.129 | COMPLETE → COMPLETE |
| Ex4 | 63.78 → **57.11** (-6.67) | 0.890 → 0.994 (gravity_col-WI475X190X12X4, IS 800 9.3 interaction / member resistance) | 0.663 → 0.741 | 0.168 → 0.174 | COMPLETE → COMPLETE |
| Ex5 | 34.55 → **32.38** (-2.17) | 1.102 → 1.132 (lateral_col-WI862X225X12X8, IS 800 9.3 interaction / member resistance) | 1.155 → 1.198 | 0.363 → 0.373 | PARTIAL (gates failing: wind_defl_Y) → PARTIAL (gates failing: wind_defl_Y) |

kg/m² of plan (the gold take-off). The gold figures differ from the sizer's verified runs by at most 0.09 kg/m² (Ex1
32.38 / 32.40, Ex2 52.69 / 52.60, Ex3 51.50 / 51.57, Ex4 57.11 / 57.14): the gold `cfg.py` take-off formulas are the
gold's own plate list, the sizer's is the October declared take-off corrected by its itemised plates. Against the
October study figures (31.54 / 50.71 / 50.20 / 55.63) the golds are 0.84 to 1.98 kg/m² heavier: the gable wind and
corner columns sized for the wall wind (and, on IN_Ex1, the corner shear key that follows the heavier corner column
under ruling O1). IN_Ex5 is the check of the new IN_Ex1 with 0.15 kN/m² PV: PARTIAL as before (the PV does not fit,
see below).

What changed, per job (from → to):
- **IN_Ex1**: COL_T TI300-1000X250X14X6 → TI375-975X225X12X8; RAF_T TI1000-550X250X14X6 → TI975-575X250X14X6; RAF_P
  WI550X220X10X5 → WI575X190X10X5; G_RAF WI350X160X8X5 → WI250X140X8X4; G_COL WI300X180X8X5 → WI200X160X12X4; W_COL
  WI400X180X8X5 → WI300X180X8X4; knee end plate 280 × 45 (20 M30, unchanged) with a 32 mm column flange plate (was
  36), stiffeners 2 × 120 × 20 (was 25), diagonal 120 × 6 (was 16); apex 240 × 36 (was 40); rafter splice 270 × 14,
  16 M20 (was 270 × 25, 12 M20); main key 2 × 400 × 28, 250 deep (was 400 × 45, 340); corner key 2 × 250 × 56, 300
  deep (was 250 × 36, 230); girts LZ210X60X20X2 (was LZ230X75X20X2), purlins unchanged.
- **IN_Ex2**: COL WI700X300X22X14 → WI725X230X22X14; RAF_K TI600-500X250X20X17 → TI575-525X260X22X16; RAF_B
  WI500X250X20X14 → WI525X210X32X14; RAF_S WI500X300X25X14 → WI525X290X22X14; CAN_T TI550-250X200X12X6 →
  TI450-200X190X12X5; G_RAF WI500X250X16X8 → WI250X220X12X4; G_COL WI450X350X20X10 → WI225X280X18X4 (WI225X270X18X4 at adoption, see below); W_COL
  WI600X250X14X8 → WI400X220X20X4; knee end plate 45 (was 50, 18 M36) with a 45 mm column flange plate (was 50),
  stiffeners 14 (was 25), diagonal 6 (was 20); rafter splice 300 × 32 (was 36); canopy root 220 × 32, 18 M20 (was
  14 M24); keys 2 × 600 × 28, 250 deep (was 600 × 50, 400) and SCBF 2 × 800 × 56, 400 deep (was 800 × 60, 420);
  purlins and girts LZ270X75X20X2.55 (were LZ250X75X20X3.15).
- **IN_Ex3**: COL WI550X250X16X8 → WI475X220X16X5; RAF_T TI800-450X220X12X6 → TI675-375X225X12X6; RAF_P WI450X200X10X6
  → WI375X190X10X4; G_RAF → WI250X120X6X4; G_COL → WI200X190X12X4; W_COL → WI350X180X8X4; knee 280 × 32, 20 M24 (was
  280 × 45, 16 M30) with a 28 mm column flange plate (was 36); apex 240 × 32, 16 M20 at (hf − 120)/3 (was 36, M24 at
  90); rafter splice 240 × 14, 12 M20 (was 25, 8 M20); key 2 × 500 × 25, 300 deep (was 450 × 40, 350); girts
  LZ240X75X20X2.3 (was LZ250X75X20X2.3).
- **IN_Ex4**: COL_T TI400-750X250X20X16 → TI425-650X250X20X14; RAF_K TI600-500X250X20X17 → TI575-475X250X18X16; RAF_B
  WI500X250X20X14 → WI475X220X16X14; G_RAF → WI225X120X6X4; G_COL → WI200X220X16X4; W_COL → WI475X190X12X4; knee end
  plate 40 (was 50, 18 M36) with a 40 mm column flange plate (was 50); apex 260 × 40 at (hf − 120)/4 (was 50 at 90);
  rafter splice 260 × 20, 12 M20 (was 32, 12 M24); key 2 × 500 × 36, 300 deep (was 500 × 45, 350); purlins
  LZ230X75X20X2.55 (was LZ250X75X20X2.55).
- `SOLUTION.md` of each job: a third-wave block at the top with the new key results; the tables below it describe the
  October design and are marked as such.
- **Re-verified on the final span-moment fix** (the review fixes 28831f8, merged here as b67c09b; Table 18
  uniform-loading Cm in place of the 0.9 sway value): IN_Ex1, IN_Ex3 and IN_Ex4 are unchanged (same kg/m², same
  ratios: their gable columns are governed by the lateral-torsional equation of 9.3.2.2, where Cm hardly enters;
  wind / corner columns IN_Ex1 0.994 / 0.911, IN_Ex3 0.975 / 0.911, IN_Ex4 0.994 / 0.970). IN_Ex2's corner column
  WI225X270X18X4 went from 0.972 to 1.066: its minor-axis span moment is about equal to its end moment, so Table 18
  gives Cmy 1.0 where the first version took 0.9. The sizer re-sized that one constant with every other plate and joint held: WI225X280X18X4 (flanges 280 wide, +147 kg, 52.69 → 52.71 kg/m²), which passes the full run; the base plate follows the section in the job's take-off.


## Engine fixes the adoption needed

### Column span moment (`static_model`, `design_pipeline`, `india_is800`) — commit 2cb42ff, review fixes 28831f8
- **Wrong:** a column's member check used its end moments only. A gable wind column is pinned at the base and at the
  end rafter and carries the gable wall wind as a span load (the IS 875 (Part 3) member wind, applied by
  `static_model.member_wind_loads` as a uniform load on the exposed column line): its end moments are zero, so the
  w L²/8 at mid-height was never checked. The gable corner columns (gable and side-wall wind, both axes) had the same
  gap. The auto-sizer therefore took every gable wind and corner column of the study down to 200 × 120 plates: with
  the moment counted, the study's strict designs had these columns at D/C 4.1 (IN_Ex1 wind column WI200X120X6X4),
  3.6 (IN_Ex1 corner column), 10.4 (IN_Ex4) and 19.8 (IN_Ex2), so they could not be adopted as they were.
- **The published (October) golds had the same gap.** Estimated from their recorded column end shears (a pinned
  column under a uniform load: M = V L / 4), their gable columns would be at: IN_Ex1 corner column WI300X180X8X5
  **1.30**, wind column WI400X180X8X5 0.72; IN_Ex2 wind column 0.68, corner column 0.63; IN_Ex3 corner column
  WI300X200X10X6 **1.20**, wind column 0.93; IN_Ex4 corner column WI350X250X12X6 **1.21**, wind column WI450X200X10X6
  **1.10**. The October IN_Ex1, IN_Ex3 and IN_Ex4 golds would have failed the check (estimates; LTB length taken as
  the declared girt / fly-brace spacing).
- **Fix:** every column record carries the signed extreme moment inside its span about both axes (`REC_FIELDS`
  `Mmaj_span` / `Mmin_span`), found from the element end forces for its uniform span load
  (`static_model.column_span_moments`), from the static part of each combination only (the response-spectrum part has
  no span load and its end forces are peak values). The demand cache is keyed on the record layout. The lead carries
  the same patch on `fix/2026-10-column-span-moment` (00336f6).
- **Review fixes (28831f8, the lead's branch, merged here as b67c09b; see CHANGES_2026-10-column-span-moment.md):** an
  independent review found the first version's use of the span moment wrong in places. The records now carry the
  free moment of the span load (`Mmaj_free` / `Mmin_free`), and the member check rebuilds the moment diagram from it,
  checks the in-span extreme of either sign with its own LTB length, and takes Cmy / Cmz from the IS 800 Table 18
  uniform-loading rows (0.95 for a pinned column under the wall wind; was 0.9 from the frame's sway flag); CmLT takes
  the row value only with the compression flange unrestrained over the member, else 1.0. Gravity columns have no sway
  mode under a span load. Splice, base and beam-to-column demands keep the end moments. The PEB golds below were
  re-verified, and their gable columns re-sized where needed, on the merged engine.
- **Who it touches:** every hot-rolled job with member wind on single-element pinned columns. CFS vendors the HR
  engine (re-vendor: the lead).

### Base plate inside the column outline (`india_connections.base_plate_design`)
- **Wrong:** the compression-side plate cantilever divided by a zero bearing length when the plate did not extend
  beyond the column (a 425 mm wind column on its declared 400 mm plate in a sizer proposal), and the whole Section 12
  block of that run went unevaluated.
- **Fix:** a geometric gate `geometry_plate_outline` (the plate must extend beyond 0.95 d × 0.8 bf, the IS 800 7.4.3.1
  projections) fails instead.

## The auto-sizer (handoff P12, `steel_engine/peb_autosize.py`)
- **Dado-top predictor.** The H/150 + dado-top lever checks the column displacement at the top of the 3 m brick dado
  against dado height / 240. The sizer predicted it with the eave-sway flexibility index (columns and rafters), so on
  the fixed-base IN_Ex2 it stiffened the rafters, which barely moves the dado top, and the full runs failed in turn on
  the rafter splices. The dado top now has its own index: for fixed bases ∫₀ᵃ (H/2 − z)(a − z)/Ix dz over the frame
  line's moment columns (a = dado height; the sway moment of a fixed-base portal column times the moment of a unit
  load at the dado top), for pinned bases the eave index (the dado top follows the eave). Its own margin and feedback
  (`dado`); a run that failed on the dado top alone no longer tightens the eave margin as well.
- **Multi-span frames.** The rafter weight of the sway index was 1 at the eaves falling to 0 at mid-width of the whole
  frame: on IN_Ex2 (96 m continuous over three pinned CHS props) that made the interior rafters sway members, the
  sizer lightened the end spans and the full runs overshot the predicted sway. The weight is now per span between
  moment-connected supports, and where pinned props stand between them the support moment decays to zero at the first
  prop (`LocalModel.rafter_sway_weight`); a portal is unchanged.
- **Base plates and anchors.** Every slab base (not the gusseted fixed bases) has its plate thickness and anchor
  diameter sized for the candidate columns: the governing per-case demands of the run's IS 800 12.12 / 7.4 base row,
  the capacity / minimum moments scaled to the candidate column's Mpc (IS 800 9.3.1.2), checked with the engine's
  `base_plate_design_biaxial` (thickness by bisection over IS 2062 plates from 12 mm, anchors M20 … M36; plan size and
  anchor layout as declared); the plates are itemised in the take-off (an older calibration keeps its own basis,
  `calib_items`); a column must fit its base plate with 15 mm each side (sizer rule).
- **Adopting a design:** spec keys `hold_joints` (joints held at given values) and `size_base_plates` (False keeps the
  plates), used to re-size only the gable columns of the study designs.
- Tests: `tests/test_third_wave_peb.py`.

<!-- STUDY -->
