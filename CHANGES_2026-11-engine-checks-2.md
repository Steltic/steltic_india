# steltic-india — 2026-11 engine checks 2 (re-check 3 and the group strength line)

Branch `fix/2026-11-engine-checks-2`, from main 56909e3 (PR #32, `CHANGES_2026-11-engine-checks.md`). It covers the
three low items of re-check 3 in `briefs/ENG_REVIEW.md`, and one item that the MSME re-size of IN_Ex21 found. Gold cfgs
are not edited.

## R3-1. The side-wall check takes the pattern's fields exchanged as well

- **Problem.** A hand-built pattern (no `wall_side_kNm2`) has its side-wall Cpe derived from Table 5.
  `side_wall_pressure` checked the pattern's own (windward, leeward) Cpe against Table 5's (A, B), or (C, D), in that
  order only.
  - IN_Ex6 writes its reversed wind by exchanging the two fields (cfg, HR-B-12).
  - So its WMXR± and WMYR± patterns, each with its +R sign variant, drew a false WARN: 8 of its 16.
  - The chosen θ was right, but for the reversed X patterns only because the two angles tie there (both miss by
    0.95).
- **Fix.** Each angle is now compared with the pair taken directly and exchanged, and the smaller miss counts. The same
  miss decides the angle and the warning.
  - The record says `pattern_fields_exchanged`.
  - `_wall_zone` exchanges the members' Table 5 surfaces with the fields: the engine's "windward" face of WMXR+ is
    wall B.
- **Result.** All 16 of IN_Ex6's patterns match: θ 0 with side Cpe −0.6 along X, θ 90 with −0.5 along Y, no warning.
  A pattern that matches neither angle either way still warns. The warning now says it tried both.
- **Correction.** `CHANGES_2026-11-engine-checks.md` (R2-4) said "IN_Ex6's patterns match". That bullet is now
  corrected.

## R3-2. A not-applicable Section 12 row reads "not applicable" in the report

- **Problem.** `report_india._is800_s12_detailing` counted every ok-None row as "not evaluated (missing inputs block
  COMPLETE)". That included R2-1's not-applicable rows: a `no_seismic` job, with no seismic detailing to check.
- **Fix.**
  - The summary counts the not-applicable rows apart, with their reason, for example "2 not applicable (no_seismic
    declared …)".
  - A row whose checks are all not applicable reads "not applicable (reason)".
  - The table gains a "not applicable" column only when such a row exists. No gold declares `no_seismic`, so no gold
    report changes.

## R3-3. A column piece past a lower roof or a wall step with no node is split by height

- **Problem.** `wall_wind_pieces` judged each column piece at its mid-height: whether it is the first element of its
  strip, its width, and the facade step beside it.
  - Case 1, the reviewer's variant of IN_Ex9: the hall column (12, 30) as one piece 0–8 m, with no node at the 5 m
    lean-to roof. At 4 m it stands behind the lean-to wall. So the hall wall above the lean-to in its strip
    (7.5 × 3 = 22.5 m²) was on no member, and the −X face came to 457.5 m² of 480.
  - Case 2, the other way: a lower lean-to (3 m) under a one-piece hall column. The column is exposed at 4 m, so it
    took its strip over all 8 m, including 22.5 m² behind the lean-to wall.
  - Case 3: a one-piece column next to a step that ends below its mid-height never handed its re-entrant share to the
    corner column.
- **Fix.**
  - Each piece is also judged band by band. The band edges are the heights where any piece or one of its strip's
    envelope members ends, or where such a member passes the piece's line.
  - When the bands give a different own area or a different re-entrant share from the mid-height judgement, the
    piece is split by height. Each band carries the wall where the piece is the first element of its strip, with that
    band's width and facade steps.
  - The area of the loaded bands is spread over the piece's length. That is the convention of the R2-2 re-entrant
    share.
  - Otherwise, which is every piece of every gold, the mid-height path is unchanged.
  - The split is recorded per piece and face in `member_wind_wall_scan` (`height_bands` / `side_height_bands`), with
    each band's exposure and width and the area against the mid-height area. The text is in `WALL_SCAN_BASIS`.
- **Limit.** Spreading the loaded bands over the piece moves their resultant to the piece's mid-length. The frame gets
  the full force, but a band at the top of a long piece loads the frame lower than it really is. A model with a node at
  the step (as every gold has) is exact.
- **Result** (scan of IN_Ex9's wall geometry):

  | Variant | −X face before | −X face now | Hand total |
  |---|---|---|---|
  | IN_Ex9 as modelled (nodes at 5 m) | 480 | 480 | 480 |
  | Hall column (12, 30) one piece 0–8 m (the reviewer's) | 457.5 | 480 | 480 |
  | 3 m lean-to, nodes at 3 m | 468.75 | 480 | 480 |
  | 3 m lean-to, hall column (12, 15) one piece | 491.25 | 480 | 480 |

  The along-ridge faces stay at 288 m² in every variant.

## G-1. A member group's strength line is its worst strength element

- **Problem.** A member group's package row was built from one element: the one with the largest D/C.
  - When that element's D/C is its Table 3 slenderness ratio, the group's strength line (9.3 interaction / member
    resistance) was that element's strength ratio, not the group's worst.
  - On IN_Ex21's bottom chord the package showed e44 at 0.19, while the chord elements that carry the wind-uplift
    compression were higher (A/B below).
  - The verdict was right: the group D/C is the larger of the two ratios. But the strength line, the Chapter 6 member
    table and the headline's worst strength could all understate.
  - The Table 3 line already came from the group's worst Table 3 element (review 2026-11, MSME).
- **Fix** (`design_pipeline.group_check_rows`).
  - Each group record carries `strength_worst` (element, ratio, combination, clause, and the PEB station when it is
    not the mid-depth section) and `table3_worst` (element, ratio, KL/r, limit, combination, clause).
  - The strength line is the worst strength element's, named "(element eN, combination …; the largest in the
    group)", when it is not the D/C-governing element's.
  - A tapered PEB element is checked at its mid-depth section and two stations (D-T1). `peb_station_checks` records
    its worst strength station (`strength_worst`), which need not be the station that governs its D/C.
  - The group D/C, its governing check and `governing_element_result` are unchanged.
- **What prints it.** Everything that prints a group's strength ratio reads that line:
  - the package rows and the report's per-group check tables;
  - the Chapter 6 member table (`report_second_wave.member_cells`);
  - the headline (`report_second_wave.headline`: the maximum over all groups' strength lines, so over all elements,
    now naming the element when it is not the governing one, also in the STATUS sentence);
  - the 7.6.4 lateral-member scan (`_strength_dc`).
  - `member_schedule.csv` and `member_demands.md` print demands and the group D/C only.
  - This covers every member type: 9.3 members (PEB and general) and pin-ended truss members (the axial line).
- **Correction.** `CHANGES_2026-11-engine-checks.md` gave the IN_Ex21 chord's worst strength ratio as 0.19 at e44.
  That bullet now gives the true worst element and ratio (A/B below).

## Tests and mutation checks

`tests/test_engine_checks_2026_11_checks2.py`, 11 tests:

| Item | Tests |
|---|---|
| R3-1 | IN_Ex6's 8 pattern forms × 2 signs: no warning, θ / Cpe, the exchanged flag and surfaces. A Y pattern with θ 0's exchanged coefficients: the exchanged match chooses θ 0, not the plan's θ 90. |
| R3-2 | Real no_seismic rows (the R2-1 builders): "not applicable (no_seismic declared …)", 0 not evaluated. A seismic job's not-evaluated row and an unchanged table. |
| R3-3 | The reviewer's one-piece variant (480, the band record). The 3 m lean-to both ways (480, the over-count removed, the re-entrant share below 3 m). IN_Ex9 as modelled unchanged. |
| G-1 | Real `member_check_is800` results on a double-angle chord (e44 governed by Table 3, e190 by the wind compression): the line, both records, the headline, its sentence, the Chapter 6 cell and `_strength_dc`. The governing element as the worst (line kept). A real `peb_station_checks` element whose worst strength station is not its governing one. A synthetic PEB record. |

One existing test changed: `test_span_moment_fix.py::test_e2e_gable_wind_column_is_governed_by_its_span_moment`.
- It asserted that the wind-column group's 9.3 line is the D/C-governing element's.
- In its test shed, the group (the two gable wind columns, e2 and e13) is governed by e2's Table 3 ratio, 0.485.
- e13, its mirror image, has the larger strength ratio: 0.25766 against 0.25764.
- The line is now e13's. The test checks it against `strength_worst`: at least the governing element's ratio, and
  within 1 % of it. Both elements carry the span moment.

Mutation checks (`wt/ENG/tools/mutate4.py`, `logs/mutation6.txt`): 12 of 12 caught.
- R3-1: the warning from the direct pair only; the angle from the direct pair only; the surfaces not exchanged.
- R3-2: N/A counted as not evaluated; the row value instead of "not applicable".
- R3-3: no band split; the banded piece keeps its mid-height area; the cuts from the piece's own strip only.
- R2-2 rules whose code moved: the share by width; the share over the whole height.
- G-1: the line from the D/C element again; the PEB worst strength station not recorded.

The R2-2 step-band mutation ("the share over the whole height") no longer changes any area: the band split corrects
it, because the bands are cut at every piece end. It is caught by the banded record, since IN_Ex9 as modelled is then
banded.

## Gold A/B (eng9 at 0484520, the eng5..eng8 job snapshot)

- **Digests.** All 30 gold digests are identical to each gold's latest earlier digest (eng8 for IN_Ex9, eng6 at 4e051ce
  for 18, eng5 for the other 11; `gold/results/compare_c2.json`):
  - status, open reasons and status reasons;
  - every member D/C, governing check, element and combination;
  - every connection and Section 12 row;
  - the headline, tonnage and wind post Ka.
  - The digest does not hold R3-1's package changes on IN_Ex6 (below).
- **Member wind** (`gold/results/wind_totals3`, the 17 golds with member wind). Every per-wall force, area, envelope
  residual and member count equals the bca766e run.
  - No gold piece is banded (R3-3): every gold has a node where a lower roof meets a column.
  - IN_Ex6's 8 side-wall warnings are gone. Its θ and Cpe are unchanged (θ 0 / −0.6 along X, θ 90 / −0.5 along Y).
    Under its reversed patterns the members' surfaces now read B windward / A leeward (D / C along Y).
- **Group strength lines (G-1).** The digest holds the governing element's ratio, so these changes are not in it:
  - 94 groups in 28 of the 30 golds now print another element's strength line. 48 of them move by more than 0.005,
    and 21 by more than 0.05 (`gold/results/strength_lines_c2.txt`).
  - The largest moves:

    | Gold | Group | Line before | Line now |
    |---|---|---|---|
    | IN_Ex21 | bottom chord 2ISA70 (D/C 0.782, Table 3 e44) | 0.187 (e44) | **0.734** (e190, 0.9DL+1.5W_Y) |
    | IN_Ex11 workshop | roof NPB400 (D/C 0.750) | 0.165 (e53) | 0.691 (e65) |
    | IN_Ex11 | roof NPB400 (D/C 0.750) | 0.192 (e174) | 0.677 (e190) |
    | IN_Ex17 | floor NPB500 (D/C 0.776) | 0.181 (e351) | 0.511 (e817) |
    | IN_Ex21 | vertical ISA70 (D/C 0.899) | 0.139 (e57) | 0.468 (e197) |
    | IN_Ex6 | lateral column WPB300 (D/C 0.868) | 0.455 (e31) | 0.778 (e11) |
    | IN_Ex19 | floor NPB450 (D/C 0.827) | 0.433 (e258) | 0.716 (e1144) |

  - Each new line is at most its group's D/C (the largest is 0.807) and at most its gold's headline strength, which
    is unchanged in all 30. So no headline, status or verdict moves: only the report's labels and figures change.
- **Run time.** The same as eng5 within the run-to-run noise (IN_Ex1 PEB 118 → 124 s, IN_Ex2 PEB 264 → 295 s, eng6
  278 s; IN_Ex9 13 → 14 s).

## Suite

Full HR suite under heavy at e15cbde: **1,345 passed, 5 skipped** in 7 min 05 s (`wt/ENG/logs/suite_c2b.txt`). The
first run, at 0484520, had one failure: the existing test above, before it followed G-1 (`logs/suite_c2.txt`,
1,344 passed). That is main's 1,334 plus the 11 new tests.
