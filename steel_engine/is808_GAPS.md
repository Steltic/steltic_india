# IS 808 shapes database - gaps and corrections

**Built:** from IS 808:2021 Tables 1-13 via `pdftotext -layout` -> `tools/build_is808_shapes.py` (WP2.2).
**Output:** `steel_engine/is808_shapes.csv` (554 validated rows); `steel_engine/is808_quarantine.csv` (1 rows, found:false).
**Parse errors / skipped lines:** 0
**Validator after build:** 0 failing rows (|r - sqrt(I/A)| <= 3 %, |M - 0.00785A| <= 3 %, |Ze - 2I/D| <= 4 %, Zp/Ze in [0.99, 1.6], angle Iuu+Ivv = Izz+Iyy within 3 %, I-section A vs plate area 0.88-1.15).

## Units
N-mm. The SI columns (`*_mm`, `*_mm2`, `*_mm3`, `*_mm4`, `*_mm6`, `A_si_mm2`, `Izz_si_mm4`, `Iyy_si_mm4`) are
authoritative. Inch columns (`A`, `Ix`, `rx`, ...) are derived from them for the kip-in twin only.
Angles carry `Iuu_mm4, Ivv_mm4, ru_mm, rv_mm` (principal axes) and `r_min_mm = rv`; `Iw_mm6 = 0` for angles.

## Counts by type (validated)
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

## Quarantined rows (1) - not selectable; `sections.props()` raises (found:false)
- `WPB280X280X284.13` (pdf p.17): A 36195 inconsistent with plate area 2BT+(D-2T)t 12642

## Corrected rows (90) - PDF misprints corrected from the PDF's own corroborating columns
- `ISA35X35X3` (pdf p.29): ISA 35x35x3 rz printed '.0.7' (Table 9, pdf p.29); ry printed 10.7 and sqrt(Izz/A)=10.75 -> 10.7
- `ISA100X100X6` (pdf p.31): rv_mm printed 200 disagrees with sqrt(I/A)=20.00 (A, I corroborated by mass/Ze) -> 20
- `ISA100X100X8` (pdf p.31): rv_mm printed 198 disagrees with sqrt(I/A)=19.84 (A, I corroborated by mass/Ze) -> 19.8
- `ISA100X100X10` (pdf p.31): rv_mm printed 197 disagrees with sqrt(I/A)=19.72 (A, I corroborated by mass/Ze) -> 19.7
- `ISA100X100X12` (pdf p.31): rv_mm printed 196 disagrees with sqrt(I/A)=19.60 (A, I corroborated by mass/Ze) -> 19.6
- `ISA110X110X8` (pdf p.31): rv_mm printed 217 disagrees with sqrt(I/A)=21.79 (A, I corroborated by mass/Ze) -> 21.8
- `ISA110X110X10` (pdf p.31): rv_mm printed 216 disagrees with sqrt(I/A)=21.62 (A, I corroborated by mass/Ze) -> 21.6
- `ISA110X110X12` (pdf p.31): rv_mm printed 215 disagrees with sqrt(I/A)=21.54 (A, I corroborated by mass/Ze) -> 21.5
- `ISA110X110X16` (pdf p.31): rv_mm printed 214 disagrees with sqrt(I/A)=21.35 (A, I corroborated by mass/Ze) -> 21.3
- `ISA130X130X8` (pdf p.32): rv_mm printed 258 disagrees with sqrt(I/A)=25.85 (A, I corroborated by mass/Ze) -> 25.9
- `ISA130X130X10` (pdf p.32): rv_mm printed 257 disagrees with sqrt(I/A)=25.64 (A, I corroborated by mass/Ze) -> 25.6
- `ISA130X130X12` (pdf p.32): rv_mm printed 256 disagrees with sqrt(I/A)=25.58 (A, I corroborated by mass/Ze) -> 25.6
- `ISA130X130X16` (pdf p.32): rv_mm printed 254 disagrees with sqrt(I/A)=25.39 (A, I corroborated by mass/Ze) -> 25.4
- `ISA150X150X10` (pdf p.32): rv_mm printed 298 disagrees with sqrt(I/A)=29.78 (A, I corroborated by mass/Ze) -> 29.8
- `ISA150X150X12` (pdf p.32): rv_mm printed 296 disagrees with sqrt(I/A)=29.65 (A, I corroborated by mass/Ze) -> 29.6
- `ISA150X150X16` (pdf p.32): rv_mm printed 294 disagrees with sqrt(I/A)=29.39 (A, I corroborated by mass/Ze) -> 29.4
- `ISA150X150X20` (pdf p.32): rv_mm printed 292 disagrees with sqrt(I/A)=29.22 (A, I corroborated by mass/Ze) -> 29.2
- `ISA200X100X12` (pdf p.37): rz_mm printed 646 disagrees with sqrt(I/A)=64.42 (A, I corroborated by mass/Ze) -> 64.4
- `ISA200X200X12` (pdf p.32): rv_mm printed 399 disagrees with sqrt(I/A)=39.88 (A, I corroborated by mass/Ze) -> 39.9
- `ISA200X200X16` (pdf p.32): rv_mm printed 396 disagrees with sqrt(I/A)=39.56 (A, I corroborated by mass/Ze) -> 39.6
- `ISA200X200X20` (pdf p.32): rv_mm printed 393 disagrees with sqrt(I/A)=39.33 (A, I corroborated by mass/Ze) -> 39.3
- `ISA200X200X25` (pdf p.32): rv_mm printed 391 disagrees with sqrt(I/A)=38.98 (A, I corroborated by mass/Ze) -> 39
- `LB400` (pdf p.10): rz_mm printed 16.3 disagrees with sqrt(I/A)=163.27 (A, I corroborated by mass/Ze) -> 163.3 | ry_mm printed 3.14 disagrees with sqrt(I/A)=31.45 (A, I corroborated by mass/Ze) -> 31.4
- `LB450` (pdf p.10): rz_mm printed 18.2 disagrees with sqrt(I/A)=181.91 (A, I corroborated by mass/Ze) -> 181.9 | ry_mm printed 3.2 disagrees with sqrt(I/A)=32.04 (A, I corroborated by mass/Ze) -> 32
- `LB500` (pdf p.10): rz_mm printed 20.1 disagrees with sqrt(I/A)=200.89 (A, I corroborated by mass/Ze) -> 200.9 | ry_mm printed 3.33 disagrees with sqrt(I/A)=33.33 (A, I corroborated by mass/Ze) -> 33.3
- `LB550` (pdf p.10): rz_mm printed 21.9 disagrees with sqrt(I/A)=220.72 (A, I corroborated by mass/Ze) -> 220.7 | ry_mm printed 3.48 disagrees with sqrt(I/A)=34.93 (A, I corroborated by mass/Ze) -> 34.9
- `LB600` (pdf p.10): LB 600 Iw printed '2 04 0000' (IS 808:2021 Table 2, pdf p.10) -> 2 040 000 x10^6 mm6 | rz_mm printed 23.9 disagrees with sqrt(I/A)=240.54 (A, I corroborated by mass/Ze) -> 240.5 | ry_mm printed 3.79 disagrees with sqrt(I/A)=38.01 (A, I corroborated by mass/Ze) -> 38
- `LC400` (pdf p.26): Izz cell wraps '13 / 900' in IS 808:2021 Table 8 (pdf p.26, printed p.24)
- `MC75` (pdf p.23): rz_mm printed 39.4 disagrees with sqrt(I/A)=29.35 (A, I corroborated by mass/Ze) -> 29.3
- `MC175X22.7` (pdf p.23): printed mass 22.7 kg/m disagrees with 0.00785A=21.43; A corroborated by Izz/rz, Iyy/ry and Ze -> Mass_kg_m=21.43 (designation label keeps the printed mass)
- `MC250X34.2` (pdf p.24): ry_mm printed 2.36 disagrees with sqrt(I/A)=23.61 (A, I corroborated by mass/Ze) -> 23.6
- `MC250X38.1` (pdf p.24): ry_mm printed 2.32 disagrees with sqrt(I/A)=23.16 (A, I corroborated by mass/Ze) -> 23.2
- `MC300` (pdf p.24): ry_mm printed 2.59 disagrees with sqrt(I/A)=25.95 (A, I corroborated by mass/Ze) -> 25.9
- `MC300X41.5` (pdf p.24): ry_mm printed 2.55 disagrees with sqrt(I/A)=25.55 (A, I corroborated by mass/Ze) -> 25.5
- `MC300X46.2` (pdf p.24): ry_mm printed 2.49 disagrees with sqrt(I/A)=24.93 (A, I corroborated by mass/Ze) -> 24.9
- `MC350` (pdf p.24): ry_mm printed 2.81 disagrees with sqrt(I/A)=28.11 (A, I corroborated by mass/Ze) -> 28.1
- `MC400` (pdf p.24): ry_mm printed 2.81 disagrees with sqrt(I/A)=28.13 (A, I corroborated by mass/Ze) -> 28.1
- `NPB240X120X34.32` (pdf p.12): ry_mm printed 2.74 disagrees with sqrt(I/A)=27.40 (A, I corroborated by mass/Ze) -> 27.4
- `NPB750X270X145.29` (pdf p.14): printed '5.2.8' (double decimal point) read as 52.8
- `PBP200X43.85` (pdf p.40): ry_mm printed 4.89 disagrees with sqrt(I/A)=48.82 (A, I corroborated by mass/Ze) -> 48.8
- `PBP200X53.49` (pdf p.40): ry_mm printed 4.96 disagrees with sqrt(I/A)=49.52 (A, I corroborated by mass/Ze) -> 49.5
- `PBP220X57.28` (pdf p.40): ry_mm printed 5.36 disagrees with sqrt(I/A)=53.54 (A, I corroborated by mass/Ze) -> 53.5
- `PBP260X75.01` (pdf p.40): ry_mm printed 6.25 disagrees with sqrt(I/A)=62.50 (A, I corroborated by mass/Ze) -> 62.5
- `PBP260X87.3` (pdf p.40): ry_mm printed 6.33 disagrees with sqrt(I/A)=63.32 (A, I corroborated by mass/Ze) -> 63.3
- `PBP300X76.92` (pdf p.40): ry_mm printed 7.26 disagrees with sqrt(I/A)=72.60 (A, I corroborated by mass/Ze) -> 72.6
- `PBP300X88.46` (pdf p.40): ry_mm printed 7.32 disagrees with sqrt(I/A)=73.44 (A, I corroborated by mass/Ze) -> 73.4
- `PBP320X88.48` (pdf p.41): ry_mm printed 7.07 disagrees with sqrt(I/A)=70.90 (A, I corroborated by mass/Ze) -> 70.9
- `PBP300X95` (pdf p.40): ry_mm printed 7.36 disagrees with sqrt(I/A)=73.52 (A, I corroborated by mass/Ze) -> 73.5
- `PBP320X102.84` (pdf p.41): ry_mm printed 7.15 disagrees with sqrt(I/A)=71.52 (A, I corroborated by mass/Ze) -> 71.5
- `PBP300X109.54` (pdf p.40): ry_mm printed 7.42 disagrees with sqrt(I/A)=74.33 (A, I corroborated by mass/Ze) -> 74.3
- `PBP320X117.33` (pdf p.41): ry_mm printed 7.23 disagrees with sqrt(I/A)=72.40 (A, I corroborated by mass/Ze) -> 72.4
- `PBP300X124.2` (pdf p.41): ry_mm printed 7.48 disagrees with sqrt(I/A)=74.84 (A, I corroborated by mass/Ze) -> 74.8
- `PBP320X146.69` (pdf p.41): ry_mm printed 7.37 disagrees with sqrt(I/A)=73.69 (A, I corroborated by mass/Ze) -> 73.7
- `PBP300X150.01` (pdf p.41): ry_mm printed 7.57 disagrees with sqrt(I/A)=75.54 (A, I corroborated by mass/Ze) -> 75.5
- `PBP300X180.12` (pdf p.41): ry_mm printed 7.69 disagrees with sqrt(I/A)=76.78 (A, I corroborated by mass/Ze) -> 76.8
- `PBP300X184.12` (pdf p.41): ry_mm printed 7.72 disagrees with sqrt(I/A)=77.07 (A, I corroborated by mass/Ze) -> 77.1
- `PBP320X184.1` (pdf p.41): ry_mm printed 7.54 disagrees with sqrt(I/A)=75.39 (A, I corroborated by mass/Ze) -> 75.4
- `PBP300X222.58` (pdf p.41): ry_mm printed 7.87 disagrees with sqrt(I/A)=78.64 (A, I corroborated by mass/Ze) -> 78.6
- `PBP400X122.4` (pdf p.41): ry_mm printed 9.4 disagrees with sqrt(I/A)=94.36 (A, I corroborated by mass/Ze) -> 94.4
- `PBP400X140.2` (pdf p.41): ry_mm printed 9.5 disagrees with sqrt(I/A)=94.81 (A, I corroborated by mass/Ze) -> 94.8
- `PBP360X152.2` (pdf p.41): ry_mm printed 9 disagrees with sqrt(I/A)=90.48 (A, I corroborated by mass/Ze) -> 90.5
- `PBP400X158.1` (pdf p.41): ry_mm printed 9.6 disagrees with sqrt(I/A)=95.42 (A, I corroborated by mass/Ze) -> 95.4
- `PBP400X176.1` (pdf p.41): ry_mm printed 9.6 disagrees with sqrt(I/A)=96.13 (A, I corroborated by mass/Ze) -> 96.1
- `PBP360X174.2` (pdf p.41): ry_mm printed 9.1 disagrees with sqrt(I/A)=91.49 (A, I corroborated by mass/Ze) -> 91.5
- `PBP360X178.4` (pdf p.41): ry_mm printed 9.1 disagrees with sqrt(I/A)=91.25 (A, I corroborated by mass/Ze) -> 91.2
- `PBP400X194.3` (pdf p.41): ry_mm printed 9.7 disagrees with sqrt(I/A)=96.71 (A, I corroborated by mass/Ze) -> 96.7
- `PBP400X212.5` (pdf p.41): ry_mm printed 9.7 disagrees with sqrt(I/A)=97.37 (A, I corroborated by mass/Ze) -> 97.4
- `PBP400X230.9` (pdf p.41): ry_mm printed 9.8 disagrees with sqrt(I/A)=97.94 (A, I corroborated by mass/Ze) -> 97.9
- `WB150` (pdf p.8): rz_mm printed 6.22 disagrees with sqrt(I/A)=62.32 (A, I corroborated by mass/Ze) -> 62.3 | ry_mm printed 2.09 disagrees with sqrt(I/A)=20.94 (A, I corroborated by mass/Ze) -> 20.9
- `WB175` (pdf p.8): rz_mm printed 7.32 disagrees with sqrt(I/A)=73.31 (A, I corroborated by mass/Ze) -> 73.3 | ry_mm printed 2.59 disagrees with sqrt(I/A)=25.87 (A, I corroborated by mass/Ze) -> 25.9
- `WB200` (pdf p.8): rz_mm printed 8.45 disagrees with sqrt(I/A)=84.49 (A, I corroborated by mass/Ze) -> 84.5 | ry_mm printed 2.99 disagrees with sqrt(I/A)=29.90 (A, I corroborated by mass/Ze) -> 29.9
- `WB200X52.09` (pdf p.8): rz_mm printed 8.48 disagrees with sqrt(I/A)=84.85 (A, I corroborated by mass/Ze) -> 84.8 | ry_mm printed 3.49 disagrees with sqrt(I/A)=34.91 (A, I corroborated by mass/Ze) -> 34.9
- `WB225` (pdf p.8): rz_mm printed 9.52 disagrees with sqrt(I/A)=95.26 (A, I corroborated by mass/Ze) -> 95.3 | ry_mm printed 3.22 disagrees with sqrt(I/A)=32.20 (A, I corroborated by mass/Ze) -> 32.2
- `WB250` (pdf p.8): rz_mm printed 10.6 disagrees with sqrt(I/A)=106.88 (A, I corroborated by mass/Ze) -> 106.9 | ry_mm printed 4.05 disagrees with sqrt(I/A)=40.60 (A, I corroborated by mass/Ze) -> 40.6
- `WB300` (pdf p.8): rz_mm printed 12.6 disagrees with sqrt(I/A)=126.57 (A, I corroborated by mass/Ze) -> 126.6 | ry_mm printed 4.01 disagrees with sqrt(I/A)=40.19 (A, I corroborated by mass/Ze) -> 40.2
- `WB350` (pdf p.8): rz_mm printed 14.6 disagrees with sqrt(I/A)=146.32 (A, I corroborated by mass/Ze) -> 146.3 | ry_mm printed 4.02 disagrees with sqrt(I/A)=40.20 (A, I corroborated by mass/Ze) -> 40.2
- `WB400` (pdf p.8): rz_mm printed 16.6 disagrees with sqrt(I/A)=165.92 (A, I corroborated by mass/Ze) -> 165.9 | ry_mm printed 4.04 disagrees with sqrt(I/A)=40.29 (A, I corroborated by mass/Ze) -> 40.3
- `WB450` (pdf p.8): rz_mm printed 18.6 disagrees with sqrt(I/A)=186.42 (A, I corroborated by mass/Ze) -> 186.4 | ry_mm printed 4.1 disagrees with sqrt(I/A)=41.03 (A, I corroborated by mass/Ze) -> 41
- `WB500` (pdf p.8): rz_mm printed 20.7 disagrees with sqrt(I/A)=207.70 (A, I corroborated by mass/Ze) -> 207.7 | ry_mm printed 4.96 disagrees with sqrt(I/A)=49.63 (A, I corroborated by mass/Ze) -> 49.6
- `WB550` (pdf p.8): rz_mm printed 22.8 disagrees with sqrt(I/A)=228.86 (A, I corroborated by mass/Ze) -> 228.9 | ry_mm printed 5.1 disagrees with sqrt(I/A)=51.14 (A, I corroborated by mass/Ze) -> 51.1
- `WB600` (pdf p.8): rz_mm printed 24.9 disagrees with sqrt(I/A)=249.71 (A, I corroborated by mass/Ze) -> 249.7 | ry_mm printed 5.25 disagrees with sqrt(I/A)=52.58 (A, I corroborated by mass/Ze) -> 52.6
- `WB600X145.06` (pdf p.8): rz_mm printed 25 disagrees with sqrt(I/A)=250.00 (A, I corroborated by mass/Ze) -> 250 | ry_mm printed 5.35 disagrees with sqrt(I/A)=53.62 (A, I corroborated by mass/Ze) -> 53.6
- `WPB200X200X37.34` (pdf p.16): Iw cell blank in IS 808:2021 Table 4 (pdf p.16, printed p.14) -> Iw empty (found:false for LTB)
- `WPB360X300X91.04` (pdf p.18): printed mass 91.04 kg/m disagrees with 0.00785A=83.21; A corroborated by Izz/rz, Iyy/ry and Ze -> Mass_kg_m=83.21 (designation label keeps the printed mass)
- `WPB360X300X125.81` (pdf p.18): printed mass 125.81 kg/m disagrees with 0.00785A=111.47; A corroborated by Izz/rz, Iyy/ry and Ze -> Mass_kg_m=111.47 (designation label keeps the printed mass)
- `WPB360X300X163` (pdf p.18): printed mass 163 kg/m disagrees with 0.00785A=141.3; A corroborated by Izz/rz, Iyy/ry and Ze -> Mass_kg_m=141.3 (designation label keeps the printed mass)
- `WPB340X300X290.64` (pdf p.18): printed mass 290.64 kg/m disagrees with 0.00785A=247.27; A corroborated by Izz/rz, Iyy/ry and Ze -> Mass_kg_m=247.27 (designation label keeps the printed mass)
- `WPB500X300X187.34` (pdf p.19): printed '7.2.7' (double decimal point) read as 72.7
- `WPB600X300X285.48` (pdf p.19): ry_mm printed 722 disagrees with sqrt(I/A)=72.16 (A, I corroborated by mass/Ze) -> 72.2
- `WPB650X300X224.78` (pdf p.19): printed '6.9.8' (double decimal point) read as 69.8

## Parse errors
- none

## Out of scope
- Annex A/B formula-only custom sections: compute from the Annex formulae with a cite; never invent.
- Rectangular/square hollow sections (IS 4923) are not in the corpus: no path (found:false).
- IS 1161 circular hollow sections live in `is1161_tubes.csv` (grade/process resolved from cfg; no default fy).

## Lookup labels
- Beams/cols: `MB200`, `LB150`, `SC250`, `NPB100X55X8.1`; channels `MC200`, `LC300`; angles `ISA100X75X10`;
  piles `PBP200X43.85`; duplicates append the printed mass (`WB200X52.09`).
