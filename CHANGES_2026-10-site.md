# steltic-india — 2026-10 third wave: the PEB lever study's contract for the Hub (handoff P11)

Branch `fix/2026-10-third-site`, from origin/main 44b74de. It goes with steltic_hub_india's branch of the same name
(the Variations tab reads the contract below). No engine check, no gold and no report changes: the designs are
untouched. Files: `scripts/peb_lever_infer.py` (new), `scripts/peb_lever_study.py`, `steel_engine/peb_autosize.py`
(three lines), `tests/test_peb_lever_third_wave.py` (new).

## A job spec inferred from the job's own cfg.py

- A job with no hand-written spec in `scripts/peb_lever_jobs.py` gets one from `scripts/peb_lever_infer.py`, so a Hub
  project (or an engineer's own PEB job) needs no spec. The job's `cfg.py` is executed and its model built once
  (`cfg['custom_build']`, no analysis) in a child process; the member roles come from the members the build makes.
  - `members`: the top-level `WI` / `TI` literal constants the model uses; `group` from their members (column; rafter
    or canopy → rafter); `sfrs: False` when no member is in a moment frame (a column released at its top, a gable
    rafter, a canopy). A braced-frame column (pinned top, a `lateral_col:` base) is kept at its size, with a note.
  - `links`: equal depths that meet at the knee (knee column top, knee rafter start) and at each main-frame rafter
    splice (`peb['splices']`, both sides).
  - `splice_faces`: each named `rafter_splice` joint with an end plate, matched to a constant by the plate's lever
    arm (d − tf) and web (a web doubler allowed); `base_consts`: the column constants whose `column_base` entry has a
    shear key; `knee_column`: the main-frame column under the knee.
  - `frame_line` NX // 2; `base` from `cfg['base']`, or the knee column's base entry when it is 'mixed';
    `dado_height_mm` from `DADO_H`, else the lowest girt when `cfg['cladding_brittle']`; `seismic` from `cfg['seis']`,
    `R_Y` / `R_X` and the transverse system; `Lr_const`, the secondary script (`PURLIN`, `GIRT`, `FY`), the
    collateral / PV loads and the purlin span (`SX`); `brace` when there is a `BRACE` constant.
  - What cannot be read is a reason the spec is refused (`InferError`), never a guess; every derived value is in the
    spec's notes.
- **Check on the golds:** the specs inferred from the four PEB golds' `cfg.py` equal the hand-written ones field for
  field (the `solar` entry of IN_Ex1 is hand-written only). The test runs when `STELTIC_PEB_GOLDS` names the gold job
  folders.
- A hand-written spec still wins. The spec a study used is written to `<work>/<job>/job_spec.json`, and its source is
  recorded in `study.json` (`spec_source`, `spec_notes`).

## The runner's contract

- `--list-variants [--json]` prints the contract and runs nothing:
  - the switches (`ladders`, `stop_after_min`, `cfs_python`, `progress_json`, `spec_from_cfg`, ...);
  - the progress-line prefix and events, the variant order and labels;
  - the hand-written specs;
  - per `--job`: the spec's source and notes, zone / I / route / dado / base, whether solar-ready applies, the resized
    constants, and the variants of both ladders with their status, code status (`compliant` / `reading` /
    `not compliant` / `n/a`, as the outputs tag them), alias, start and whether they are sized.
  The Hub reads this instead of parsing `--help` and importing the script.
- `--progress-json` adds one line per event, `@@peb-study {json}`: plan, variant, resumed, row (with kg/m²), budget,
  job_done and done. The human lines are unchanged.
- `--cfs-python <interpreter>` designs the purlins and girts with the CFS engine in its own interpreter (the
  candidate list and the secondary worker, `peb_autosize.CFS_PY`). Before any sizing the runner checks that this
  interpreter can import the CFS engine. Without the switch, nothing changes.
- The solar-ready variant applies to IN_Ex1 as before (its spec carries the IN_Ex5 wind basis).

## Tests

- `tests/test_peb_lever_third_wave.py`: 10 tests, and 1 optional (the golds). They cover:
  - inference on the mini test portal and on a synthetic registry (roles, moment frame, ties, faces with a web
    doubler, bases, dado, route), and the reasons when it refuses;
  - the hand-written spec winning;
  - the `--list-variants --json` contract, run as a command;
  - the code-status reading;
  - `--cfs-python`, with a recording interpreter and the pre-check;
  - the progress events and `job_spec.json`.
- Full suite: **1,131 passed, 5 skipped** (baseline 1,121 / 4; the new skip is the optional gold comparison).
