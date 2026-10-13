# PEB release (2026-10): limitations, assumptions and owner decisions

This file records what the PEB release (`CHANGES_2026-10-peb.md`) models as an assumption, what IS 800 and the
corpus do not cover and how each gap was handled, and what the owner decided (`docs/PEB_TAPERED_SCOPE.md`
section 8). The gold solutions IN_Ex1 … IN_Ex5 state the job-level consequences in their SOLUTION.md.

## Modelling assumptions
- **Stepped members.** A web-tapered member is modelled as `n_seg` prismatic segments (`taper_nseg`, default 8),
  each with the section at its mid-length. Every segment is checked at both ends with the exact local section, so
  the checks see the real depths; only the analysis stiffness is stepped.
- **Member axis.** Columns and rafters are modelled on straight centrelines: base to knee, and eave to apex at the
  true roof slope. The centroid shift of a member whose depth varies (one flange straight, the other inclined) is
  not modelled. The knee is a rigid joint at the intersection of the centrelines, with no rigid end offsets. Joint
  checks use the node moment with the face section (D-T7), which overstates the moment at the face.
- **Roof diaphragm.** `roof_geometry.tie_diaphragm` ties the eave joints to the diaphragm across the span only and
  the ridge joints along it, so the eaves spread freely under gravity. Joints of `braced_lines` (end-bay roof
  girders) are tied like the eaves. The roof bracing itself is designed as a statically determinate girder
  (`secondary_members`), not as analysis members.
- **Restraints (D-T1).** Purlins and girts restrain the outer flange; fly braces restrain the inner flange at the
  positions declared in `cfg['flange_braces']`. The fly brace is checked for the IS 800 8.3.2 restraint force and as
  a single-angle strut (7.5.1.2). Its stiffness is not checked: IS 800 gives a force, not a stiffness requirement.
- **End plates.** Moment capacity by IS 800 10.3.5 / 10.4.7 (bolt tension with prying) and the 8.2.1.2 plate strip:
  the sum of the row forces times their lever arms over the declared tension rows.
  - Row force: 2 Te for every row (a plastic distribution, as in the thick-plate end-plate method), capped for a row
    inside the flange by the web strip that feeds it, be x t_web x fy / gamma_m0 (IS 800 6.2; `web_t_mm` includes a
    declared web plate). The prying force is never negative: when Te < K the plate check is Te lv <= Mp_strip.
  - The strip per bolt is the declared `be`; the golds use the row pitch, capped at half the plate width (IS 800 10.4.7:
    effective width per pair of bolts), and `lv` from the bolt to the toe of the flange or web weld. Only rows in the
    tension half of the section are counted. Where two rows sit beyond a flange, the golds declare an extension rib
    stiffener.
  - Demand at a knee: owner ruling D-T7, 1.2 Mp of the face section in either sign; under route B (IS 18168, SMRF)
    8.4, 1.1 Ry fy Zpb. The same demand is used for the column side of a bolted knee: the column flange as a T-stub
    flange with the same rows (`column_flange_t_mm`, the knee-zone flange plate) and the column web feeding the inner
    rows (with the knee-panel doubler), and the column stiffeners at the rafter flange levels. The knee panel shear
    uses the factored knee moment (IS 800 12.10 sets no panel demand for an OMF; the SMF panel at 1.2 Mp is IS 800
    12.11.2.3 in Section 12). Two-way action of the column flange between stiffeners is not credited (conservative).
  - Apex: 1.2 Mp of the face (D-T7), and under IS 18168 not less than 1.80 x the analysis moment (6.5). Rafter splices:
    the factored moment of both signs, x 1.80 under IS 18168 6.5.
  - Moment reversal: a `symmetric` pattern has the same rows at the other flange and the same capacity both ways. A
    one-sided pattern is checked in the reverse sign with its rows measured from the other flange.
- **Crane rail spread** (opt-in, `cfg['crane']['check_rail_spread']`): the change of the rail gauge under the full
  crane frame case (vertical with impact, the R e moments and surge, gamma 1.0) on the sway model, against the IS 800
  Table 6 limit for the relative displacement between rails. It is reported in `crane_sway.rail_spread` and is not a
  gate.
- **Tonnage.** The take-off (`calc_package['peb']['tonnage']`) is built from three parts:
  - the analysis members, from their plate areas;
  - the declared secondary records: IS 801 purlins and girts with their laps, and the roof-girder struts;
  - a plate take-off of the declared connections (`peb_connection_mass_kg`).
  Fly braces, sag rods, bridging, cleats, welds and bolts are not weighed. They are in the roof dead load as an EOR
  allowance.

## What IS 800 and the corpus do not cover, and how it was handled
| Gap | Handling |
|---|---|
| LTB and member buckling of web-tapered members (Annex E is prismatic; 3.7.3 (c) covers tapered flange elements only) | Owner ruling D-T1: LTB segment by segment between restraints, each station with its own section, **C1 = 1.0** (conservative: the moment-gradient C1 of the proposal is not used). Major-axis buckling over the member length with the smallest section of the member. The elastic critical load factor lambda_cr of the stepped model is checked by 4.6.2(b) (all golds > 5) |
| Slender (class 4) webs | IS 800 3.7.2 (d), the deduction route: the width in excess of the semi-compact limit is removed for axial and bending. Shear by 8.4.2 with the declared stiffener spacing. SMRF members under IS 18168 route B have no slender element (Table 2) |
| Wind coefficients for roof-mounted PV | None in IS 875-3: the flush array is treated as part of the roof (EOR record, VERIFY); module and clamp uplift is the PV vendor's design (IN_Ex5) |
| Attached (wall-mounted) canopies | IS 875-3 gives free-standing canopies only: EOR coefficients with source and VERIFY (IN_Ex2) |
| Dynamic wind of a low, flexible shed (f1 < 1 Hz) | IS 875-3 9.1 (b) and 10.2: the gust factor on the frame's across-ridge force, with the walls of the member cases scaled to it. Across-wind (10.3) is for tall buildings and is recorded as not applicable (EOR) |
| Fatigue detail category (IS 800 Table 26 is OCR-illegible in the corpus) | Declared by the EOR from the printed table, VERIFY (IN_Ex3) |
| Anchor bond, pedestal bearing, Ec | IS 456 (outside the corpus): EOR inputs with VERIFY. Foundations are delegated with the reactions |
| Cold-formed zed bending | IS 801:1975 with IS 811 sections. A lipped zed is designed about its geometric axis only with a declared `zed_basis` (sheeting through-fastened to one flange, the free flange held by sag rods and fly braces); principal-axis bending is not implemented. Lapped purlins are continuous beams with the laps at 2 EI |
| IS 811 section range | IS 811 tabulates zeds to 250 mm deep. Deeper proprietary purlins are outside the corpus, which is why 9 m bays (IN_Ex2) need close spacing |
| IS 1893 (Part 4), industrial structures | Not in the corpus. The portals use the IS 1893 (Part 1) Table 9 building rows |
| Zone or Vb of a town not tabulated, where Fig. 1 is image-only | Ruling R5 site proxy (a tabulated town close by, VERIFY), or a corpus Fig. 1 reading record where one exists |

## Owner decisions (section 8)
| Decision | Ruling |
|---|---|
| D-T1 stability basis | Accepted as proposed, with C1 = 1.0 in the engine (above) |
| D-T2 Zones III-V | Route B: IS 18168:2023 adopted voluntarily (`apply_is18168`). E350 B0 (5.2(a)), Table 2 limits with b = bf/2 for welded flanges, Ry, 9.3 fixed bases at 1.1 Ry Mpc, 9.4 minimum base moment, 6.5 splices at 1.8 x and >= 3 db (see D-T9), 7.2 KL/r < 75, 8.4 beam-column connections (the PEB knees) for 1.1 Ry fy Zpb. The E250 material row keeps its IS 800 E250B form |
| D-T3 monosymmetric sections | Doubly symmetric only |
| D-T4 tension-only rods | Not used. Braces are CHS or WPB designed for compression |
| D-T5 purlins and girts | Designed with the CFS engine (IS 801) and imported into the HR package |
| D-T6 scope of IS 800 12.4.2 | Complete-penetration welds for connection welds only; flange-to-web welds are fillets |
| D-T7 Mp at a tapered joint face | 1.2 Mp of the section at the joint face, at the knees and the apex, in either sign. Rafter splices take the factored moment of both signs (x 1.80 under IS 18168 6.5) |
| D-T8 IS 18168 wording in IN_Ex9 | Not part of this release (IN_Ex9 results are unchanged) |
| O1 (existing ruling) | 1.2 Vd of the column section on every SFRS base, both axes. On pinned PEB bases this sizes the shear keys (IN_Ex1: 1,543 kN against 98 kN from the analysis) |

## Open owner decision
- **D-T9, IS 18168 6.5 at end-plate splices (route B).** 6.5 asks for splices >= 3 db from a column face and a design
  strength >= 1.80 x the required strength (both applied), and "design strength of each flange splice plate shall at
  least be 1.2 Ry fy Af". An end-plate splice has no flange splice plate. The golds read the third sentence as
  applying to bolted or welded flange-plate splices only. If the owner rules that an end-plate splice must also
  develop 1.2 Ry fy Af at each flange, the IN_Ex2 / IN_Ex4 rafter splices need about four or five rows of M30 at each
  flange (the IN_Ex2 splices of 250 x 20 flanges: 2,520 kN, against about 1,200 kN of tension-flange bolts today).

## Not checked by the engine (EOR items, stated in each SOLUTION.md)
- Flange-to-web welds of the built-up members (shear flow, and the bolt-row tension at the knee); the butt splice of
  the knee-zone column flange plate to the column flange (CJP with a 1:4 taper).
- Kink forces where the inner flange of a tapered member changes direction (the knee and the end of the haunch).
- Through-thickness properties (lamellar tearing) of the 45-50 mm end plates under CJP flange welds.
- Temperature: IS 800 3.10.3.2 suggests the two lines of longitudinal bracing be no more than 50 m apart; the golds
  with end-bay bracing (IN_Ex1, IN_Ex2, IN_Ex4) exceed it, so the eave struts and the bracing between the braced bays
  are to be checked for the restrained temperature movement (no temperature load case in the engine).
- Crane brackets (IN_Ex3): the bracket-to-column welds, the column web at the bracket flanges, the gantry seat bolts
  and the surge torsion on the bracket.

## Not in this release
- Nonlinear analysis of tapered frames: they are marked not representable in the variations metrics, and exempt from
  that eligibility rule by default.
- The variations study on IN_Ex1 (scope deliverable 7.4).
- In the STAAD export, member wind, crane and the IS 800 4.3.6 notional loads. The file lists them as not exported.
