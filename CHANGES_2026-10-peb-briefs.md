# steltic-india — 2026-10: PEB example briefs, renumbering, PEB scope revision 2

Branch `fix/2026-10-peb-briefs`. No engine logic changes: every existing job designs exactly as before. What changes is
which example briefs exist, their numbers, and the documents an agent reads.

## Example briefs: most common building types first

- **Five new PEB briefs**, IN_Ex1 … IN_Ex5 (RETRIEVE style, no IS values except the occupancy's I):
  - IN_Ex1 PEB factory shed, 30 m clear span, tapered welded portals, pinned bases, brick dado, Bengaluru (Zone II);
  - IN_Ex2 Grade A logistics warehouse, 4 × 24 m modular frames, 12 m clear height, dock canopy, sprinkler collateral,
    solar-ready roof, Bhiwandi (Zone III, map reading);
  - IN_Ex3 PEB crane shed, 24 m span, 10 t EOT crane on brackets, fixed bases, Nagpur (Zone II);
  - IN_Ex4 PEB fulfilment warehouse in Zone IV, SMRF portals (the D4 gate on a PEB), Farrukhnagar, NCR;
  - IN_Ex5 rooftop solar PV on the IN_Ex1 shed as built: a check, not a design, with the roof's PV capacity.
  They need the PEB release (tapered welded members): each opens with a paragraph telling the agent to stop with
  design_status 'blocked' if the engine cannot take tapered sections. The API serves them (`in1` … `in5`); the UI
  picker does not offer them until the PEB release lands.
- **The 15 existing briefs are renumbered IN_Ex6 … IN_Ex20**: single-storey industrial buildings first, then braced
  and moment-frame buildings by height. Old → new: Ex1 → 13, Ex2 → 16, Ex3 → 8, Ex4 → 14, Ex5 → 6, Ex6 → 15, Ex7 → 17,
  Ex8 → 11, Ex9 → 19, Ex10 → 20, Ex11 → 12, Ex12 → 18, Ex13 → 10, Ex14 → 7, Ex15 → 9. Brief texts are unchanged
  except their ids. Full map and policy: `test_buildings/RENUMBERING_2026-10.md`.
- The rename was mechanical (`scripts/renumber_2026-10.py`): every `IN_ExN` / `IN_CFS_ExN` id in file and folder
  names and in every text file, in one pass (briefs, `usa_reference/` originals and memos, `tests/fixtures/IN_Ex13/`,
  engine comments, the contract, tests). Dated records (`CHANGES_2026-09-review.md`, `docs/INDIA_COMPLETE_GAP_WAVE*.md`,
  `docs/INDIA_HR_POLISH_WAVE_D.md`) keep the old numbers and now carry a note at the top. One user-visible message
  string changes ("… (IN_Ex8 pattern)" in `india_loads.py`).
- Pickers: `steltic/main.py` serves `in1` … `in20` (inN = IN_ExN); `frontend/index.html` offers in6 … in20 with the
  hub's labels (the stale BRBF / SPSW / IMF labels are gone).
- `test_buildings/README_INDIA.md` lists the 20 briefs with building type and status.

## Documents

- `docs/PEB_TAPERED_SCOPE.md` — the agent scope for tapered PEB frames, revision 2: corrected from the IS corpus
  (slender webs by IS 800 3.7.2 (d); HSFG bolts 12.4.1; joint design moments 12.10.2.1 / 12.11.2.1; fixed bases
  12.12.1; Table 6 H/240 for masonry cladding; E250 B for an IS 800 12.11 SMRF; IS 18168 optional for industrial
  buildings under 1.2), new owner decisions D-T6 (scope of 12.4.2), D-T7 (Mp at a tapered joint face) and D-T8 (the
  IN_Ex9 IS 18168 wording), a sharper D-T2 (two Zone III–V routes), and four new deliverables (reactions.csv, anchor
  bolt plan, BOM, STAAD.Pro export).
- `scripts/renumber_2026-10.py` — the renumbering tool; `tree` mode renames a copy of the gold packs and the website
  solutions (the source is never changed).

## Tests

- `test_fix_D01_brief_lint.py`: 20 briefs; the cyclone / re-entrant id sets and the per-brief tests follow the new
  numbers (Ex8 / Ex7 cyclone belt, Ex15 re-entrant, Ex14 hospital k1, Ex9 Shimla, Ex7 OMRF row).
- `test_india_contract.py`: the UI picker offers in6 … in20; the engine serves in1 … in20 and each maps to IN_ExN.
- `tests/fixtures/zone_system_cfgs.json`: keys renamed with their briefs (Ex8, Ex9, Ex6, Ex10, Ex7,
  legacy_Ex10_OCBF_ZoneII); `test_fix_D02.py`, `test_india_core.py`, `test_india_seismic_wp1.py` follow.
- Full suite, no corpus: **961 passed, 4 skipped** (916 + the 45 lint cases of the five new briefs).
