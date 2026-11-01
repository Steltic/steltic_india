# steltic_india — 2026-10 third wave: angle-truss MSME shed (IN_Ex21)

Branch `fix/2026-10-third-msme-shed`, from main `44b74de`. The final column span-moment fix is merged in from
`fix/2026-10-column-span-moment` (`28831f8`). The provisional cherry-pick `2cb42ff` was reverted first.

This adds a new example: the typical small-industry shed of a south Indian industrial estate (IN_Ex21, Hosur). The
engine designs it as pin-jointed angle roof trusses on rolled MB columns, with knee braces. The branch also adds the
engine support the shed needs.

Most new paths leave earlier golds unchanged:
- they need a `double_angle` section, a `truss` element, a declared `cfg['truss_connections']` or
  `cfg['tonnage_benchmark']`;
- the column-line change acts only on a column piece that starts off the grid. A static check of all 22 gold models
  found none;
- Appendix C changes only without a tool-call log. Every earlier gold has one.

Three changes are not gated, and the first two DO change earlier golds (intended; the lead's final gold run shows
them):
- **IS 800 Table 3 row choice (review 2026-11).** The member-wind combinations (`WM0+`, `WM90-R`, ...) now count as
  wind combinations, in the general member check and in the axial check. Before, only `EQ`, `W_`, `WL` and `EL` did.
  A member whose compression arises only in member-wind combinations moves from row (i) 180 to row (iii) 250, so
  IN_Ex1, IN_Ex2 and IN_Ex8 members (e.g. the IN_Ex2 roof rows) become less conservative.
- **Row (i) label.** An axial force below 1 N (analysis noise) is no longer compression, and row (i) now names the
  largest compression of a combination without wind or earthquake (it printed "(i) compression from DL + LL" with a
  wind or earthquake combination). This changes labels, not ratios.
- **Single angles in 9.3.** `member_check_is800` passes `section_type = 'angle'` for a single angle, so 9.3.1 uses the
  conservative linear form of 9.3.1.1 instead of the 9.3.1.2 I / H reduced moments (a compact angle went from 0.06 to
  0.35 in the review's example). No earlier gold has an angle in this check; fly braces use their own path.

## The example (test_buildings/IN_Ex21_MSME_angle_truss_shed_Hosur.txt)

- **Site:** Hosur (SIPCOT industrial complex, Krishnagiri district). Hosur is in neither IS 1893 Annex E nor IS 875-3
  Annex A, so the nearest listed town is used: Bangalore (Bengaluru), about 40 km away. That gives Zone II, Z = 0.10
  and Vb = 33 m/s, recorded as the ruling R5 site proxy (`site_proxy`, distance, basis, VERIFY).
- **Geometry:** span 18 m, length 36 m (6 m bays), eave 6.5 m, slope 1 in 4 (14.04°).
- **Trusses:** Pratt angle trusses with 12 panels of 1.5 m on plan and purlins at every top-chord panel point.
  - Chords: double angles on 8 mm gussets.
  - Webs: single angles bolted through one leg.
  - Bolts: 8.8 HSFG.
  - The heel is a pinned seat on the column cap.
- **Columns and frames:** MB columns. A knee brace from each column, 1.5 m below the eave, to the first bottom-chord
  panel point makes each frame a knee-braced truss portal (OMRF, R = 3).
- **Gables:** gable posts at 6 m.
- **Bracing:**
  - CHS OCBF X-bracing in the end bays (R = 4). Single angles cannot meet IS 800 12.7.2.1 (KL/r ≤ 120) over the 8.85 m
    diagonals.
  - End-bay roof bracing of angles.
  - CHS eave struts and bottom-chord ties.
- **Cladding and secondary members:** CFS Z purlins and girts (IS 801, D-T5); GI sheeting; 3 m brick dado (H/240).

## Engine (new and changed)

- **`sections.py`:** `register_double_angle` and custom section type `double_angle`. Two IS 808 angles back to back on
  a gusset.
  - The in-plane axis (normal to the gusset) has I = 2 I1, with no parallel-axis term.
  - The out-of-plane axis has I = 2 (I1' + A1 (c + g/2)²).
  - The elastic modulus is taken at the toe. Zp = 2 Zp1 and 2 A1 (c + g/2).
  - The connected leg is chosen with `connected_leg`. `double_angle_label(angle, gap_mm)` gives `2ISA70X70X6-G8` (the
    gusset is in the label), and registering a name again with another angle, gusset or leg is refused.
- **`india_is800.py`:**
  - Double angles: classified by the component angle (Table 2 'double angles with the components separated' and the
    'angle, compression due to bending' rows); Table 10 class c; shear area of the two legs.
  - LTB of a double angle bent in the truss plane: IS 800 8.2.2(a) (minor axis, no LTB) when Ix ≤ Iy, otherwise not
    evaluated.
  - Angle sections in combined axial force and bending use the conservative linear form of 9.3.1.1 (single angles
    included: see above).
  - `axial_member_check_is800`: pin-ended truss members, axial force only.
    - Compression: 7.1.2, with a single angle by the 7.5.1.2 equivalent slenderness (Table 12) and a double angle by
      7.5.2.1. 7.5.2.1 needs >= 2 bolts in line at each end and bounds its effective lengths (in the gusset plane
      0.7 - 0.85 L, normal to it L: a smaller K is raised); with one bolt 7.5.2.2 sends the strut to 7.5.1 (each angle
      through one leg). Undeclared bolts leave it not evaluated.
    - Tension: 6.2 / 6.3.3 / 6.3.4 / 6.4.1 from the declared end connection. Missing inputs leave the check not
      evaluated.
    - Table 3 rows: (i) 180, (iii) 250, (vi) 400, with the member-wind rule above (`is_lateral_combo`).
  - `member_check_is800` passes `angle_connection` to the compression check and gives truss chords the Table 3 rows of
    a member carrying axial load.
  - `angle_end_connection_inputs`: the 6.3.3 / 6.4.1 areas of one bolt line in the connected leg.
- **`engine3d.py`:** `add_truss` (an OpenSees truss element, kind `truss`) and `register_truss_member`, which registers
  the chords. Both feed `info['truss']`.
- **`static_model.py`:**
  - The `truss` kind is analysed like a brace (truss element, self-weight at the nodes).
  - The roof-plane key `purlins_at_nodes` brings the roof area load, the gable cladding and the roof wind to a truss
    top chord as purlin reactions at its panel points (lever rule per segment). The chord's self-weight stays
    distributed.
- **`truss_design.py` (new):**
  - Connection specs (`cfg['truss_connections']`).
  - Bolt groups in shear and bearing: a double angle in double shear, bearing on the gusset or on the two legs.
  - HSFG slip at service (10.4.3) and the 12.4.1 gate when the truss is part of the lateral system.
  - Detailing: 10.2.2 / 10.2.3.2 (on the thinner of the angle and the gusset) / 10.2.4.2, and at least 2 bolts for a
    double-angle strut (7.5.2.1). The end distance follows the cut of the angle end (`end_cut`: sheared 1.7 d0 by
    default; sawn, machine-flame cut or planed 1.5 d0); the toe edge is rolled.
  - Back-to-back interconnection (7.8.1 / 7.8.2; 10.2.5.5 at most 600 mm in a compression member; 10.2.5.4 at most
    1000 mm in tension) and the 7.8.4 bolt size (16 / 20 / 22 mm by thickness).
  - Gussets (engineering practice, stated): yield on the Whitmore width, block shear (6.4.1, one bolt line, to the
    declared gusset edge) and buckling on the Whitmore width (7.1.2 class c, declared K and free length). For a chord
    the full chord force is used: the heel and apex gussets, where the chord ends. Missing gusset geometry leaves the
    row not evaluated.
  - The knee checks of IS 800 12.10.2.1 / 12.10.2.4 (D-T10, below).
  - Angles only: a CHS or other non-angle truss member takes the general member check, and its end connection is
    reported as not covered (it crashed before).
  - A declared chord splice at a panel-point gusset (`splice`: {at, gusset_depth_mm}): 7.3.4.2, the gusset across
    the cut for the full chord force.
- **`design_pipeline.py`:**
  - Truss roles `truss_<group>`, which are not part of the brace / SFRS-brace logic.
  - Knee-braced column lines count as lateral lines.
  - Truss member inputs: end connection, single-angle end condition, axial only.
  - Truss connection records.
  - The knee records (`info['truss_knees']`) go to Section 12 with the knee brace's design strength and the
    1.2DL + 0.5LL end reaction.
  - `section12_cfg(cfg)`: the Section 12 cfg that `design_india` builds, now a function. It carries
    `cfg['truss_connections']`. In the first IN_Ex21 run every knee was "not evaluated" without it.
  - `column_line(n1, n2, grid)`: a column's grid line is read from its end on the grid. The upper piece of a gable
    post runs from an off-grid truss node to the post top. Before, it decoded to a truss-node line (also a moment
    line), so it was taken as a frame column and made a spurious beam-column joint at the bottom chord.
  - Secondary angle struts pass `angle_connection` / `tension_inputs` / `axial_only` through.
- **`report.py`:** with no tool-call log, Appendix C now says so in plain words. Before, it printed the developer
  note naming the missing log file and server call. Every earlier gold has a log, so their reports are unchanged.
- **`india_is800_s12.py`:** in an OMF the knees of a knee-braced truss portal are the moment joints (12.10.2.1 /
  12.10.2.4). Without joints or knees the joint check is still not evaluated.
- **`peb_checks.py`:** truss members are primary steel in the take-off.
- **`peb_outputs.py`:**
  - STAAD export: double angles as `TABLE D / LD / SD <angle> SP <gap>`, and truss members as `MEMBER TRUSS`.
  - IS 808:2021 MB / MC names exported as the STAAD Indian table names (ISMB / ISMC). No earlier gold exports such a
    section.
- **`peb_report.py`:** the angle-truss section: members, end connections, knees, and the rulings that apply.
- **`report_public.py`:** new ruling D-T10. **`viewer3d.py`:** truss members drawn as axial members.

### Steltic design ruling D-T10 (owner, 2026-11-01)

Knee-braced truss portal, IS 800 12.10.2.1:

- The truss is pinned on the column cap. It reaches the column only through the couple of the knee brace and the heel
  seat.
- So the maximum moment the beam can deliver to the joint is the largest force the knee brace can deliver in EITHER
  direction (the wind reverses), N_del = max(Pd, Tdg): its compression design strength, or its tension strength on
  gross-section yield Tdg = Ag fy / γm0. Rupture and block shear of the brace end are connection limit states and do
  not cap it. M_del = N_del times the lever arm about the heel.
- The knee is designed for 1.2 times that moment:
  - each knee-brace connection, the bolts and the gussets at both ends, for 1.2 N_del; gusset buckling for 1.2 Pd;
  - the brace's own bolted end (6.3.3 rupture, 6.4.1 block shear) not weaker than Tdg;
  - the heel seat for the horizontal force of the couple, with the 12.10.2.4 shear (1.2DL + 0.5LL plus
    2 × 1.2 M_del / span).
- So the knee and heel connections are designed so that the brace yields (gross section) before they fail.
- The first implementation used min(Pd, Td), the weaker direction. The 2026-11 review found that and it was
  corrected: the owner's ruling is "1.2 × the moment the knee brace can deliver".
- The truss joints use fully tensioned HSFG bolts (12.4.1). The welds to the column are CJP (12.4.2).
- The Mp alternative of 12.10.2.1 is not used: a triangular truss has no plastic moment at the column face.

## Gold run (IN_Ex21, 2026-11-01, after the independent review; on main `41fb2f7` with the span-moment fix)

**Result:** design status COMPLETE, no open reasons.

**Final sizes (IS 808 / IS 1161, E250 / YSt 310):**

| Member | Section | Ratio | Governing |
|---|---|---|---|
| Main columns | MB300 | 0.73 | 9.3 interaction |
| Gable posts | MB225 (strong-axis buckling length 8.0 m, base to top chord) | 0.71 | slenderness |
| Top chord | 2ISA70X70X6-G8 (on 8 mm gussets) | 0.71 | — |
| Bottom chord | 2ISA70X70X6-G8 | 0.95 | 9.3, under 0.9DL + 1.5WL uplift |
| Verticals up to 1.5 m | ISA60X60X6 | 0.71 | — |
| Long verticals (1.875 m and 2.25 m) | ISA70X70X6 | 0.90 | Table 3 |
| Diagonals | ISA70X70X6 | 0.96 | Table 3 KL/r 172.7 / 180 |
| End diagonals | ISA80X80X8 | 0.68 | — |
| Knee braces | ISA90X90X8 | 0.82 | 7.5.1.2 |
| Wall X-bracing | CHS114.3X3.6 | 0.63 | — |
| Eave struts | CHS114.3X3.6 | 0.61 | Table 3 (iii): its compression is wind-only (0.85 on row (i) before the member-wind fix) |
| Roof-girder diagonals | ISA90X90X8 | 0.97 | Table 3 (iii) 250 |
| Roof-girder struts and bottom-chord ties | CHS76.1X3.6 | 0.94 | — |
| Purlins | LZ200X60X20X1.6 with 2 sag-rod lines | 0.96 | IS 801, CFS engine |
| Girts | LZ170X60X20X1.6 | 0.85 | IS 801, CFS engine |

**Connections:**
- All truss bolts are M16 8.8 HSFG: 8 per knee-brace end, 4 per chord end (heel and apex), 3 per end diagonal, 2
  elsewhere. Angle ends sheared (end distance 35 mm >= 1.7 d0); 8 mm gussets with a declared detail (bolt line to the
  gusset edge 40 mm, free length 150 mm, K 0.65).
- The highest connection ratio is 0.96 (the edge distance of the 60 mm vertical). The chord-end gussets carry the full
  chord force (Whitmore yield, block shear, buckling).
- Knees, under Steltic design ruling D-T10 (the knee designed for 1.2 times the moment the knee brace can deliver in
  either direction): N_del = max(Pd 114.7, Tdg 315.9) = 315.9 kN, so 1.2 N_del = 379.1 kN at each knee-brace end and
  M_del = 335.1 kN-m.
  - bolts 0.85 (8 M16: 448 kN);
  - gusset block shear 0.92, Whitmore yield 0.52, buckling (1.2 Pd) 0.22;
  - the brace yields first: its bolted end (rupture 348.8 kN) against its gross yield 315.9 kN, 0.91;
  - heel seats (12.10.2.4) 0.78.
  So the knee and heel connections are designed so that the brace yields (gross section) before they fail. With the
  first implementation's min(Pd, Td) the knee took 1.2 x 114.7 kN on 3 bolts (0.79), and in tension the connection
  (174 kN) was weaker than the brace.
- Fly braces have an M16 4.6 bolt: 0.32 (with M12 the check was not evaluated, because the corpus thread table has no
  M12).

**Serviceability:** wind sway across the span is 22.6 mm against H/240 = 27.1 mm (0.84; brick dado). Earthquake drift is
0.20 of the 0.004 limit (Zone II; wind governs).

**Steel:**
- Total 19,859 kg on 648 m², which is **30.6 kg/m²** of plan:

  | Group | kg/m² |
  |---|---|
  | Primary | 15.8 |
  | Bracing | 5.65 |
  | Secondary | 5.0 |
  | Connections | 4.2 (longer knee gussets and the chord-end bolts after the review) |

- A published comparison of conventional hot-rolled steel sheds gives 27.7 kg/m² at 15 m span and 35.8 kg/m² at
  20 m (N. Kumar and K. S. Grover, IJRASET, June 2022, Table 4). The 18 m shed sits inside that range. The report
  prints the range with its source next to the take-off. That study is for Delhi (Vb 47 m/s, about twice Hosur's
  wind pressure), so a mid-range position is on the heavy side: this design is not lean (the Table 3 180 rows, the
  ISA90 roof-girder angles at KL/r 242 / 250, and 4.2 kg/m² of connections including the shear keys of ruling O1).

**Outputs:**
- STAAD export (`model.std`), as for the PEB jobs: the double angles as `TABLE D ISA70X70X6 SP 8.0`, webs and braces as
  `MEMBER TRUSS`;
- `design/bom.csv`, reactions and the anchor-bolt plan;
- the viewer.

**First-run fixes:**
- The first run (PARTIAL, 67 reasons) found the two engine gaps fixed above (knee specs, gable-post line) and these
  undersized members: knee brace ISA75 (1.52), end diagonal ISA65 (1.28), 60 mm long verticals (KL/r 191), bottom
  chord 2ISA65 (1.11), gable post MB200 (1.05).
- It also found an unevaluated fly-brace bolt and a slender ISA90X90X6 roof-girder diagonal.
- Four size variants were then run in one slot (all COMPLETE). The lightest was kept.

**Stated, not modelled (review 2026-11):**
- Two load paths for the gable wind: in the analysis the gable wind reaches the side walls through the rigid roof
  diaphragm (the post tops are tied to it). The roof girder, the bottom-chord ties and the bottom-chord X-bracing are
  designed outside the model; the bottom-chord X-bracing is in the take-off only. The roof-girder chord forces (about
  18.5 kN factored) are not added to the top chords of the gable truss and the first inner truss: they do not govern
  (148 kN against the 166 kN top-chord force the chords are sized for).
- Chord splices: the 18 m bottom chord is spliced at the mid-span panel-point gusset, checked (new `splice` spec key)
  for all the chord force (IS 800 7.3.4.2, not faced for bearing): the chord-end bolts on each side and the gusset
  across the cut (gross yield and net rupture). The top chords end at the apex gusset and need no other splice
  within a 12 m stock length (design-engineer assumption).

## Nonlinear run (stage 2): what the shed needs from the nonlinear engine

The HR package carries everything the model needs:
- the custom build with kind `truss` elements, `info['truss']` groups and `info['truss_knees']`;
- the double-angle definitions in the cfg snapshot (`custom_sections`, type `double_angle`);
- the truss connections and the restraint positions.

The nonlinear engine was not changed here. It needs:
1. kind `truss` treated like `brace` in its fibre model / package reader. Today it builds a Truss only for kind `brace`.
2. The `double_angle` sections registered from the snapshot. HR `sections.register_custom_sections` does this once NL
   runs on current HR main with this branch merged. NL also needs an angle fibre section (single and double angles), or
   a truss material capped at the 7.5 compression strength.
3. The knee braces as the frame's yielding / buckling members in the transverse direction. The truss seat stays pinned.
   Check that the knee brace, not its connection, is the first to buckle or yield: the knee connections are designed
   for 1.2 times the larger of the brace's compression strength and its gross-section yield (D-T10).
4. The restraints for the member checks: purlins at every top-chord panel point, the bottom-chord ties at the plan
   positions published as `cfg['bottom_chord_ties_mm']` = [4500, 9000, 13500] (from the y = 0 eave; the bottom-chord
   Ly 4.5 m is derived from them), girts and fly braces at 3.0 m and 4.75 m.

Wind governs the design in Zone II. Across the span the earthquake base shear is 10.7 kN; the wind storey force is
47.7 kN, and the member wind on walls and roof totals 100.8 kN horizontally.
A pushover will mainly show reserve, not a seismic demand check.

## Tests

`tests/test_msme_truss_2026_10.py` (40 tests) checks every new path against hand calculations:

- double-angle properties;
- Table 2 / 10;
- 7.5.2.1 and 7.5.1.2 by hand;
- 6.3.3 / 6.4.1 by hand;
- the Table 3 rows;
- the axial ratio;
- missing inputs block the check;
- the chord beam-column check and 8.2.2(a);
- the bolt group in double shear;
- detailing and stitches;
- the knee geometry and 12.10.2.1 / 12.10.2.4;
- `add_truss` and the kind map;
- purlin nodal loads (gravity and wind totals);
- tonnage;
- STAAD labels;
- member inputs;
- the report section with the public-text pass;
- the Section 12 cfg carries the truss connections to the knee checks;
- a column's line read from its grid end;
- Appendix C without a log;
- the take-off typical range.

The brief-count tests now expect 21 India briefs. IN_Ex21 is offered in the UI example list (`frontend/index.html`,
`steltic/main.py`, `/api/example/in21`) and listed in `test_buildings/README_INDIA.md`; the frontend contract test
covers in1-in21. The contract (`contract/AGENT_START.md`) documents the new cfg keys. D-T10 is recorded with its
meaning in the owner decisions of `docs/PEB_LIMITATIONS.md`, and the meaning printed with every "D-T10" in public text
now names the HSFG 8.8 bolts and the complete-penetration welds at the column.
