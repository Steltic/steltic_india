# steltic-india — 2026-11 engine checks 3 (the review's notes N1–N3 on the consistency guards)

Branch `fix/2026-11-engine-checks-3`, from main e45a65d (PR #33, `CHANGES_2026-11-engine-checks-2.md`). It covers
the low notes N1–N3 of the "Branch 2 review" in `briefs/ENG_REVIEW.md`. Only `consistency.py` changes. No package,
digest or status reads these guards; they print in the report's consistency chapter and in `consistency.check`.

## N1. The ponding guard judges the roof's real span

- **Problem.** The guard asked whether any roof group's longest *element* is 12 m or more.
  - A PEB portal's rafters are short tapered pieces: IN_Ex1's longest is 9.04 m, on a 30 m span.
  - A flat roof's beams are split at the secondary beams.
  - So the guard could not fire on a PEB.
- **Fix** (`consistency._roof_span_m`). The roof span is now the longest roof plane's eave-to-eave span (the frame
  span, `cfg['roof_planes']`). Without roof planes, on an N-mm job, it is the longest grid bay, which is the span of
  the roof beams between the column lines. The element test stays as a lower bound. The message now names the span
  and its basis.

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
| N1 | IN_Ex1 (published PEB, 30 m portal, no ponding screen) | Quiet at e45a65d. Fires now on "roof plane 0 span eave to eave 30.0 m". The 4.4 screen clears it. |
| N1 | IN_Ex16 (flat roof, 7.5 m bays) | Quiet. With one 15 m bay it fires, though its roof beams are recorded in 7.5 m pieces. |
| N2 | IN_Ex16 (`composite_scope` bare_steel, worksheet evaluated) | Quiet. With the worksheet failed or missing it fires. Honest stubs still clear it. |
| N3 | IN_Ex12 unit B (its 7.11.3 separations), read as a two-wing plan | Quiet. Without the separation it fires. An unrelated "gusset_edge_separation" check does not clear it; "seismic_joint_width" and "IS 1893 7.11.3 gap" do. |

The engine checks 2 C1 test asserted that a scope alone clears the composite guard. It now asserts N2: a scope with
the worksheet clears it, a scope alone does not.

Mutation checks (`wt/ENG/tools/mutate6.py`, `logs/mutation8.txt`): **7 of 7 caught**.
- N1: the element length again; the roof planes not read; the grid bay not read.
- N2: the scope clears without a worksheet.
- N3: "separation" clears it; a 7.11.3 tag does not; the separation record not read.

Full HR suite under heavy at ba06d5c: **1,353 passed, 5 skipped** in 6 min 29 s (`wt/ENG/logs/suite_c5.txt`). That
is main's 1,349 plus the 4 new tests.

## Golds

- **`consistency.check`** (old e45a65d and new `consistency.py`, on all 30 gold packages of the e45a65d runs;
  `gold/results/consistency_c5.json`). 25 lists are unchanged. 5 gain one finding each, N1's ponding guard, because
  these roofs are long spans with no IS 875 (Part 4) 4.4 screen:

  | Gold | Roof span | Note |
  |---|---|---|
  | IN_Ex21 (MSME truss shed) | roof plane 18.0 m | no `cfg['ponding']` |
  | IN_Ex1, published and PEB set | roof plane 30.0 m | no `cfg['ponding']` |
  | IN_Ex5, published and PEB set | roof plane 30.0 m | the IN_Ex1 shed with PV; no `cfg['ponding']` |

  The other roof-plane golds (IN_Ex2, IN_Ex3, IN_Ex4, both sets, and IN_Ex9) and IN_Ex7, IN_Ex8 and IN_Ex10
  have the screen and stay quiet. The owners of IN_Ex1, IN_Ex5 and IN_Ex21
  clear it by declaring `cfg['ponding']`. No other list changes: N2 and N3 move no gold.
- **Digests.** The five golds whose lists change were re-run at ba06d5c (`gold/runs/eng11`, the same job
  snapshot). Their digests are identical to the e45a65d runs (eng10, `gold/results/compare_c5.json`).
  The other 25 cannot move: only `consistency.py` changed, and their issue lists are the same.
