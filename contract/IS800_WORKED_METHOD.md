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
  (`LLT_sag`, `LLT_hog` in the cfg member inputs); the framework does not guess it.

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
   KL/r <= 160; plastic brace section; brace connection force 1.1 fy Ag (CHS219.1x8, fy 250 -> 1459 kN
   whatever the analysis force); SCBF columns plastic.
5. OMF (IS 800 12.10): connections for min(1.2 Mp of the beam, deliverable moment).
6. SMF (IS 800 12.11): beam-to-column connections for 1.2 Mp of the beam; shear from 1.2DL + 0.5LL plus
   2 (1.2 Mp) / L'; panel zone per joint with doubler / web thickness each >= (dp + bp)/90; continuity
   plates; sum Mpc / sum Mpb >= 1.2 at EVERY joint from the model connectivity, Mpc reduced for axial load.
7. Column bases (IS 800 12.12): fixed bases and anchors for 1.2 Mp of the column; shear >= the larger of the
   full column shear and 1.2 Vd.
8. EBF: IS 800 points to specialist literature -- use IS 18168:2023 with the links modelled.

Every check goes into `calc_package.capacity_design.checks` as
`{value, limit, dc, ok, clause, cite, source}`; a failing or found:false item blocks COMPLETE.
