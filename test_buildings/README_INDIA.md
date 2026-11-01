# Example briefs — steltic_india

The 21 India briefs below are the design basis (IS 800 / IS 875 / IS 1893 / IS 18168 systems per SYSTEM_TABLE). They
are numbered so that **the most common building types come first**: what Indian steel engineers design most often —
the pre-engineered (PEB) shed and warehouse — then the other single-storey industrial buildings, then braced and
moment-frame buildings by height. The numbering changed on 2026-10; the old-to-new map is
[`RENUMBERING_2026-10.md`](RENUMBERING_2026-10.md).

| # | Brief | Building | Status |
|---|---|---|---|
| 1 | `IN_Ex1_PEB_factory_shed_tapered_Bengaluru.txt` | PEB factory shed, 30 m clear span, tapered welded portals, pinned bases, brick dado (Zone II) | runs (PEB release) |
| 2 | `IN_Ex2_PEB_GradeA_warehouse_multispan_Bhiwandi.txt` | Grade A logistics warehouse, 4 x 24 m modular frames, 12 m clear height, dock canopy, solar-ready roof (Zone III) | runs (PEB release, D-T2 route B) |
| 3 | `IN_Ex3_PEB_crane_shed_10t_Nagpur.txt` | PEB crane shed, 24 m span, 10 t EOT crane on column brackets, fixed bases (Zone II) | runs (PEB release) |
| 4 | `IN_Ex4_PEB_warehouse_SMRF_Zone4_NCR.txt` | PEB fulfilment warehouse in Zone IV, SMRF portals — the D4 gate on a PEB (Farrukhnagar, NCR) | runs (PEB release, D-T2 route B) |
| 5 | `IN_Ex5_PEB_rooftop_solar_check_Bengaluru.txt` | Rooftop PV on the existing IN_Ex1 shed: check as built, PV capacity of the roof | runs (PEB release; a check of the IN_Ex1 gold) |
| 6 | `IN_Ex6_OMRF_warehouse_mezzanine_Hyderabad.txt` | Multi-bay OMRF warehouse + storage mezzanine (Zone II) | runs today |
| 7 | `IN_Ex7_Crane_bay_OMRF_OCBF_Vizag.txt` | Crane-bay industrial building, 200 kN EOT crane, cyclone belt | runs today |
| 8 | `IN_Ex8_SMF_portal_Chennai_wind.txt` | Single-storey SMF portal shed, wind-governed, cyclone belt (Zone III) | runs today |
| 9 | `IN_Ex9_Gable_warehouse_SMF_SCBF_snow_Shimla.txt` | Gable warehouse + lean-to office, snow (Zone IV) | runs today |
| 10 | `IN_Ex10_SCBF_bigbox_flexdiaphragm_Indore.txt` | Single-storey big-box retail, flexible roof diaphragm (Zone III) | runs today |
| 11 | `IN_Ex11_OCBF_4levels_splitlevel_Jaipur.txt` | 4-storey office + 2-storey workshop wing, OCBF, split-level (Zone II) | runs today |
| 12 | `IN_Ex12_SMF_3levels_Zplan_school_Chandigarh.txt` | 3-storey SMF school, three separated wings (Zone IV) | runs today |
| 13 | `IN_Ex13_SCBF_5levels_Delhi.txt` | 5-storey SCBF office (Zone IV) | runs today |
| 14 | `IN_Ex14_SCBF_hospital_Kolkata.txt` | 8-storey SCBF hospital, I = 1.5 | runs today |
| 15 | `IN_Ex15_EBF_8levels_Lplan_Pune.txt` | 8-storey EBF office, re-entrant plan (Zone III) | runs today |
| 16 | `IN_Ex16_SMF_office_Mumbai.txt` | 9-storey SMF office (Zone III) | runs today |
| 17 | `IN_Ex17_SCBF_10levels_Ahmedabad.txt` | 10-storey SCBF laboratory / office (Zone III) | runs today |
| 18 | `IN_Ex18_SMF_podium_11levels_Kochi.txt` | 11-storey SMF office with an open podium storey (Zone III) | runs today |
| 19 | `IN_Ex19_EBF_12levels_Tplan_Guwahati.txt` | 12-storey EBF residential, two units (Zone V) | runs today |
| 20 | `IN_Ex20_SCBF_18levels_slender_Noida.txt` | 18-storey slender SCBF office tower (Zone IV) | runs today |
| 21 | `IN_Ex21_MSME_angle_truss_shed_Hosur.txt` | Typical MSME shed: 18 m pin-jointed angle roof trusses with knee braces on ISMB columns, CFS purlins, brick dado (Zone II) | runs (angle-truss support, Steltic design ruling D-T10) |

**PEB release (2026-10):** IN_Ex1 … IN_Ex5 use welded plate I-sections, web-tapered members, flange braces and the
owner decisions recorded in [`docs/PEB_TAPERED_SCOPE.md`](../docs/PEB_TAPERED_SCOPE.md) and
[`CHANGES_2026-10-peb.md`](../CHANGES_2026-10-peb.md) (D-T1 … D-T7). They are served by the API (`/api/example/in1` …
`in5`) and offered in the UI pickers. IN_Ex21 (added 2026-11, after the renumbering) is the angle-truss MSME shed of a
south Indian industrial estate: pin-jointed angle trusses with knee braces (Steltic design ruling D-T10: the knee
designed for 1.2 times the moment the knee brace can deliver, with HSFG 8.8 bolts and complete-penetration welds at
the column), served as `/api/example/in21` (`CHANGES_2026-10-msme-shed.md`). Each brief still tells the agent to stop with design_status 'blocked' on an
engine without tapered sections.

The shipped US-basis briefs and the retired EXAMPLE memos live under `usa_reference/` and are not loaded.
Retired EOR EXAMPLE memos (not loaded, **not-for-construction**; numbers as renumbered 2026-10):

- (IN_Ex15 EBF EXAMPLE memo retired: R from Table 9 (ii)(c); file under usa_reference/)
- (IN_Ex17 BRBF EXAMPLE memo retired: BRBF has no Indian basis, D3 -> SCBF; file under usa_reference/)
- (IN_Ex19 SPSW EXAMPLE memo retired: SPSW has no Indian basis, D3 -> EBF in Zone V per IS 18168 1.3; usa_reference/)
- (IN_Ex20 dual SMF+BRBF EXAMPLE memo retired: no dual claim, SCBF sole system per IS 18168 1.3; usa_reference/)
- (IN_Ex18 soft-storey SMF / overstrength EXAMPLE memo retired: R from Table 9 i)(d), no transfer girder in the brief and
  no foreign overstrength factor (D02); file under usa_reference/)

Agents must still LIVE-retrieve IS 875 / IS 1893 into `cfg['load_plan']` every job.
