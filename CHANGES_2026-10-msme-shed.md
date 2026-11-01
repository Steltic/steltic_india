# steltic_india — 2026-10 third wave: angle-truss MSME shed (IN_Ex21)

Branch `fix/2026-10-third-msme-shed`, from main `44b74de`. The final column span-moment fix is merged in from
`fix/2026-10-column-span-moment` (`28831f8`). The provisional cherry-pick `2cb42ff` was reverted first.

This adds a new example: the typical small-industry shed of a south Indian industrial estate (IN_Ex21, Hosur). The
engine designs it as pin-jointed angle roof trusses on rolled MB columns, with knee braces. The branch also adds the
engine support the shed needs.

The new paths leave every earlier gold unchanged:
- they need a `double_angle` section, a `truss` element, a declared `cfg['truss_connections']` or
  `cfg['tonnage_benchmark']`;
- the column-line change acts only on a column piece that starts off the grid. A static check of all 22 gold models
  found none;
- Appendix C changes only without a tool-call log. Every earlier gold has one.

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
  - The connected leg is chosen with `connected_leg`. `double_angle_label`.
- **`india_is800.py`:**
  - Double angles: classified by the component angle (Table 2 'double angles with the components separated' and the
    'angle, compression due to bending' rows); Table 10 class c; shear area of the two legs.
  - LTB of a double angle bent in the truss plane: IS 800 8.2.2(a) (minor axis, no LTB) when Ix ≤ Iy, otherwise not
    evaluated.
  - Angle sections in combined axial force and bending use the conservative linear form of 9.3.1.1.
  - `axial_member_check_is800`: pin-ended truss members, axial force only.
    - Compression: 7.1.2, with a single angle by the 7.5.1.2 equivalent slenderness (Table 12) and a double angle by
      7.5.2.1.
    - Tension: 6.2 / 6.3.3 / 6.3.4 / 6.4.1 from the declared end connection. Missing inputs leave the check not
      evaluated.
    - Table 3 rows: (i) 180, (iii) 250, (vi) 400.
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
  - Detailing: 10.2.2 / 10.2.3.2 / 10.2.4.2, and at least 2 bolts for a double-angle strut (7.5.2.1).
  - Back-to-back interconnection (7.8.1 / 7.8.2; 10.2.5.4).
  - Gusset yield on the Whitmore width (engineering practice, stated).
  - The knee checks of IS 800 12.10.2.1 / 12.10.2.4.
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
- So the maximum moment the beam can deliver to the joint is the knee brace's design strength N_d = min(Pd, Td) times
  its lever arm about the heel.
- The knee connections are designed for 1.2 times that moment:
  - each knee-brace connection for 1.2 N_d;
  - the heel seat for the horizontal force of the couple, with the 12.10.2.4 shear (1.2DL + 0.5LL plus
    2 × 1.2 M_del / span).
- The truss joints use fully tensioned HSFG bolts (12.4.1). The welds to the column are CJP (12.4.2).
- The Mp alternative of 12.10.2.1 is not used: a triangular truss has no plastic moment at the column face.

## Gold run (IN_Ex21, 2026-11-01, on the merged span-moment fix)

**Result:** design status COMPLETE, no open reasons, 30 s run.

**Final sizes (IS 808 / IS 1161, E250 / YSt 310):**

| Member | Section | Ratio | Governing |
|---|---|---|---|
| Main columns | MB300 | 0.73 | 9.3 interaction |
| Gable posts | MB225 | 0.71 | slenderness |
| Top chord | 2ISA70X70X6 on 8 mm gussets | 0.71 | — |
| Bottom chord | 2ISA70X70X6 | 0.95 | 9.3, under 0.9DL + 1.5WL uplift |
| Verticals up to 1.5 m | ISA60X60X6 | 0.71 | — |
| Long verticals (1.875 m and 2.25 m) | ISA70X70X6 | 0.90 | Table 3 |
| Diagonals | ISA70X70X6 | 0.96 | Table 3 KL/r 172.7 / 180 |
| End diagonals | ISA80X80X8 | 0.68 | — |
| Knee braces | ISA90X90X8 | 0.82 | 7.5.1.2 |
| Wall X-bracing | CHS114.3X3.6 | 0.63 | — |
| Eave struts | CHS114.3X3.6 | 0.85 | — |
| Roof-girder diagonals | ISA90X90X8 | 0.97 | Table 3 (iii) 250 |
| Roof-girder struts and bottom-chord ties | CHS76.1X3.6 | 0.94 | — |
| Purlins | LZ200X60X20X1.6 with 2 sag-rod lines | 0.96 | IS 801, CFS engine |
| Girts | LZ170X60X20X1.6 | 0.85 | IS 801, CFS engine |

**Connections:**
- All truss bolts are M16 8.8 HSFG: 3 per chord and knee-brace end, 3 per end diagonal, 2 elsewhere.
- The highest connection ratio is 0.96 (the edge distance of the 60 mm vertical).
- Knees, IS 800 12.10.2.1 under Steltic design ruling D-T10 (knee designed for 1.2 times the moment the knee brace can
  deliver): 0.79.
- Heel seats, 12.10.2.4: 0.31.
- Fly braces have an M16 4.6 bolt: 0.32 (with M12 the check was not evaluated, because the corpus thread table has no
  M12).

**Serviceability:** wind sway across the span is 22.6 mm against H/240 = 27.1 mm (0.84; brick dado). Earthquake drift is
0.20 of the 0.004 limit (Zone II; wind governs).

**Steel:**
- Total 19,740 kg on 648 m², which is **30.5 kg/m²** of plan:

  | Group | kg/m² |
  |---|---|
  | Primary | 15.8 |
  | Bracing | 5.65 |
  | Secondary | 5.0 |
  | Connections | 4.0 |

- A published comparison of conventional hot-rolled steel sheds gives 27.7 kg/m² at 15 m span and 35.8 kg/m² at
  20 m (N. Kumar and K. S. Grover, IJRASET, June 2022, Table 4). The 18 m shed sits inside that range. The report
  prints the range with its source next to the take-off.

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
   for 1.2 times the brace strength.
4. The restraints for the member checks: purlins at every top-chord panel point, bottom-chord ties at 4.5 m, girts and
   fly braces at 3.0 m and 4.75 m.

Wind governs the design in Zone II. Across the span the earthquake base shear is 10.7 kN; the wind storey force is
47.7 kN, and the member wind on walls and roof totals 100.8 kN horizontally.
A pushover will mainly show reserve, not a seismic demand check.

## Tests

`tests/test_msme_truss_2026_10.py` (28 tests) checks every new path against hand calculations:

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

The brief-count tests now expect 21 India briefs. IN_Ex21 is not added to the UI example list (a lead decision). The
contract (`contract/AGENT_START.md`) documents the new cfg keys.
