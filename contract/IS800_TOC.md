# IS 800:2007 — clause map for RAG queries

The authoritative text lives in the India RAG corpus (stem `IS_800_2007`, collection
`engineering_standards_IS800`). Query by clause id (`clause="8.2.2"`, `clause="Table 4"`); never quote
clause text from memory.

| Section | Clauses you will use |
|---|---|
| 1 General | 1.8 member axes (z-z major, y-y minor) |
| 2 Materials | 2.2 structural steel (IS 2062 grades E250/E350/E410/E450), 2.4 bolts |
| 3 General design requirements | 3.5 load combinations, 3.7 section classification (Table 2), 3.8 maximum slenderness (Table 3), 3.9 resistance to horizontal forces, 3.10 expansion joints |
| 4 Methods of analysis | 4.3.6 notional horizontal loads (0.5 % of factored gravity), 4.4 elastic analysis, 4.6 frame buckling / Annex D effective length |
| 5 Limit state design | 5.3 actions (Table 4 partial safety factors for loads), 5.4 strength (Table 5 partial safety factors for materials: gamma_m0 1.10, gamma_m1 1.25), 5.6 serviceability (Table 6 deflection limits) |
| 6 Tension members | 6.2 yielding, 6.3 rupture (6.3.3 angles), 6.4 block shear |
| 7 Compression members | 7.1.2 design compressive strength (buckling classes, Table 7, Table 10), 7.2 effective length (Table 11), 7.4 column bases (7.4.3.1 slab base thickness), 7.5 angle struts |
| 8 Bending | 8.2.1 laterally supported (8.2.1.2 low / high shear), 8.2.2 laterally unsupported (LTB, Annex E Mcr), 8.3 effective length for LTB (Table 15), 8.4 shear, 8.9 purlins and girts |
| 9 Combined forces | 9.2 shear and bending, 9.3.1 section strength (9.3.1.1 plastic/compact interaction), 9.3.2 overall member strength (9.3.2.2 bending + axial compression, Table 18 Cm) |
| 10 Connections | 10.2 fastener spacing/edge, 10.3 bearing bolts (10.3.3 shear, 10.3.4 bearing, 10.3.5 tension, 10.3.6 combined), 10.4 HSFG (10.4.3 slip), 10.5 welds (10.5.7 fillet strength), 10.7 minimum design action |
| IS 800 12 Earthquake | IS 800 12.2 load combinations (IS 800 12.2.3 column/connection 2.5 EL), IS 800 12.3 R, IS 800 12.4 connections, IS 800 12.5 columns, IS 800 12.7 OCBF, IS 800 12.8 SCBF, IS 800 12.9 EBF, IS 800 12.10 OMF, IS 800 12.11 SMF (IS 800 12.11.2 beam-column joint, IS 800 12.11.3 column requirements), IS 800 12.12 column bases |
| 13 Fatigue | 13.1-13.6 (crane girders and other fluctuating-stress members) |

Companion stems: `IS_808_2021` (sections), `IS_816_1969` (welding), `IS_9595_1996`, `IS_4000_1992` (HSFG),
`IS_1161_2014` (tubes), `IS_2062_Part_1_2025` (steel), `IS_18168_2023` (EBF links).
Loads (mandatory every job): `IS_875_Part_1_2026` … `IS_875_Part_5_1987`, `IS_1893_Part_1_2016` (with
Amendments 1 and 2).
