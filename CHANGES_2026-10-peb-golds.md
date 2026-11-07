# steltic-india — 2026-10 third wave: the auto-sized PEB golds (IN_Ex1 … IN_Ex5)

Branch `fix/2026-10-third-peb-golds`, from main 44b74de. Owner decision (2026-10-30): adopt the auto-sized designs of
the PEB variations study (the "strict" variant: the owner rulings D-T1, D-T2, D-T4, D-T5, D-T7, O1, H/240 with a brick
dado, D8) as the published golds of IN_Ex1 … IN_Ex4; IN_Ex5 (rooftop PV on IN_Ex1 as built) follows the new IN_Ex1;
everything derived from them is re-based. The job folders (`cfg.py`, `secondary/secondary_is801.py`, IN_Ex5
`pv_check.py`) live in the gold area, not in this repo; this file records what changed in them.

## Independent review (2026-11-06, briefs/PEB_REVIEW.md): status

The review found no dropped or weakened check, hand checks agreeing with the engine to 0.01 %, IN_Ex2 reproducing
byte for byte and the IN_Ex5 numbers consistent, but three engine blockers that decide golds sized to 0.99-1.00:
**A** member checks rank combinations by magnitude, not sign (IN_Ex2 canopy root 1.211); **B** the Table 2 web class
uses P = 1 N (IN_Ex3 column about 1.07, IN_Ex2 wind column about 1.05, IN_Ex1 main column about 1.03); **C** joint
plates of 16-20 mm keep fy 250 / 350 (IN_Ex3 knee stiffeners 1.024). A and B, and `plate_fy` in the sizer, are fixed
by the engine agent and are on main (56909e3); the golds were re-verified on it and only what failed was re-sized
(next section), and the IN_Ex5 PV answer, the strengthening option and the IN_Ex2 / IN_Ex4 comparisons re-based.

Done on this branch before the engine fixes landed (no sizing runs):
- **C in the gold cfgs:** the plate, stiffener and key yield stresses that the IN_Ex1-Ex4 helpers compute
  (`bolted_end_plate`, the base plate and fin plate helpers, the knee shear plates and panel stiffeners, the shear
  keys) now come from the engine's IS 2062 (Part 1):2025 Table 3 band function (`india_is800.fy_is2062`, behind a one-line alias
  in each cfg). Executing the cfgs before and after (no analysis) changes exactly: IN_Ex1 knee flange stiffeners
  20 mm and gable splice plates 20 mm, IN_Ex3 knee flange stiffeners 18 mm and gable splice plates 20 mm, IN_Ex4
  rafter and gable splice plates 20 mm, all 250 → 240 MPa, and IN_Ex2's 60 mm fixed-base plate 240 → 230 MPa (a case
  the review did not list: that helper had no band above 40 mm).
- The biaxial base keeps the minor-axis plate outline row (review item 4) and the sizer's no-plate reason is per call
  (item 7); tests added.
- Wording: "worst member ratio" where the member maximum is quoted, with the worst connection, Section 12 and purlin /
  girt ratios beside it (SOLUTION.md blocks, the table below: IN_Ex3's knee is at 1.000); the IN_Ex5 block gives the
  package's 59 reasons (15 was the stored, truncated list); the study design runs (strengthening option, the
  comparisons' re-sized rows) say "every check passes ... engine status partial only for the missing grounding
  record" instead of COMPLETE.

## Engine-check pass (main 56909e3, 2026-11-06): re-verified, and only what failed re-sized

Main 56909e3 (the engine-check fixes A–C with rulings R1 and D-T11, side walls, a wind post's own Ka, gates on the
earthquake records, the panel-zone doubler at its own fy, member wind) is merged here (0103e60). Owner ruling for
this pass: run IN_Ex1–Ex4 on the merged engine and re-size **only what fails**, everything else held (the sizer with
the failing member constants and joint slots free, `hold_joints` for the rest); no full strict re-size. The gold
cfgs also changed on this branch before the runs:
- the helper-computed plate, stiffener and key fy from the engine's IS 2062 band function (`fy_is2062`, review
  blocker C). The literal plate values left in the cfgs were all at or below their band (and the engine caps a
  declared plate fy at its band): the base gussets (IN_Ex2 37 mm at 230 against a band of 240, its 28 and 25 mm
  gussets at 240, IN_Ex3 28 mm and IN_Ex4 30 / 28 mm at 240), the 6 mm fly-brace angles and the 10-12 mm fin, gusset
  and stiffener plates at 250, the IN_Ex3 crane bracket at 250 with its column at 350, and the knee CJP parent metal
  at 350. After the final review they call the band function too; executing the cfgs before and after changes one
  value, the IN_Ex2 37 mm base gussets 230 → 240 MPa. The CHS brace end connections keep the tube's 310 MPa (not an
  IS 2062 plate);
- the end-plate helper's web strip: the member web at its band, and a web doubler at its own (E250) band,
  thickness-weighted, as the engine takes the knee strip (the sizer's `ep_dict` the same);
- IN_Ex2 / IN_Ex5: the side walls take the same 10.2 gust ratio as the windward and leeward walls in each pattern;
- knee and panel doublers left at E250 (no `doubler_grade` declared: nothing in the golds says E350).

Tags (the fix behind each move): **A** every combination with both moment signs; **B** Table 2 web class with the
combination's N; **R1** Pd from the axial-only class (42ε effective area above it); **D-T11** the 42ε / axial row
with compression and |Mz| ≤ 0.05 Mdz; **C** IS 2062 bands (here: the web doublers of the knees at E250, and plates of
16–20 mm at 240); **SW** the side walls on the corner columns and posts; **Ka** a wind post's own Ka; **G**, **PZ**,
**MW** moved no PEB row. "Before" is the gold of cdfc027 (the review's state); "fixed engine" is the same cfg run on
0103e60; "final" is the re-sized gold. The pre-fix packages and the attribution script are in the PEB sandbox
(`scratch/prefix`, `scratch/attribution.py`).

| job | item | before | fixed engine | tags | re-sized (from → to) | final |
|---|---|---|---|---|---|---|
| Ex1 | corner columns | 0.911 | **1.133** | SW (side-wall suction, biaxial), Ka (+6 %), R1 | G_COL WI200X160X12X4 → WI350X160X12X10 | 0.992 |
| Ex1 | main columns (WI862 station) | 0.996 | **1.063** | B, R1 | COL_T TI375-975X225X12X8 → TI325-975X240X12X8 | 0.978 |
| Ex1 | gable rafter as roof-girder chord | 0.960 | **1.023** | B / R1 (strut) | G_RAF WI250X140X8X4 → WI275X140X8X4 | 0.997 |
| Ex1 | knee end plate and its 12.10.2.1 rows | 0.991 | **1.091** | C (8 mm web doubler at E250; 20 mm stiffeners at 240) | end plate 280 × 45, 20 M30 → 280 × 36 with two outer rows, 24 M30; column flange plate 32 → 28 mm; flange stiffeners 20 → 25 mm | 0.974 (knee), 0.925 (12.10.2.1) |
| Ex1 | main shear key (O1, 1.2 Vd of the new column) | — | — | follows the column | 2 × 400 × 28, 250 deep → 2 × 400 × 32, 300 deep | — |
| Ex2 | corner posts | 0.990 | **1.392** | SW with the gust ratio on the side walls (+51 % loads), Ka (+7 % / +8 %), R1 | G_COL WI225X280X18X4 → WI300X300X20X4 | 0.996 |
| Ex2 | canopy beam root | 0.9995 | **1.211** | A (1.2DL+1.2LL+1.2WM0+, hogging, was not checked) | CAN_T TI450-200X190X12X5 → TI625-200X190X12X4; root end plate 220 × 32 → 220 × 18 | 0.983 (member), 0.978 (root plate) |
| Ex2 | gable wind columns | 0.993 | **1.052** | B, R1 | W_COL WI400X220X20X4 → WI450X210X20X4 | 0.996 |
| Ex2 | gable rafter as roof-girder chord | 0.984 | **1.031** | B / R1 (strut) | G_RAF WI250X220X12X4 → WI200X225X12X4 | 0.995 |
| Ex2 | knee (column stiffeners at the rafter flanges) | 0.973 | **1.076** | C (16 mm column-web doubler at E250) | flange stiffeners 14 → 20 mm | 0.985 (knee) |
| Ex3 | corner posts | 0.911 | **1.178** | Ka (+7 %), B / D-T11 (compact → semi-compact), R1 | G_COL WI200X190X12X4 → WI200X200X14X4 | 0.925 |
| Ex3 | columns | 0.994 | **1.083** | B (compact → semi-compact), R1 | COL WI475X220X16X5 → WI550X220X16X5 | 0.956 |
| Ex3 | knee (column stiffeners at the rafter flanges) | 1.000 | **1.096** | C (6 mm doubler at E250, 18 mm stiffeners at 240) | flange stiffeners 18 → 22 mm | 0.999 (now the column-flange T-stub row of the deeper column) |
| Ex3 | rafter haunch and splice (moved by the deeper column) | 0.995 / 0.942 | — | follows the column | RAF_T TI675-375X225X12X6 → TI700-375X230X12X6; rafter splice 240 × 14, 12 M20 → 240 × 20, 8 M20 | 0.971 (haunch), 0.954 (splice) |
| Ex4 | corner posts | 0.970 | **1.242** | Ka (+6 %), B / D-T11 (plastic → semi-compact), R1 | G_COL WI200X220X16X4 → WI200X225X16X5 | 0.985 |
| Ex4 | knee (column stiffeners at the rafter flanges) | 0.973 | **1.083** | C (16 mm column-web doubler at E250) | flange stiffeners 12 → 18 mm | 0.981 |

Ka (a wind post's own tributary area) raised every corner post's in-span moments by 6-8 % (IN_Ex1 1.06, IN_Ex2
1.07 / 1.08, IN_Ex3 1.06 / 1.07, IN_Ex4 1.06), which contributed to all four corner failures. The IN_Ex3 and IN_Ex4
corner posts failed under the 90° wind with negative internal pressure (WM90−), where the side walls carry no net load: their tags are
Ka, B / D-T11 and R1, not SW (corrected after the final review). The IN_Ex1 and IN_Ex2 corner columns are SW, with Ka
on top. Ka moved the gable wind columns by −2 to +1 % (none failed). No Section 12 row of the PEB golds failed on the
fixed engine (G, PZ). The IN_Ex1 and IN_Ex2 gable rafters as roof-girder chords failed in the secondary-member
list, which my first free list missed: their runs were repeated with G_RAF free. The first IN_Ex3 attempt held the
haunch and the rafter splice and could not pass (the deeper column draws more moment into the haunch), so both
were freed.

Main e45a65d (the report's strength lines) and 8cc56ec (the consistency chapter's advisory guards) were merged
before the final runs (09e3f62, 768ddab); neither changes a design result. The five golds were run once more on the
final head (2026-11-07, after the merge and the last literal-fy switch below): every figure in this file is from
those runs and is unchanged from the runs on 73ad473.

**Final kg/m² (gold take-off, all COMPLETE):**

| job | cdfc027 (review) | final | change |
|---|---|---|---|
| Ex1 | 32.38 | **33.11** | +0.73 |
| Ex2 | 52.71 | **52.77** | +0.06 |
| Ex3 | 51.50 | **52.25** | +0.75 |
| Ex4 | 57.11 | **57.26** | +0.15 |

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

| job | kg/m² old → new | worst member ratio old → new (member, new) | worst connection ratio old → new (joint, new) | wind sway Y / limit old → new | storey drift / limit old → new | status old → new |
|---|---|---|---|---|---|---|
| Ex1 | 34.55 → **33.11** (-1.44) | 0.961 → 0.992 (lateral_col-WI350X160X12X10, IS 800 9.3 interaction / member resistance) | 0.969 → 0.983 (conn-lateral_col-WI350X160X12X10) | 0.939 → 0.979 | 0.266 → 0.276 | COMPLETE → COMPLETE |
| Ex2 | 56.17 → **52.77** (-3.40) | 0.930 → 0.996 (gravity_col-WI300X300X20X4, IS 800 9.3 interaction / member resistance) | 0.974 → 0.994 (conn-lateral_col-WI725X230X22X14) | 0.891 → 0.937 | 0.390 → 0.402 | COMPLETE → COMPLETE |
| Ex3 | 56.97 → **52.25** (-4.72) | 0.849 → 0.992 (gravity_col-WI350X180X8X4, IS 800 9.3 interaction / member resistance) | 0.948 → 0.999 (conn-peb-knee-WI550X220X16X5-WI700X230X12X6) | 0.412 → 0.527 | 0.086 → 0.104 | COMPLETE → COMPLETE |
| Ex4 | 63.78 → **57.26** (-6.52) | 0.890 → 0.993 (roof-WI569X250X18X16, IS 800 9.3 interaction / member resistance) | 0.984 → 0.984 (conn-brace-WPB180X180X51.22) | 0.663 → 0.741 | 0.168 → 0.174 | COMPLETE → COMPLETE |
| Ex5 | 34.55 → **33.11** (-1.44) | 1.102 → 1.127 (lateral_col-WI934X240X12X8, IS 800 9.3 interaction / member resistance) | 0.969 → 1.085 (conn-peb-splice-190702) | 1.155 → 1.206 | 0.363 → 0.377 | PARTIAL (gates failing: wind_defl_Y) → PARTIAL (gates failing: wind_defl_Y) |

Old: the October golds as published; new: the final golds (adopted 2026-10-30, re-sized where the engine-check fixes made them fail, section above), on the final engine (this branch: main 8cc56ec plus this branch). kg/m² of plan (the gold take-off). At adoption (before the engine-check pass) the gold figures differed from the sizer's verified runs by at most 0.09 kg/m² (Ex1
32.38 / 32.40, Ex2 52.71 / 52.71, Ex3 51.50 / 51.57, Ex4 57.11 / 57.14): the gold `cfg.py` take-off formulas are the
gold's own plate list, the sizer's is the October declared take-off corrected by its itemised plates. Against the
October study figures (31.54 / 50.71 / 50.20 / 55.63) the golds are 0.84 to 2.00 kg/m² heavier: the gable wind and
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
- **Splice feedback** (bb295a9): the local model's splice demands are the last run's frozen moments; on the
  continuous multi-span IN_Ex2 rafters a re-sized frame moves them by 20 to 30 % (R = 3 route: 356 kN-m predicted,
  452 in the run), and a failed splice tightened every splice margin by 0.02 per run. A failed end-plate moment check
  now tightens its own joint kind's margin by the overshoot, as the sway margin does. It did not run on the IN_Ex2
  R = 3 attempt above (the change came out of it); the follow-up study runs with it.
- **Study page footer:** says slab base plates and anchors are sized for each design (it said they kept the gold's).
- **End-plate web strip** (9aeb226): a web doubler at its own IS 2062 band (E250 unless declared), thickness-weighted
  with the member web at the member's band, in `ep_dict` as in the gold cfg helper (the two keep the same arithmetic).
- **Local combinations** (a35e1b4): after engine fix A the full run checks every combination, which made each local
  evaluation about 8 times slower; the local model (proposals only) keeps a sign-aware subset -- the largest and
  smallest of every signed record field, the largest shears and a combined N / Mmaj / Mmin proxy for each moment
  sign -- and a miss is caught by the full run and fed back through the margins.
- **Base shear-key demand** (c66480b, final review): under the analysis-key reading the sizer shrank the IN_Ex4 SMRF
  base keys (to 200 × 14, 150 deep) and every full run failed the column-base shear key at about 5× (the October
  study failed the same way). `base_demands` took Hc for the IS 18168 9.3 capacity shear 2.2 Ry Mpc / Hc from the
  column's buckling length (13 m against a 6 m base element on IN_Ex2), where the engine's base check takes the base
  spec's Hc_mm, else the base element's length; and it had no IS 18168 9.4 shear 1.1 Ry Mpc / Hc for pinned SFRS bases.
  Both now follow the engine. On an IN_Ex2 run copy the sizer's demands under the 1.2 Vd reading equal the engine's
  shear-key rows (2,066.0 and 4,988.3 kN) both before and after the change, so the strict-rule sizing is unchanged. The
  five golds do not use the changed path: their cfgs are verified by full runs, and the IN_Ex2 / IN_Ex4 base keys were
  held in the engine-check pass. Under the analysis reading the demands rise from 296.7 / 0.1 kN to 685.8 / 136.7 kN,
  and the IN_Ex4 key rows now pass their full runs (the lever study below).
- **History** (final review Low 6): each full run keeps the first 12 blocking reasons and their full count
  (`n_blocking`), in the sizer and the lever study.
- Tests: `tests/test_third_wave_peb.py` (30).

## IN_Ex5: the PV answer on the new IN_Ex1 (final engine, re-sized IN_Ex1)
- `pv_check.py --bisect --bisect-readings` (0.01 kN/m² bisection): **capacity 0.00 kN/m²** at H/240, at H/150 (the
  dado detailed to move independently) and on strength alone. The largest ratio is 0.997 without the PV (the gable
  rafter acting as roof-girder chord) and 1.001 with 0.01 kN/m² (the same chord); from 0.03 kN/m² the frame is below
  1 Hz and the gust-factor sway fails H/240; at 0.15 kN/m² the job is PARTIAL (57 reasons; worst member ratio 1.127,
  the main column; wind sway 1.206 of H/240). October (the old IN_Ex1): 0.02 kN/m², limited by the sway once the
  frame drops below 1 Hz. The side walls are now loaded, with the same 10.2 gust ratio as the other walls.
- The bisection and the strengthening option below ran before main e45a65d was merged; the final gold runs on the
  merged head (73ad473, and again 252d57f after 8cc56ec) show that the merges change nothing here (IN_Ex5 at 0.15 kN/m² still 1.127; the IN_Ex1
  roof-girder chord still 0.9973, the bisection's 0.00 kN/m² point).
- The report's PV answer and the installer note follow (0.00 kN/m²; "a lighter array or a smaller covered area does
  not help: the shed as built has no spare capacity for PV").
- `design/pv_sensitivity_static_wind.json` (an October sensitivity run with the static wind, not part of the current
  check) is withdrawn from the job folder; **the lead removes it from the published gold**.
- **Site flag (the hub's HR index, SITE's build):** the IN_Ex5 flag still reads as the October answer. Suggested
  text: "The shed as built has no spare capacity for PV: it is designed close to its limits (largest ratio 0.997
  without the array, over 1.0 with 0.01 kN/m²), and with the PV mass the frame drops below 1 Hz and the gust-factor
  sway exceeds the H/240 limit. Strengthened to carry 0.15 kN/m²: +2.88 kg/m² (6.48 t), largest ratio 0.999; see the
  report."

## Re-based report files
- **IN_Ex5 `strengthening_option.json`** (solar-ready, strengthen-only from the final IN_Ex1, the IN_Ex5 wind basis):
  +6.48 t, **+2.88 kg/m²** (33.11 → 35.99); every check passes in its design run, largest check ratio 0.999 (the
  12.10.2.1 knee connection moment). The design run builds no report, so the engine's own status for it is partial,
  only for the missing grounding record (the file says so instead of COMPLETE). Changes: main columns
  TI325-975X240X12X8 → TI350-975X270X12X8, corner columns WI350X160X12X10 → WI350X160X12X12, gable end rafter
  WI275X140X8X4 → WI275X150X8X4, rafter bodies WI575X190X10X5 → WI625X220X10X5, haunches TI975-575X250X14X6 →
  TI975-625X250X14X8, main shear keys 2 × 400 × 36, 300 deep, knee column flange plate 28 → 32 mm and flange
  stiffeners 25 → 28 mm, apex end plates 36 → 40 mm, purlins LZ230X75X20X2 → LZ230X75X20X2.3. October (from the old
  IN_Ex1): +2.34 kg/m² (5.25 t).
- **IN_Ex4 `compliance_comparison.json`** (final engine, final gold): as designed = the published auto-sized SMRF
  (57.26 kg/m²); the SMRF re-sized by the current sizer 56.61; the ordinary frame (OMRF R 3 / OCBF R 4, no IS 18168,
  the Zone IV ban set aside for the comparison) auto-sized from it 51.93; **difference 4.68 kg/m² (9.0 % of the
  ordinary frame)**, 5.33 against the published design (before the engine-check pass: 5.78, 11.4 %; October: 6.09,
  12.3 %). The re-sized rows say "every check passes" (design runs without the report) instead of COMPLETE.
- **IN_Ex2 `compliance_comparison.json`** (final engine, final gold): as designed = the published auto-sized SMRF
  (52.77 kg/m²); the SMRF re-sized by the current sizer 51.46 (533.5 t); the ordinary frame row is the SMRF's sizes
  run as an ordinary frame with ordinary braced frame braces, 51.72 (536.2 t), the lightest passing ordinary frame.
  In 7 full runs (the sizer's relax rule included) every lighter ordinary frame failed: 519 t on the eave sway (1.09),
  508 t on a rafter splice end plate (1.15), 530.1 t on the eave sway by 0.5 %; the proposals after them, with the
  sway margin tightened, passed but were heavier. **The cost of compliance is stated as a bracket** (final review):
  between the lightest passing ordinary frame (0.5 % heavier than the re-sized SMRF, −0.26 kg/m²) and the lightest
  tried (+0.33 kg/m²), so within about ±0.3 kg/m² (±0.6 %): nil at the sizer's resolution, against 4.68 kg/m²
  (9.0 %) on IN_Ex4. The file's `difference` carries the bracket (`range_kg_m2` [−0.26, +0.33], printed by the report
  as "between −0.26 and +0.33 kg/m²"); the signed −0.26 and the +1.05 against the published design are dropped (the
  latter measured the slack in the partly re-sized published design, not the cost of compliance). The limit is the
  sizer's sway prediction for the continuous multi-span ordinary frame (its proposals miss by up to 9 %), not the
  code checks.
- The files are written by the item-13 script of the second wave (adapted: the rows above; public wording, no
  constant names in the change list). IN_Ex8 is the SECT agent's.

## The lever study on the new golds (full ladder) — follow-up
Run on the final engine with `--ladder full --control` (work folder in the PEB sandbox), in resumable chunks under
the shared heavy slots. Done so far (kg/m² of plan; the strict row is the published design re-sized by the current
sizer, which now also sizes base plates and anchors):

| job | published | strict (re-sized) | R = 3 route | solar-ready |
|---|---|---|---|---|
| IN_Ex1 | 32.38 | 31.81 (4 full runs) | n/a (ordinary frames as briefed) | 35.24 (+2.86) |
| IN_Ex2 | 52.71 | 51.37 (6) | 51.63, not resolved (8) | |
| IN_Ex4 | 57.11 | 56.46 (3) | 50.68 (6) | |

Still to run (owner order: after the merge, as a follow-up): the other levers alone and the cumulative steps on
IN_Ex1, IN_Ex2 (including the H/150 + dado-top lever the new dado predictor is for) and IN_Ex4, the whole IN_Ex3
ladder, a second IN_Ex2 R = 3 attempt with the splice feedback above, and `/home/claude/briefs/VIDEO6_NUMBERS.md`
(the writer is ready; it states that the gold is now the strict design).

## Tests
Full suite on this branch (252d57f, main 8cc56ec merged, under heavy, 2026-11-07): **1,368 passed, 5 skipped,
0 failed** (the final review's run on 73ad473: 1,363 / 5 skipped; main before the third wave: 1,121 / 4 skipped).
