# steltic-india — 2026-11 engine checks 3 (the review's notes N1–N3 on the consistency guards, the ponding slope)

Branch `fix/2026-11-engine-checks-3`, from main e45a65d (PR #33, `CHANGES_2026-11-engine-checks-2.md`). It covers
the low notes N1–N3 of the "Branch 2 review" in `briefs/ENG_REVIEW.md`, and the lead's ruling on the ponding guard's
roof slope (2026-11-07). Only `consistency.py` changes. No package,
digest or status reads these guards; they print in the report's consistency chapter and in `consistency.check`.

## N1. The ponding guard judges the roof's real span

- **Problem.** The guard asked whether any roof group's longest *element* is 12 m or more.
  - A PEB portal's rafters are short tapered pieces: IN_Ex1's longest is 9.04 m, on a 30 m span.
  - A flat roof's beams are split at the secondary beams.
  - So the guard could not fire on a PEB.
- **Fix** (`consistency._roofs_for_ponding`). Each roof is judged on its real span:
  - a roof plane: its eave-to-eave span (the frame span, `cfg['roof_planes']`);
  - the roof outside the planes (a flat roof, a lean-to): the longest roof element and, on an N-mm job without
    planes, the longest grid bay (the span of the roof beams between the column lines).
- **Slope (Steltic ruling, 2026-11-07).** The guard fires only on a long span (12 m or more) whose slope is flatter
  than 1 in 20, or unknown. The slope comes from:
  - a roof plane's flatter side;
  - otherwise the ponding input's `roof_slope`;
  - otherwise the declared `cfg['roof_pitch_deg']`.

  This is an engineering basis, not an IS criterion, and the message states it (`PONDING_SLOPE_BASIS`):
  - IS 875 (Part 4):2021 4.4 asks for the investigation on "flat roofs (or with a small slope)" and gives no number
    (corpus: `IS_875_Part_4_1987/markdown/pages_search/page_004.md`, the 2021 text).
  - The engine's 4.4 screen (`india_loads.ponding_screen_4_4`) requires the mid-span deflection to be less than the
    fall over the half span. At 1 in 20 that fall is span/40.
  - A roof meeting IS 800 Table 6 (span/180 for a rafter under profiled metal sheeting, corpus
    `IS_800_2007/markdown/pages_search/page_037.md`) passes the screen with a margin of 180/40 = 4.5.
- The message names the span, the slope and their sources.

## N2. A declared `composite_scope` clears the composite guard only with its worksheet

- **Problem.** `cfg['composite_scope']` cleared the guard even when the package had no worksheet: a build that
  failed (`composite_design.status = 'error'`), or no record at all.
- **Fix.** The scope clears the guard only when the worksheet's slots are in the package. The scope is read from the
  worksheet first, then the cfg. Honest found:false stubs still clear it (H6).
- **"A scope record that says no composite floor".** The contract has no such value: `COMPOSITE_INDIA.md` allows
  `bare_steel` and `delegated` only. A job without a composite floor does not trigger the guard, whose trigger is
  "composite" in `floor_system` / `arch` / `notes`. When the notes only mention a composite floor, the engine
  builds the found:false stubs from the same words, and those clear the guard.

## N3. The seismic joint needs the 7.11.3 record or a check tagged as the joint

- **Problem.** A designed label containing "separation" or "pounding" cleared the guard, for example a gusset's edge
  separation.
- **Fix.** The guard is cleared by one of:
  - the 7.11.3 separation record (`deformation_compatibility.separation`, from `cfg['adjacent_units']`);
  - a designed connection or computed check whose label says "seismic joint" (`seismic_joint`, `seismic-joint`) or
    "7.11.3".

## Tests, mutation checks, suite

`tests/test_engine_checks_2026_11_checks3.py`, 4 tests, each on a real gold package. The fixtures in
`tests/fixtures/engine_checks_2026_11/` are cut from the e45a65d gold runs (`gold/runs/eng10`) by
`gold/tools/make_fixtures_c3.py`, down to what the guards read:

| Note | Gold | What the test shows |
|---|---|---|
| N1 | IN_Ex1 (published PEB, 30 m portal at 1 in 10, no ponding screen; longest rafter piece 9.04 m) | The guard reads the plane: 30 m, 1 in 10. It stays quiet (not a small slope). The same portal at 1 in 50 fires with the stated basis, and the 4.4 screen clears it. |
| N1 | IN_Ex16 (flat roof, 7.5 m bays) | Quiet. With one 15 m bay (the roof beams still in 7.5 m pieces) it fires while the slope is unknown, or at 1 in 60 (IN_Ex10's form, without its screen). It is quiet at a declared 1 in 10 pitch. |
| N2 | IN_Ex16 (`composite_scope` bare_steel, worksheet evaluated) | Quiet. With the worksheet failed or missing it fires. Honest stubs still clear it. |
| N3 | IN_Ex12 unit B (its 7.11.3 separations), read as a two-wing plan | Quiet. Without the separation it fires. An unrelated "gusset_edge_separation" check does not clear it; "seismic_joint_width" and "IS 1893 7.11.3 gap" do. |

The engine checks 2 C1 test asserted that a scope alone clears the composite guard. It now asserts N2: a scope with
the worksheet clears it, a scope alone does not.

Mutation checks (`wt/ENG/tools/mutate7.py`, `logs/mutation9.txt`): **12 of 12 caught**.
- N1: the element length again; the roof planes not read; the grid bay not read.
- Slope: ignored; unknown taken as steep; the plane's slope not read; the declared slope not read; the limit at
  1 in 100.
- N2: the scope clears without a worksheet.
- N3: "separation" clears it; a 7.11.3 tag does not; the separation record not read.

Full HR suite under heavy at the head 263c8a0: **1,353 passed, 5 skipped** in 6 min 20 s
(`wt/ENG/logs/suite_c7.txt`). That is main's 1,349 plus the 4 new tests. It was the same at ba06d5c and 8f6b899
(`suite_c5.txt`, `suite_c6.txt`).

## Golds

- **`consistency.check`** compared old (e45a65d) against new `consistency.py` on all 30 gold packages of the e45a65d
  runs (`gold/results/consistency_c7.json` at the head): **all 30 lists are identical**.
  - At ba06d5c (the span rule without the slope), five lists gained a ponding finding: IN_Ex21 (18 m), and IN_Ex1
    and IN_Ex5 in both sets (30 m). Their roofs are 1 in 4 and 1 in 10, so under the slope ruling they are quiet
    again.
  - N2 and N3 move no gold.
- **The roofs the guard reads** (`gold/results/roof_slopes_c6.txt`):

  | Gold | Long roof (>= 12 m) | Slope | 4.4 screen |
  |---|---|---|---|
  | IN_Ex21 | roof plane 18 m | 1 in 4 | no (not needed) |
  | IN_Ex1, IN_Ex5 (both sets) | roof plane 30 m | 1 in 10 | no (not needed) |
  | IN_Ex3, IN_Ex4 (both sets) | roof plane 24 / 30 m | 1 in 10 | yes |
  | IN_Ex2 (both sets) | roof plane 96 m, 14.4 m member | 1 in 20 | yes |
  | IN_Ex7, IN_Ex8 | roof members 21 / 24 m (declared pitch) | 1 in 10 | yes |
  | IN_Ex9 | hall plane 24 m at 1 in 4; lean-to beam 12.4 m | 1 in 50 (its ponding input) | yes: covered |
  | IN_Ex10 | roof beams 15 m | 1 in 60 (its ponding input) | yes: covered |
  | the multi-storey golds | none (6–9 m bays) | mostly not declared | no |

  IN_Ex9's lean-to and IN_Ex10's roof are long and flatter than 1 in 20, so the guard is quiet only because their
  4.4 screens are declared.
- **Digests.** Only `consistency.py` changed, which no package, digest or status reads. The five golds whose lists
  moved at ba06d5c were re-run there, and their digests are identical to the e45a65d runs (`gold/runs/eng11`,
  `gold/results/compare_c5.json`).
