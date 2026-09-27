# IS 800:2007 worked method (member and system checks)

This is the check SEQUENCE the framework's `india_is800.member_check_is800` and
`india_is800_s12.section12_checks` follow, with hand values you can use to confirm a result. Numbers
are N, mm, MPa unless stated. Verify every clause you rely on against the RAG
(`collection="engineering_standards_IS800"`, `clause="<id>"`).

## 1. Material and section
1. fy from IS 2062 by grade AND thickness (use max(tf, tw)): E250 250 (t <= 16), 240 (16-40), 230 (40-100);
   E350 350 / 330 / 320. Never a default 250.
2. Section class from IS 800 Table 2 with epsilon = sqrt(250/fy) (plastic / compact / semi-compact / slender).
3. Buckling class from Table 10 (rolled I: h/b > 1.2 and tf <= 40 -> a about z-z, b about y-y; h/b <= 1.2 ->
   b / c; welded I -> b / c; hollow hot-finished -> a, cold-formed / ERW -> b; angles, channels, tees -> c).

## 2. Compression -- 7.1.2
fcd = (fy/gamma_m0) / (phi + sqrt(phi^2 - lambda^2)), phi = 0.5 [1 + alpha (lambda - 0.2) + lambda^2],
lambda = sqrt(fy (KL/r)^2 / (pi^2 E)), alpha from Table 7 (a 0.21, b 0.34, c 0.49, d 0.76). KL = the element's
OWN length x K (Table 11 / Annex D; K = 1.0 unless justified). Maximum KL/r per Table 3.

Hand values: MB400, E250, KL = 3.6 m: Pdz = 1761.4 kN (class a); Pdy = 649.5 kN (class b, chi = 0.3645).
WPB800X300X317.36, fy 240, KL = 5400 mm: Pdy = 5955 kN.

## 3. Bending -- 8.2.1 (restrained) and 8.2.2 (lateral-torsional buckling)
* 8.2.1.2: Md = beta_b Zp fy / gamma_m0 (beta_b = 1 plastic/compact, Ze/Zp semi-compact), capped at
  1.2 Ze fy / gamma_m0 for simply supported beams (1.5 for cantilevers); high shear (V > 0.6 Vd) reduces Md.
* 8.2.2: Md = beta_b Zp fbd; fbd = chi_LT fy / gamma_m0; Mcr per Annex E; alpha_LT 0.21 rolled, 0.49 welded;
  lambda_LT <= 0.4 -> no LTB reduction.
* LLT is the PHYSICAL unbraced length of the compression flange for each moment sign: a deck restrains the
  top flange (sagging), uplift / hogging needs the fly-brace spacing. Declare it per member group
  (`cfg['LLT_sag_mm']`, `cfg['LLT_hog_mm']`, a number or `{role: mm}`; per member or per column in
  `cfg['member_overrides']`); the framework does not guess it.
* Channels (IS 808 ISMC purlins / girts): Mcr by the IS 800 Annex E general expression (load through the shear
  centre, It = J, Iw = Cw); declare the restraint spacing (sag rods / fly braces) as LLT.

Hand values: MB450, LLT = 3 m: Md = 271.3 kNm. NPB400X180X57.38, LLT = 3040 mm: Md = 217.0 kNm
(lambda_LT <= 0.4 needs LLT <= 1611 mm). CHS168.3x8 simply supported: Md cap = 42.04 kNm.

## 4. Shear -- 8.4
Vd = Av fy / (sqrt(3) gamma_m0); shear buckling (8.4.2) when d/tw > 67 epsilon.

## 5. Tension -- 6.2 / 6.3 / 6.4
Tdg = Ag fy / gamma_m0; Tdn = 0.9 An fu / gamma_m1 (angles 6.3.3); block shear 6.4.1 -- evaluate BOTH
expressions and take the smaller.

## 6. Combined -- 9.3.1 and 9.3.2.2 (per combination, concurrent forces)
Evaluate every combination with its OWN P, Mz, My (never the envelope maxima of each):
* 9.3.1: section strength (plastic/compact interaction with Mndz, Mndy reduced for n = N/Nd).
* 9.3.2.2: P/Pdy + Ky Cmy My/Mdy + KLT Mz/Mdz <= 1 and P/Pdz + 0.6 Ky Cmy My/Mdy + Kz Cmz Mz/Mdz <= 1,
  Cm from Table 18 using the end moments of that combination.

Hand values: Ex10 element 73 (WPB800X300X317.36, L 5400, P = 7213 kN, Mz = 159 kNm, My = 15.5 kNm):
P/Pdy = 1.21. Ex12 level-1 WPB800 at 6.6 m: 9.3.2.2 ~ 1.52.

## 7. Earthquake systems -- IS 800 Section 12 (after the member checks)
1. Combinations: IS 800 12.2.3 (1.2DL + 0.5LL +- 2.5EL and 0.9DL +- 2.5EL) for columns with P/Pd > 0.4 and for
   connections -- generated automatically and tagged `[col]`.
2. Connections (IS 800 12.4): slip-critical HSFG or turned-and-fitted bolts (10.4.3 slip check); complete
   penetration butt welds except column splices (record any EOR exception); no load sharing between bolts
   and welds.
3. OCBF (IS 800 12.7): KL/r <= 120; P <= 0.8 Pd; 30-70 % tension share; connection force min(1.2 fy Ag,
   12.2.3 force); gusset checks.
4. SCBF (IS 800 12.8): braces of E250B (IS 2062) unless an EOR exception / IS 18168 basis is recorded;
   KL/r <= 160 with the per-axis K (Kz L on rz, Ky L on ry); plastic brace section; brace compression from the
   Table 4 combinations; brace connection force 1.1 fy Ag (CHS219.1x8, fy 250 -> 1459 kN whatever the analysis
   force); SCBF columns plastic. Where IS 18168 applies the force is max(1.1 Ry fy Ag, Ru fu An) (10.4.1(a)):
   An = the declared `An_mm2`, else Ag — for E250 (Ry 1.4, Ru 1.2, fy 250, fu 410) that is 1.2 x 410 Ag = 492 Ag N
   (1.97 fy Ag) against 1.54 fy Ag = 385 Ag N, so Ru fu An governs unless An < 0.78 Ag.
5. OMF (IS 800 12.10): connections for min(1.2 Mp of the beam, deliverable moment).
6. SMF (IS 800 12.11): beam-to-column connections for 1.2 Mp of the beam; shear from 1.2DL + 0.5LL plus
   2 (1.2 Mp) / L'; panel zone per joint with doubler / web thickness each >= (dp + bp)/90 (a built-up box
   counts both webs, and the joint is checked in both frame directions); continuity plates; sum Mpc / sum Mpb
   >= 1.2 at EVERY joint from the model connectivity, Mpc reduced for axial load. IS 18168 8.2: sum Zpc fyc
   (1 - Pu/Pd) / sum 1.1 Ry Zpb fyb > 1.4 (not at the roof, 8.2.1), Pu = the maximum factored axial compression
   over ALL combinations (literal, ruling R3; `scwb_pu_basis` 'seismic' = the Table 4 earthquake rows only).
7. Column bases (IS 800 12.12): fixed bases and anchors for 1.2 Mp of the column (IS 18168 9.3: 1.1 Ry Mpc and
   2.2 Ry Mpc / Hc); shear >= the larger of the full column shear and 1.2 Vd. Checked for EVERY combination
   with its concurrent (P, Mz, My, V): biaxial anchors (corner anchor = sum of the two tension-side shares),
   net uplift by anchor / bearing equilibrium, Mpc by the IS 800 9.3.1.2 form of the column (rolled I (c):
   1.11 Mp (1 - n) <= Mp; welded I (b); box / RHS (d); CHS (e)). A gusseted base is checked to IS 800 7.4.2
   (plate panels between gussets, gusset outstand / shear / bending, gusset welds); an embedded base against the
   EOR capacities (VERIFY). Anchor embedment (IS 456) is always an EOR input.
8. EBF (IS 800 12.9 points to specialist literature — IS 18168:2023 11 / 12.3 with the links modelled by
   `engine3d.add_link` and declared in `info['links']`): link Table 2 (iv) and the beam outside it Table 2 (i);
   shear link e < 1.6 MpL / VpL (11.3); link shear Vu <= Vd over the Table 4 earthquake rows; stiffeners 11.4
   (full-depth end stiffeners both sides, combined width >= bf - 2 tw, t >= max(0.75 tw, 10 mm); intermediate
   spacing <= 30 tw - d/5 for 0.08 rad); link rotation (L/e) x R x elastic storey drift <= 0.08 rad (12.3.3.1);
   braces, beams outside the link and columns for 1.1 Ry Sh Vd / 1.2 Ry Vd of the link (12.3.2.2, 12.3.4.5);
   links not connected to columns (12.3.1) and braced at both flanges (12.3.3.2); 12.3.4.4 beam-to-column
   joints where a brace or gusset frames in.
9. Column splices (IS 800 12.5.2): each flange splice of an SFRS column >= 1.2 fy Af (12.5.2.2), PJP welds
   200 % of the required strength (12.5.2.1); a CJP with matching electrode develops the parent metal
   (IS 800 10.5.7.1.2) and is deemed to comply (ruling R4) — the weld record is required. Flange force per
   combination: P Af/A + Mz/d + 3 My/bf with a web splice (P/2 + ... without); machined bearing ends (7.3.4.1)
   leave tension / bending plus the IS 800 5.1.2 tie (the largest factored DL + LL reaction of one floor, T/2 per
   flange). IS 18168 7.5 (and 12.2.4.6 SCBF / 12.3.4.7 EBF): 5.5 demands, plates >= 1.2 Ry x flange / web
   strength, >= 0.5 Mp of the smaller member and shear > sum Mp / Hc.
10. IS 18168 5.3 / Table 2 width-to-thickness limits are live wherever IS 18168 applies (beams (i), columns (ii)
   with Ca, braces (iii), links (iv); built-up boxes by the closed-box rows (B - 2 tw)/tf and (D - 2 tf)/tw).

Every check goes into `calc_package.capacity_design.checks` as
`{value, limit, dc, ok, clause, cite, source}`; a failing or found:false item blocks COMPLETE.
