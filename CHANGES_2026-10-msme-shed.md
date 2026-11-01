# steltic_india — 2026-10 third wave: angle-truss MSME shed (IN_Ex21)

Branch `fix/2026-10-third-msme-shed` (from main `44b74de`, with the column span-moment fix `2cb42ff` cherry-picked from
the PEB branch). This adds a new example: the typical small-industry shed of a south Indian industrial estate. It is
designed by the engine as pin-jointed angle roof trusses on rolled MB columns, with knee braces (IN_Ex21, Hosur). It
also adds the engine support the shed needs. Every earlier gold is unchanged: the new paths need a `double_angle`
section, a `truss` element or a declared `cfg['truss_connections']`.

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
  - Secondary angle struts pass `angle_connection` / `tension_inputs` / `axial_only` through.
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

## Tests

`tests/test_msme_truss_2026_10.py` (24 tests) checks every new path against hand calculations:

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
- the report section with the public-text pass.
