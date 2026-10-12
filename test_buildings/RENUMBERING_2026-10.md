# Renumbering of the India example briefs (2026-10)

The example briefs are numbered so that **the most common building types come first**: what Indian steel engineers
design most often (PEB sheds and warehouses, other single-storey industrial buildings) before braced and moment-frame
buildings, which follow by height. Five new PEB briefs take IN_Ex1 … IN_Ex5; the 15 existing HR briefs move to
IN_Ex6 … IN_Ex20. The 15 CFS briefs keep their count and are reordered the same way (portals first, then storey count).

Use this table to read any document dated before 2026-10.

## HR (steltic_india)

| New | Old | Brief (title part of the file name) |
|---|---|---|
| IN_Ex1 | new | `PEB_factory_shed_tapered_Bengaluru` |
| IN_Ex2 | new | `PEB_GradeA_warehouse_multispan_Bhiwandi` |
| IN_Ex3 | new | `PEB_crane_shed_10t_Nagpur` |
| IN_Ex4 | new | `PEB_warehouse_SMRF_Zone4_NCR` |
| IN_Ex5 | new | `PEB_rooftop_solar_check_Bengaluru` |
| IN_Ex6 | IN_Ex5 | `OMRF_warehouse_mezzanine_Hyderabad` |
| IN_Ex7 | IN_Ex14 | `Crane_bay_OMRF_OCBF_Vizag` |
| IN_Ex8 | IN_Ex3 | `SMF_portal_Chennai_wind` |
| IN_Ex9 | IN_Ex15 | `Gable_warehouse_SMF_SCBF_snow_Shimla` |
| IN_Ex10 | IN_Ex13 | `SCBF_bigbox_flexdiaphragm_Indore` |
| IN_Ex11 | IN_Ex8 | `OCBF_4levels_splitlevel_Jaipur` |
| IN_Ex12 | IN_Ex11 | `SMF_3levels_Zplan_school_Chandigarh` |
| IN_Ex13 | IN_Ex1 | `SCBF_5levels_Delhi` |
| IN_Ex14 | IN_Ex4 | `SCBF_hospital_Kolkata` |
| IN_Ex15 | IN_Ex6 | `EBF_8levels_Lplan_Pune` |
| IN_Ex16 | IN_Ex2 | `SMF_office_Mumbai` |
| IN_Ex17 | IN_Ex7 | `SCBF_10levels_Ahmedabad` |
| IN_Ex18 | IN_Ex12 | `SMF_podium_11levels_Kochi` |
| IN_Ex19 | IN_Ex9 | `EBF_12levels_Tplan_Guwahati` |
| IN_Ex20 | IN_Ex10 | `SCBF_18levels_slender_Noida` |

Old → new, for reading old documents: Ex1 → Ex13, Ex2 → Ex16, Ex3 → Ex8, Ex4 → Ex14, Ex5 → Ex6, Ex6 → Ex15, Ex7 → Ex17, Ex8 → Ex11, Ex9 → Ex19, Ex10 → Ex20, Ex11 → Ex12, Ex12 → Ex18, Ex13 → Ex10, Ex14 → Ex7, Ex15 → Ex9.

## CFS (steltic_CFS_india)

| New | Old | Brief (title part of the file name) |
|---|---|---|
| IN_CFS_Ex1 | IN_CFS_Ex2 | `HR_SMF_portal_Chennai_wind` |
| IN_CFS_Ex2 | IN_CFS_Ex15 | `HR_SMF_portal_coldstorage_Srinagar` |
| IN_CFS_Ex3 | IN_CFS_Ex5 | `Portal_allCFS_elastic_Hyderabad` |
| IN_CFS_Ex4 | IN_CFS_Ex10 | `OCBF_highbay_2levels_Nagpur` |
| IN_CFS_Ex5 | IN_CFS_Ex11 | `OCBF_3levels_coastal_Vizag` |
| IN_CFS_Ex6 | IN_CFS_Ex14 | `SCBF_clinic_splitlevel_Coimbatore` |
| IN_CFS_Ex7 | IN_CFS_Ex1 | `SCBF_4levels_Delhi` |
| IN_CFS_Ex8 | IN_CFS_Ex8 | `SCBF_4levels_Tplan_Ahmedabad` |
| IN_CFS_Ex9 | IN_CFS_Ex13 | `SCBF_4levels_Lucknow` |
| IN_CFS_Ex10 | IN_CFS_Ex3 | `SCBF_5levels_Mumbai` |
| IN_CFS_Ex11 | IN_CFS_Ex6 | `SCBF_5levels_Lplan_Pune` |
| IN_CFS_Ex12 | IN_CFS_Ex4 | `OCBF_6levels_Bengaluru` |
| IN_CFS_Ex13 | IN_CFS_Ex7 | `SCBF_6levels_Zplan_Surat` |
| IN_CFS_Ex14 | IN_CFS_Ex9 | `SCBF_podium_5over2_Uplan_Noida` |
| IN_CFS_Ex15 | IN_CFS_Ex12 | `SCBF_8levels_crossplan_Kolkata` |

Old → new: Ex1 → Ex7, Ex2 → Ex1, Ex3 → Ex10, Ex4 → Ex12, Ex5 → Ex3, Ex6 → Ex11, Ex7 → Ex13, Ex8 → Ex8, Ex9 → Ex14, Ex10 → Ex4, Ex11 → Ex5, Ex12 → Ex15, Ex13 → Ex9, Ex14 → Ex6, Ex15 → Ex2.

## What was changed, and what was not

- **Changed everywhere in the four repos:** the brief ids `IN_ExN` / `IN_CFS_ExN` in file and folder names (briefs,
  `usa_reference/` originals and EOR memos, test fixtures such as `tests/fixtures/IN_Ex13/`, the nonlinear fixtures
  `IN_Ex13_pkg/` and `IN_Ex16_pkg/`) and in every text file, in one pass (`scripts/renumber_2026-10.py`). The vendored HR engine copies in steltic_CFS_india and steltic_nonlinear_india changed identically.
- **Example pickers:** `/api/example/inN` serves `IN_ExN` (HR, in1 … in20) and `IN_CFS_ExN` (CFS, in1 … in15). The HR
  UI pickers (hub manifest and the engine's own page) offered in6 … in20 until the PEB release (2026-10) made in1 … in5
  runnable; they now offer in1 … in20.
- **Short forms that clearly meant an India brief** in live code comments and agent contracts (for example "Ex5" for
  the all-CFS portal) were rewritten to the full new id. Test data keys were renamed with their briefs (the zone /
  system fixture keys `Ex8`, `Ex9`, `Ex6`, `Ex10`, `Ex7`, `legacy_Ex10_OCBF_ZoneII`; the brief-lint id sets).
- **Not changed:**
  - dated records (CHANGES files, review logs, runbooks, gap-wave reports). They keep the old numbers and carry a
    note at the top pointing here;
  - Python identifiers and test names that embed an old number (`ex1_cfg`, `_ex1_fixture`, `EX14`, `test_wp3_ex1_ex5`
    and similar), which are internal names, not brief ids;
  - bare short forms that may mean the US example sets the engines still carry (HR `ex1 … ex35`, CFS `ex1 … ex30`) or
    the nonlinear repo's US examples (`Ex18_R3`, `Ex22_SMF`).
- **Outside git (owner's PC):** the gold packages (`india_gold_HR_CFS_2026-09-27`, `india_gold_NL_2026-10-04`) and the
  website solution folders are named by the old numbers. `python3 scripts/renumber_2026-10.py tree <src> <dst>` writes a renamed
  copy (folders renamed, ids rewritten inside html / json / md / txt / py / csv files); the source is never changed.
