# Example briefs — steltic_india

USA AISC/ASCE example briefs in this folder are **non-authoritative** templates for geometry /
OpenSees modelling patterns only. Prefer the India briefs:

- `IN_Ex1_SCBF_5levels_Delhi.txt`
- `IN_Ex2_SMF_office_Mumbai.txt`
- `IN_Ex3_Industrial_portal_Chennai_wind.txt`
- `IN_Ex4_Dual_SMF_SCBF_hospital_Kolkata.txt`
- `IN_Ex5_OMRF_warehouse_mezzanine_Hyderabad.txt`
- `IN_Ex6_EBF_8levels_Lplan_Pune.txt`
- `IN_Ex7_BRBF_10levels_Ahmedabad.txt`
- `IN_Ex8_OCBF_4levels_splitlevel_Jaipur.txt`
- `IN_Ex9_SPSW_12levels_Tplan_Guwahati.txt`
- `IN_Ex10_Dual_SMF_BRBF_18levels_Noida.txt`
- `IN_Ex11_SMF_3levels_Zplan_school_Chandigarh.txt`
- `IN_Ex12_SMF_softstory_podium_Kochi.txt`
- `IN_Ex13_OCBF_bigbox_flexdiaphragm_Indore.txt`
- `IN_Ex14_Crane_bay_IMF_Vizag.txt`
- `IN_Ex15_Gable_warehouse_snow_Shimla.txt`

EOR EXAMPLE fixtures (COMPLETE gate when Table 9 / Ω0 found:false) — **not-for-construction**:

- `IN_Ex6_EOR_inputs_EXAMPLE.json` — EBF
- `IN_Ex7_EOR_inputs_EXAMPLE.json` — BRBF
- `IN_Ex9_EOR_inputs_EXAMPLE.json` — SPSW
- `IN_Ex10_EOR_inputs_EXAMPLE.json` — dual SMF+BRBF
- `IN_Ex12_EOR_inputs_EXAMPLE.json` — soft-story SMF / Ω0

Agents must still LIVE-retrieve IS 875 / IS 1893 into `cfg['load_plan']` every job.
