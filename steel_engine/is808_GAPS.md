# IS 808 shapes database — gaps

**Built:** from IS 808:2021 Tables 1–13 via `pdftotext -layout` → `build_is808_shapes.py`
**Output:** `steel_engine/is808_shapes.csv` (554 rows)
**Parse errors/skipped lines:** 1

## Ingested
- Table 1: Medium / Wide flange beams (MB, WB)
- Table 2: Junior / Light beams (JB, LB)
- Table 3: Narrow parallel flange beams (NPB …×…×mass)
- Table 4: Wide parallel flange beams (WPB …×…×mass)
- Table 5: Column / heavy beam sections (SC, HB)
- Tables 6–8: channels (MC, JC, LC, MPC) — Cy column handled
- Tables 9–12: equal / unequal angles (ISA a×b×t)
- Table 13: bearing piles (PBP …×mass)

## Counts by Type
- HB: 17
- ISA: 198
- JB: 4
- JC: 5
- LB: 17
- LC: 15
- MB: 14
- MC: 20
- MPC: 20
- NPB: 70
- PBP: 29
- SC: 9
- WB: 14
- WPB: 122

## Remaining / out of scope
- Annex A/B formula-only custom sections — agent must compute via RAG, not invent
- OCR digit-drop on a few ry values: auto-corrected when ry ≪ 0.08·B (documented heuristic)

## Units
Pipeline still kip+inch. CSV properties converted from IS 808 SI multipliers;
`A_si_mm2` / `Izz_si_mm4` / `Iyy_si_mm4` retain SI for audit.

## Lookup labels
- Beams/cols: `MB200`, `LB150`, `SC250`, `NPB100X55X8.1`, …
- Channels: `MC200`, `JC150`, `LC300`, `MPC250`
- Angles: `ISA50X50X6`, `ISA100X75X10` (also Designation_IS spaced form)
- Piles: `PBP200X43.85`
- Duplicates append mass suffix (`WB200X28.8`)

## IS 1161 tubes (separate CSV)
Circular hollow sections live in `is1161_tubes.csv` (81 rows) built from IS 1161:2014 Table 1
via `tools/build_is1161_tubes.py`. Labels: `CHS{OD}X{t}` and `NB{nb}X{t}` where NB captured.
Dual-path: `sections.props` / `engine3d.Ipack` load IS 808 + IS 1161 before AISC.
