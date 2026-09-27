# Example briefs — steltic_india

The 15 India briefs below are the design basis (IS 800 / IS 875 / IS 1893 / IS 18168 systems per
SYSTEM_TABLE). The shipped US-basis briefs and the retired EXAMPLE memos live under `usa_reference/`
and are not loaded:

- `IN_Ex1_SCBF_5levels_Delhi.txt`
- `IN_Ex2_SMF_office_Mumbai.txt`
- `IN_Ex3_SMF_portal_Chennai_wind.txt`
- `IN_Ex4_SCBF_hospital_Kolkata.txt`
- `IN_Ex5_OMRF_warehouse_mezzanine_Hyderabad.txt`
- `IN_Ex6_EBF_8levels_Lplan_Pune.txt`
- `IN_Ex7_SCBF_10levels_Ahmedabad.txt`
- `IN_Ex8_OCBF_4levels_splitlevel_Jaipur.txt`
- `IN_Ex9_EBF_12levels_Tplan_Guwahati.txt`
- `IN_Ex10_SCBF_18levels_slender_Noida.txt`
- `IN_Ex11_SMF_3levels_Zplan_school_Chandigarh.txt`
- `IN_Ex12_SMF_podium_11levels_Kochi.txt`
- `IN_Ex13_SCBF_bigbox_flexdiaphragm_Indore.txt`
- `IN_Ex14_Crane_bay_OMRF_OCBF_Vizag.txt`
- `IN_Ex15_Gable_warehouse_SMF_SCBF_snow_Shimla.txt`

Retired EOR EXAMPLE memos (not loaded, **not-for-construction**):

- (Ex6 EBF EXAMPLE memo retired: R from Table 9 (ii)(c); file under usa_reference/)
- (Ex7 BRBF EXAMPLE memo retired: BRBF has no Indian basis, D3 -> SCBF; file under usa_reference/)
- (Ex9 SPSW EXAMPLE memo retired: SPSW has no Indian basis, D3 -> EBF in Zone V per IS 18168 1.3; usa_reference/)
- (Ex10 dual SMF+BRBF EXAMPLE memo retired: no dual claim, SCBF sole system per IS 18168 1.3; usa_reference/)
- (Ex12 soft-storey SMF / overstrength EXAMPLE memo retired: R from Table 9 i)(d), no transfer girder in the brief and no
  foreign overstrength factor (D02); file under usa_reference/)

Agents must still LIVE-retrieve IS 875 / IS 1893 into `cfg['load_plan']` every job.
