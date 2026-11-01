# steltic-india — 2026-10 column span moment (in-span bending of columns under a span load)

Branch `fix/2026-10-column-span-moment` on main 44b74de. 00336f6 and e7cc48b are the first cut; the third commit
fixes the ten findings of the independent review (`briefs/SPAN_REVIEW.md`, read-only review of the first cut). The
review found the mechanics right and the use of the span moment wrong in places. This file describes the branch
as it now stands.

## Why

Before this branch a column's member check used its end moments only. A gable wind column, pinned at the base and
at the end rafter, carries the wall wind as a span load. Its end moments are zero, so the w L²/8 at mid-height was
never checked, and the PEB auto-sizer took the IN_Ex1–Ex4 wind columns down to 200 × 120 plates.

## What the engine does now

- **Records** (`static_model.REC_FIELDS`, now 17 fields). Every column record also carries:
  - `Mmaj_span` / `Mmin_span`: the signed extreme of the bending moment inside the element (0.0 when the extreme is
    at an end);
  - `Mmaj_free` / `Mmin_free`: the free (simply supported) moment of the span load at mid-length. With the two end
    moments this fixes the whole diagram: M(t) = M_i (1 − t) + M_j t + 4 M_free t (1 − t).

  Both come from the static part of each combination (gravity + member wind). RSA responses carry no span load.
  Records of the first cut (15 fields, no free moment) get their free moment back from an in-span extreme
  (`free_from_span_extreme`). A 13-field record reads as having no span load.
- **Member check** (`india_is800.member_check_is800`). A column with a span load hands its free moment to the check
  (`Mz_free_Nmm` / `My_free_Nmm`), which rebuilds the diagram (`span_moment_diagram`). Then:
  - the in-span extreme enters the check whatever its sign;
  - each sign is checked with its own LLT (`LLT_sag_mm` / `LLT_hog_mm`), so the flange the span moment puts in
    compression is checked even where the span moment is smaller than the end moments;
  - Cmy and Cmz come from the IS 800 Table 18 uniform-loading rows (`cm_factor_span_load`), including where the
    end moments govern;
  - C1 = 1.0, because C1 from the end moments does not apply under a span load (a declared `c1` still wins).

  Beams and every other caller are unchanged (`Mz_mid_Nmm`, `My_mid_Nmm` still read as before).
- **Envelope** (`envelope_from_records`). `Mz` / `My` stay end-moment envelopes. The column span extremes are
  enveloped apart (`Mz_span` / `My_span`) and enter only:
  - the member schedule;
  - the member inputs (`Mz_Nmm` / `My_Nmm`, plus `Mz_span_Nmm` / `My_span_Nmm` when non-zero);
  - the legacy member demands.

  The column splice / base and beam-to-column connection demands keep the end moments. The demand cache key now
  includes the envelope layout (`ENVELOPE_LAYOUT`).

## The review findings and what was done

1. **Cm and CmLT of a column whose span moment governs** (gable wind column checked with Cm = CmLT = 0.9 in every
   PEB job). IS 800:2007 text, from the corpus (`IS_800_2007.md`, 9.3.2.2):
   - "Cmy, Cmz = equivalent uniform moment factor as per Table 18";
   - "My, Mz = maximum factored applied bending moments about y and z-axis of the member";
   - "CmLT = equivalent uniform moment factor for lateral torsional buckling as per Table 18 corresponding to the
     actual moment gradient between lateral supports against torsional deformation in the critical region under
     consideration".

   The Table 18 uniform-loading rows are taken from the corpus OCR of pdf p. 78 (`markdown/pages/page_078.md`). The
   reading is set out in full in the comment above `india_is800.TABLE18_CITE`. The rows are:

   | Case | Range | Uniform loading |
   |---|---|---|
   | Mh ≥ Ms | 0 ≤ αs ≤ 1 | 0.2 + 0.8 αs ≥ 0.4 |
   | Mh ≥ Ms | −1 ≤ αs < 0, 0 ≤ ψ ≤ 1 | 0.1 − 0.8 αs ≥ 0.4 |
   | Mh ≥ Ms | −1 ≤ αs < 0, −1 ≤ ψ < 0 | 0.1 (1 − ψ) − 0.8 αs ≥ 0.4 |
   | Ms > Mh | αh ≥ 0, or ψ ≥ 0 | 0.95 + 0.05 αh |
   | Ms > Mh | αh < 0 and ψ < 0 | 0.95 + 0.05 αh (1 + 2ψ) |

   - The table's note ("For members with sway buckling mode ... Cmy = Cmz = 0.9") is applied as follows:
     - **Gravity columns** (no moment beam and no brace on their line: the gable wind columns and the leaning
       columns) have no sway buckling mode of their own. Under a span load they take the plain row whatever
       `cfg['sway_frame']` says (`sway_span_load = False`, `_member_input_record`).
     - Scope: the span-load path only. A gravity column's end-moment-only checks (Table 4 combinations,
       IS 1893 7.11.2 deformation compatibility) keep the job's `sway` flag and so Cm = 0.9. Applying the same rule
       there would lower the 7.11.2 ratios of the moment-frame golds (double curvature: Cm 0.9 → 0.4, and CmLT with
       it). That is a design-rule change for the lead and owner to rule on, not part of this fix.
     - **Sway members with a span load** take the larger of 0.9 and the row value.
   - **CmLT** never takes the sway value, because the note covers Cmy and Cmz only.
     - Under a span load, CmLT is the row value of the major-axis diagram where the compression flange is
       unrestrained over the member (LLT ≥ L).
     - Where lateral supports sit inside the member, CmLT is 1.0, the Table 18 upper bound. The gradient between
       the girts is not resolved (conservative).
     - Without a span load, CmLT = Cmz as before.
   - **Assumption (marked in the code):** the OCR lost the bending-moment sketches, so Ms is read two ways, as the
     moment at mid-length and as the in-span extreme, and the larger Cm is used. With no span load the Mh ≥ Ms
     rows give back 0.6 + 0.4ψ exactly, which supports the reading.
   - Pinned-pinned gives 0.95; fixed-fixed 0.5; propped (fixed base, pinned top) 0.55.
   - Tested with `sway: True` (unit test and the mini shed, which has `sway_frame` True).
2. **Smaller span moment of opposite sign** (fixed-fixed wL²/24, propped 9wL²/128). It is now always passed and
   checked on its own sign with its own LLT. Review case 3: the hogging check over 8 m is made and governs.
3. **End moments governing under a span load.** These now get the Mh ≥ Ms rows, not 0.6 + 0.4ψ. Review case: knee
   −120 kN·m with mid-height −78 kN·m gives Cm = 0.72, not 0.60. In a sway member the note's 0.9 stands.
4. **Connection demands.** The column envelope `Mz` / `My` no longer carries the span moment. In the mini shed the
   pinned gable column's splice / base demand moment is 0.0, where the first cut had 17.64 kN·m. The checked splice
   and base values were not affected (they read `Mmaj` and `Mmaj_i`).
5. **PEB station checks.** `My_mid_Nmm` and the free moments are now cleared with `Mz_mid_Nmm`. A station is
   checked with its end forces only.
6. **`_top_records`.** It keeps every combination in which a column carries a span load (the member-wind
   combinations of that column) in place of the three largest |span|. The ranking dropped the governing pair when
   the span moment ties across gravity factors. Test: a 40-case set where the governing case ranks fifth by
   |span|. On the mini shed, the reported 9.3 interaction of every column equals the check over all its
   combinations. Cost on the mini shed: 14 columns checked in 0.02 s.
7. **Tests** (`tests/test_span_moment_fix.py`, 55 cases). One element is compared with 200 elements on both axes and
   both vecxz for:
   - pinned-pinned;
   - fixed-fixed;
   - propped;
   - cantilever (vertex at the tip, returns 0.0);
   - top released by `-releasez` / `-releasey`.

   The parabola from the end moments and the free moment matches the fine model at every station.

   Further unit tests:
   - P-Delta with 300 kN axial load and the top on a lateral spring (the chord shears are consistent);
   - the explicit element length;
   - both model builders;
   - the record layout, including the 13- and 15-field compatibility;
   - the envelope split;
   - every Table 18 row, its linear-row limit and the sway note;
   - the member check (sign-aware, sway, CmLT, KLT, C1, minor axis);
   - the gravity-column span-load sway flag;
   - `_top_records`, the station checks and the C1 lever.

   End-to-end on the mini PEB shed:
   - the gable wind column's governing 9.3 record carries q × tributary × L²/8 with Cm 0.95 and a Table 18 basis;
   - its interaction D/C (0.254) is over twice the D/C of the same records without the span fields (0.077). This
     assertion fails without the span moment;
   - the top records never drop the governing combination;
   - the connection demand is 0;
   - the station D/Cs are unchanged by the span fields.

   Mutation checks were run on the fix (span not passed, old `_top_records`, station keys not cleared). Each one
   fails these tests.
8. **Element length.** `column_span_moments` takes `L` from the column dict, set by `build_static` and
   `_staticize_custom`. It refuses a column without one and never reads the live OpenSees model.
9. **Opt-in C1 gradient lever** (`peb_rules ltb_c1: 'gradient'`, not the default). `_c1_segment` now returns
   C1 = 1.0 when an element in the restrained length carries a span load. **Limitation:** the lever still
   interpolates element end moments linearly and does not evaluate the parabola, so under wall wind it gives no
   benefit. The default `unity` lever is unaffected.
10. **Scope: parametric models carry no column span load.** `member_wind_loads` applies the wall wind as a
    distributed load only when every column has `transf` 1 or 2 (custom and roof-plane builds). `build_static`
    column dicts carry no `transf`, so the parametric (non-custom) models take the nodal fallback. The wall wind
    reaches them as level forces at the grid nodes (tributary storey height), so their columns get no span load and
    no span moment from this branch. This is unchanged, documented here and in `build_static`, and tested
    (`test_model_builders_set_the_column_length`). The golds are custom (`frame_build` / PEB) or roof-plane builds,
    so they take the distributed path wherever all their columns sit on transf 1 or 2. In the IN_Ex1 gold run of
    2026-11-01, 64 of the 154 column elements carry a span moment. The span moments of the other golds have not been
    checked here; the lead's re-runs will show them.

## Effect on the designs (for the gold re-runs)

- **Mini PEB shed** (`tests/_peb_fixture.py`, `sway_frame` True), first cut → now:

  | Member | Interaction D/C | Cm | Splice / base demand moment |
  |---|---|---|---|
  | Gable wind column | 0.2543 → 0.2544 (eq. 1 governs; Cm enters eq. 2) | Cmz 0.90 → 0.95 | 17.64 → 0 kN·m |
  | Corner gable posts | unchanged | Cmy 0.90 → 0.95 | 7.29 → 0 kN·m |
  | Tapered portal columns | unchanged | — | — |

- **Expected on the golds** (not re-run here; only the lead writes the golds):
  - Gable wind and gravity columns of PEB jobs get Cm 0.95 under the wall wind, where it was 0.9.
  - Gravity columns without a span load are unchanged (sway flag kept, see finding 1).
  - Portal and wall columns under the wall wind:
    - Cm becomes max(0.9, row) in sway jobs, where it was 0.9;
    - CmLT becomes 1.0 where girts or fly braces sit inside the element, where it was 0.9;
    - the opposite-sign flange check can now govern where the span moment opposes the knee moment.
  - Connection demand moments of pinned-base columns under wall wind drop to their end moments.
- **Re-run any job folder made with 00336f6 / e7cc48b** (the IN_Ex1 gold run of 2026-11-01 has the 15-field
  layout). Its free moments are recovered only where the extreme lies inside the span.
- **For the PEB sizer** (`peb_autosize` calls `member_checks_is800` / `peb_station_checks`): more combinations per
  column check, all span-load combinations of that column. Cheap, as measured above.

## Not changed (open points for the lead)

- **Members without a span load** keep `cm_factor` as before. In a sway-frame job this means Cmy = Cmz = 0.9 and
  CmLT = Cmz = 0.9, although the Table 18 note covers Cmy and Cmz only. Changing CmLT there moves every sway-frame
  gold, in both directions.
- **Gravity columns of sway-frame jobs, without a span load,** keep the sway note (see finding 1).
- **Beams** keep their span path (`Mz_mid_Nmm` = the sagging maximum, Cm = 1.0, or 0.9 in a sway frame). Rafters
  with axial force are beams here.

## Files

- `steel_engine/static_model.py`: `REC_FIELDS` (+ `Mmaj_free`, `Mmin_free`), `_free_moment`,
  `column_span_moments` (explicit L), `free_from_span_extreme`, `combo_forces_for_member_check` (free moments,
  15-field compatibility), `envelope_from_records` (`Mz_span` / `My_span`), `ENVELOPE_LAYOUT` in the cache key,
  column `L` in `build_static` and `_staticize_custom`.
- `steel_engine/india_is800.py`: Table 18 text and reading, `span_moment_diagram`, `cm_factor_span_load`,
  `member_check_is800` (span-load path, CmLT, `Cm*_basis` and `M*_span_Nmm` in the per-combination record).
- `steel_engine/design_pipeline.py`: gravity-column `sway_span_load`, `_member_moment`, `_top_records`,
  `peb_station_checks`, member schedule / inputs vs connection demands (HR and legacy packages).
- `steel_engine/peb_levers.py`: `_c1_segment` under a span load.
- `tests/test_span_moment_fix.py` (new), `tests/test_third_wave_peb.py` (updated to the 17-field layout and the
  free-moment API).
