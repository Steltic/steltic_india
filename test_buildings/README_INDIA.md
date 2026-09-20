# Example briefs — steltic_india

USA AISC/ASCE example briefs in this folder are **non-authoritative** templates for geometry /
OpenSees modelling patterns only. Prefer the India briefs:

- `IN_Ex1_SCBF_5levels_Delhi.txt`
- `IN_Ex2_SMF_office_Mumbai.txt`
- `IN_Ex3_SMF_portal_Chennai_wind.txt`
- `IN_Ex4_SCBF_hospital_Kolkata.txt`
- `IN_Ex5_OMRF_warehouse_mezzanine_Hyderabad.txt`
- `IN_Ex6_EBF_8levels_Lplan_Pune.txt`
- `IN_Ex7_SCBF_10levels_Ahmedabad.txt`
- `IN_Ex8_OCBF_4levels_splitlevel_Jaipur.txt`
- `IN_Ex9_SPSW_12levels_Tplan_Guwahati.txt`
- `IN_Ex10_Dual_SMF_BRBF_18levels_Noida.txt`
- `IN_Ex11_SMF_3levels_Zplan_school_Chandigarh.txt`
- `IN_Ex12_SMF_podium_11levels_Kochi.txt`
- `IN_Ex13_SCBF_bigbox_flexdiaphragm_Indore.txt`
- `IN_Ex14_Crane_bay_OMRF_OCBF_Vizag.txt`
- `IN_Ex15_Gable_warehouse_snow_Shimla.txt`

EOR EXAMPLE fixtures (COMPLETE gate when Table 9 / Ω0 found:false) — **not-for-construction**:

- (Ex6 EBF EXAMPLE memo retired: R from Table 9 (ii)(c); file under usa_reference/)
- (Ex7 BRBF EXAMPLE memo retired: BRBF has no Indian basis, D3 -> SCBF; file under usa_reference/)
- `IN_Ex9_EOR_inputs_EXAMPLE.json` — SPSW
- `IN_Ex10_EOR_inputs_EXAMPLE.json` — dual SMF+BRBF
- `IN_Ex12_EOR_inputs_EXAMPLE.json` — soft-story SMF / Ω0

Agents must still LIVE-retrieve IS 875 / IS 1893 into `cfg['load_plan']` every job.
