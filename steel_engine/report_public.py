"""report_public.py -- the public-text pass of the printed reports (independent check of 2026-10-23, finding 5).

The reports are public documents. This pass keeps build-machine paths, code module and file names, repository /
branch / commit references, JSON keys and internal words out of the printed text, and prints every Steltic design
ruling with its plain meaning. It changes printed text only: no record of the calc package is read or written here.

* public_text(text)   -- the pass for any printed text (report_india applies it to the whole body before Appendix C,
                         through report_second_wave.tidy_html)
* strict_text(text)   -- public_text, and then every remaining snake_case token is spelt out; for text that comes from
                         files written by scripts (cost of compliance, strengthening option, the PV note and answer)
* public_html(html)   -- public_text on the text of an HTML fragment (tags and attributes untouched)
* leaks(text)         -- what the pass refuses to print (paths, file and module names, repository references, JSON
                         keys, internal words); the tests assert it is empty on every printed section
* gate_label(key), wind_label(key), table6_text(key), check_label(cid), ruling_meaning(rid)

Wording sources: IS 800:2007 Table 6 rows and the IS 875 (Part 3):2015 factor names are quoted from the corpus
transcriptions (IS_800_2007 Table 6 recovered; IS_875_Part_3_2015 6.3 and 7.2); the design rulings are the ones
printed in peb_report.OWNER_RULINGS / DT9_OPEN, shortened.
"""
from __future__ import annotations

import html
import os
import re

# ------------------------------------------------------------------------------------------------ design rulings
# Steltic design rulings that appear in printed text: the id is kept, and its plain meaning is always printed with it
RULINGS = {
    "D-T1": "tapered members checked segment by segment between restraints",
    "D-T2": "IS 18168 adopted voluntarily for Zone III-V portals, route B",
    "D-T3": "doubly symmetric welded sections only",
    "D-T4": "seismic braces designed for compression, no tension-only rods",
    "D-T5": "purlins and girts designed to IS 801 / IS 811 with the cold-formed engine",
    "D-T6": "complete-penetration welds for the connection welds",
    "D-T7": "joints designed for 1.2 Mp",
    "D-T9": "reading of the IS 18168 6.5 flange splice-plate rule, open",
    "D8": "floor area taken as the proxy for the number of occupants",
}
RULING_PREFIX = "Steltic design ruling"


def ruling_meaning(rid):
    return RULINGS.get(str(rid).strip())


# ------------------------------------------------------------------------------------------------ analysis gates
GATE_LABELS = {
    "rsa_X": "response spectrum base shear scaled to V&#772;<sub>B</sub>, X (IS 1893 7.7.3)",
    "rsa_Y": "response spectrum base shear scaled to V&#772;<sub>B</sub>, Y (IS 1893 7.7.3)",
    "modalmass_X": "modal mass participation at least 90 %, X (IS 1893 7.7.5.2)",
    "modalmass_Y": "modal mass participation at least 90 %, Y (IS 1893 7.7.5.2)",
    "esm_permitted": "equivalent static method permitted (IS 1893 7.7.1)",
    "stability": "model stable (every eigenvalue positive)",
    "drift_X": "storey drift within the IS 1893 7.11.1.1 limit, X",
    "drift_Y": "storey drift within the IS 1893 7.11.1.1 limit, Y",
    "wind_defl_X": "wind sway within the IS 800 Table 6 limit, X",
    "wind_defl_Y": "wind sway within the IS 800 Table 6 limit, Y",
    "dynamic_wind": "dynamic wind applied where IS 875 (Part 3) 9.1 requires it",
    "crane_sway": "crane frame sway within the IS 800 Table 6 limit",
    "beam_deflection": "floor and roof beam deflection within the IS 800 Table 6 limits",
    "model_declared": "structural model declared (bases, joints, gravity system)",
    "model_consistent": "built model consistent with the declared bases and joints",
    "model_complete": "floor framing complete (no bay without beams)",
    "equil_X": "static equilibrium, X", "equil_Y": "static equilibrium, Y",
    "baseshear_X": "applied base shear equals V<sub>B</sub>, X", "baseshear_Y": "applied base shear equals V<sub>B</sub>, Y",
    "period": "fundamental period check (IS 1893 7.6.2)",
    "dual_25pct": "moment frames carry at least 25 % of the base shear (dual system)",
}
# the same in plain text (no HTML), for text that is escaped after the pass
_GATE_PLAIN = {k: html.unescape(re.sub(r"<[^>]+>", "", v)) for k, v in GATE_LABELS.items()}


def gate_label(key, plain=False):
    k = str(key)
    lab = (_GATE_PLAIN if plain else GATE_LABELS).get(k)
    return lab if lab else humanise(k)


# ------------------------------------------------------------------------------------------------ wind table
WIND_LABELS = {
    "Vb_mps": "basic wind speed V<sub>b</sub> (m/s) (6.2)",
    "Vb_source": "V<sub>b</sub> source", "Vb_note": "V<sub>b</sub> note",
    "terrain_category": "terrain category (6.3.2.1)", "terrain_basis": "terrain basis",
    "k1": "k<sub>1</sub>, probability factor (risk coefficient) (6.3.1)",
    "k2": "k<sub>2</sub>, terrain roughness and height factor (6.3.2)",
    "k3": "k<sub>3</sub>, topography factor (6.3.3)", "k3_basis": "k<sub>3</sub> basis",
    "k4": "k<sub>4</sub>, importance factor for the cyclonic region (6.3.4)",
    "Kd": "K<sub>d</sub>, wind directionality factor (7.2.1)",
    "Ka": "K<sub>a</sub>, area averaging factor (7.2.2)", "Ka_basis": "K<sub>a</sub> basis",
    "Kc": "K<sub>c</sub>, combination factor (7.3.3.13)",
    "Vz_mps": "design wind speed V<sub>z</sub> (m/s) (6.3)",
    "pz_kNm2": "wind pressure p<sub>z</sub> = 0.6 V<sub>z</sub><sup>2</sup> (kN/m²) (7.2)",
    "pd_kNm2": "design wind pressure p<sub>d</sub> (kN/m²) (7.2)",
    "Cpe_windward": "C<sub>pe</sub>, windward wall", "Cpe_leeward": "C<sub>pe</sub>, leeward wall",
    "Cpi": "C<sub>pi</sub>, internal pressure coefficient",
    "cyclone_belt": "cyclone-prone region",
    "VB_x_kN": "wind base shear, X (kN)", "VB_y_kN": "wind base shear, Y (kN)",
}


def wind_label(key):
    return WIND_LABELS.get(str(key)) or humanise(str(key))


# ------------------------------------------------------------------------------------------------ IS 800 Table 6
# the engine's Table 6 row keys (india_loads.IS800_TABLE6) as the rows of IS 800:2007 Table 6 (corpus transcription)
TABLE6_ROWS = {
    "floor_roof_live_not_cracking": "other buildings, floor and roof, live load, elements not susceptible to cracking",
    "floor_roof_live_cracking": "other buildings, floor and roof, live load, elements susceptible to cracking",
    "cantilever_live_not_cracking": "other buildings, cantilever, live load, elements not susceptible to cracking",
    "cantilever_live_cracking": "other buildings, cantilever, live load, elements susceptible to cracking",
    "building_wind_elastic": "other buildings, lateral, wind, building with elastic cladding",
    "building_wind_brittle": "other buildings, lateral, wind, building with brittle cladding",
    "storey_wind": "other buildings, lateral, wind, inter-storey drift",
    "purlin_girt_elastic": "industrial buildings, purlins and girts, elastic cladding",
    "purlin_girt_brittle": "industrial buildings, purlins and girts, brittle cladding",
    "industrial_simple_span_live_elastic": "industrial buildings, simple span, live load, elastic cladding",
    "industrial_simple_span_live_brittle": "industrial buildings, simple span, live load, brittle cladding",
    "industrial_cantilever_live_elastic": "industrial buildings, cantilever span, live load, elastic cladding",
    "industrial_cantilever_live_brittle": "industrial buildings, cantilever span, live load, brittle cladding",
    "rafter_profiled_sheeting": "industrial buildings, rafter supporting profiled metal sheeting",
    "rafter_plastered_sheeting": "industrial buildings, rafter supporting plastered sheeting",
    "gantry_manual": "industrial buildings, gantry, crane load (manual operation)",
    "gantry_electric_upto_50t": "industrial buildings, gantry, crane load (electric operation up to 50 t)",
    "gantry_electric_over_50t": "industrial buildings, gantry, crane load (electric operation over 50 t)",
    "column_no_crane_elastic": "industrial buildings, lateral, no cranes, column with elastic cladding",
    "column_no_crane_brittle": "industrial buildings, lateral, no cranes, column with masonry / brittle cladding",
    "gantry_lateral_crane_absolute": "industrial buildings, lateral, crane + wind, gantry (crane, absolute)",
    "gantry_lateral_rails_relative_mm": "industrial buildings, lateral, crane + wind, relative displacement between rails",
    "frame_crane_pendant_elastic": "industrial buildings, lateral, crane + wind, column / frame (elastic cladding, "
                                   "pendant operated)",
    "frame_crane_cab_brittle": "industrial buildings, lateral, crane + wind, column / frame (brittle cladding, cab "
                               "operated)",
}


def table6_text(key):
    return TABLE6_ROWS.get(str(key)) or humanise(str(key))


# ------------------------------------------------------------------------------------------------ check ids
def check_label(cid):
    """A Section 12 / check id spelt out: 'is18168_7_2_column_KL_r' -> 'IS 18168 7.2 column KL/r',
    '12.11.3.2_SCWB' -> '12.11.3.2 SCWB', 'brace_conn_1p2Mp' -> 'brace conn 1.2 Mp'."""
    s = str(cid if cid is not None else "")
    s = re.sub(r"^is18168_table(\d+)_", r"IS 18168 Table \1 ", s)
    s = re.sub(r"^is18168_(\d+)_(\d+)_(\d+)_", r"IS 18168 \1.\2.\3 ", s)
    s = re.sub(r"^is18168_(\d+)_(\d+)_", r"IS 18168 \1.\2 ", s)
    s = re.sub(r"^is800_(\d+)_(\d+)_(\d+)", r"IS 800 \1.\2.\3", s)
    s = re.sub(r"(\d)p(\d)Mp\b", r"\1.\2 Mp", s)
    s = s.replace("KL_r", "KL/r")
    s = re.sub(r"^([\d.]+)_", r"\1 ", s)
    return s.replace("_", " ").strip()


def humanise(token):
    """A snake_case key or value spelt out ('frame_tributary' -> 'frame tributary', 'KL_r' -> 'KL/r')."""
    t = str(token).replace("KL_r", "KL/r")
    return re.sub(r"_+", " ", t).strip()


# ------------------------------------------------------------------------------------------------ the pass
_HERE = os.path.dirname(os.path.abspath(__file__))
try:
    # module names with an underscore or a digit only: 'report', 'sections', 'pipeline' ... are also English words
    # ('report.html'), so a bare word followed by a dot is never taken for a module
    _MODULES = sorted({f[:-3] for f in os.listdir(_HERE) if f.endswith(".py") and re.search(r"[_\d]", f[:-3])} |
                      {"india_cfs_members", "india_cfs_gates", "india_cfs_portal", "india_cfs_pipeline", "is801_members",
                       "hr_vendor_runner", "report_cfs_india", "report_cfs_second_wave", "peb_lever_study"},
                      key=len, reverse=True)
except OSError:                                                   # pragma: no cover
    _MODULES = ["engine3d", "india_is800", "india_seismic_gates", "india_combos", "india_loads", "peb_autosize"]
_MOD_ALT = "|".join(re.escape(m) for m in _MODULES)

# named module references with a plain replacement (the rest are dropped)
_MODULE_WORDS = [
    (r"(?:steltic_(?:CFS|cfs)_india\s+)?india_cfs_members\.design_purlins", "Steltic cold-formed engine"),
    (r"india_seismic_gates\.design_status", "the design status check"),
    (r"\s*by india_combos\.expand_combinations", ""),
    (r"india_combos\.expand_combinations", "the combination generator"),
    (r"india_is800\.member_check_is800", "IS 800 member check"),
    (r"(?:HR\s+)?india_loads\.ponding_screen_4_4", "ponding screen"),
]
_CFG_WORDS = {
    "flexible_diaphragm_analysis": "flexible-diaphragm analysis requested",
    "flange_braces": "flange braces as declared",
    "peb_secondary": "declared secondary members",
    "peb_connection_mass_kg": "declared connection plate masses",
    "ponding": "declared ponding input",
    "D_roof_pv": "rooftop PV load",
    "solar_pv": "rooftop PV load",
}

_SUBS = None


def _subs():
    global _SUBS
    if _SUBS is not None:
        return _SUBS
    s = []
    # build-machine paths and file names (with the brackets / separators they leave behind)
    s.append((re.compile(r"[;,]?\s*(?:study folder|variant jobs in|study run in)?\s*(?<![\w.])/(?:home|tmp|root|mnt|usr|var|opt|Users)/[^\s,;)\]]*"), ""))
    s.append((re.compile(r"[;,]?\s*(?<![\w])(?:[\w.-]+/)*[A-Za-z_]\w*\.py\b(?:\s+--[\w-]+(?:\s+(?!and\b|or\b)[a-z_]+\b)?)*"), ""))
    # a bracketed reference to a job data file inside a sentence ('(design/pv_capacity.json)'); a deliverable link
    # text such as 'design/reactions.csv' is not bracketed and is kept
    s.append((re.compile(r"\s*\(\s*design/[\w.-]+\.(?:json|csv)\s*\)"), ""))
    # repository / branch / commit references
    s.append((re.compile(r"\bsteltic_(?:india|CFS_india|cfs_india|nonlinear_india|hub_india)\s+(?:feat|fix)/[\w.-]+(?:\s+[0-9a-f]{7,40}\b)?"), "Steltic"))
    s.append((re.compile(r"\b(?:feat|fix)/2026-[\w.-]+(?:\s+[0-9a-f]{7,40}\b)?"), ""))
    s.append((re.compile(r"\(\s*steltic_india\s*\)"), ""))
    # named module references, then any other '<module>.<attr>' (dropped)
    for rx, rep in _MODULE_WORDS:
        s.append((re.compile(r"\b" + rx + r"\b"), rep))
    s.append((re.compile(r"\s*\(\s*(?:%s)\.\w+(?:\(\))?\s*\)" % _MOD_ALT), ""))
    s.append((re.compile(r"\b(?:%s)\.[A-Za-z_]\w*(?:\(\))?" % _MOD_ALT), ""))
    s.append((re.compile(r"\bsteel_engine/\S*"), ""))
    s.append((re.compile(r"\bsteltic_(?:india|CFS_india|cfs_india|nonlinear_india|hub_india)\b"), "Steltic"))
    # internal specification / work-package references
    s.append((re.compile(r"\s*\(\s*spec\s+WP\d+(?:\.\d+)*\s*\)"), ""))
    s.append((re.compile(r"\bspec\s+WP\d+(?:\.\d+)*"), ""))
    # cfg references: cfg['key'] (= value) and 'cfg key'
    _q = r"(?:'|\"|&#x27;|&#39;|&quot;)"                  # quotes, also as the HTML escapes of an escaped cell
    s.append((re.compile(r"cfg\[\s*" + _q + r"(\w+)" + _q + r"\s*\](?:\s*=\s*(?:True|False|\w+))?"),
              lambda m: _CFG_WORDS.get(m.group(1)) or ("declared " + humanise(m.group(1)))))
    s.append((re.compile(r"\bcfg\s+(D_roof_pv|solar_pv|\w+_kNm2)\b"), lambda m: _CFG_WORDS.get(m.group(1), "the job input")))
    s.append((re.compile(_q + r"solar_pv" + _q), "PV load"))
    # IS 800 Table 6 row keys and gamma_f
    s.append((re.compile(r"\b(%s)\b" % "|".join(sorted(TABLE6_ROWS, key=len, reverse=True))), lambda m: TABLE6_ROWS[m.group(1)]))
    s.append((re.compile(r"\bgamma_f\b"), "γf"))
    # analysis gate keys after the word 'gate'
    s.append((re.compile(r"\b(gate:?\s+)(%s)\b" % "|".join(sorted(GATE_LABELS, key=len, reverse=True))),
              lambda m: m.group(1) + "'" + _GATE_PLAIN[m.group(2)] + "'"))
    s.append((re.compile(r"\(was None\)"), ""))
    # keys of the comparison records written by the study scripts (the report prints none of these records)
    _jk = r"(?:difference_vs_gold|checks_that_fall_away|code_status_R3|kg_m2_by_group|same_section_dc_drop)"
    s.append((re.compile(r"\s*\(\s*(?:listed in\s+|see\s+)?" + _jk + r"\s*\)"), ""))
    s.append((re.compile(r",?\s*(?:listed in|see)\s+" + _jk + r"\b"), ""))
    s.append((re.compile(r"\b" + _jk + r"\b"), "the study record"))
    # analysis gate keys anywhere (a gate key printed on its own, e.g. in a table cell)
    s.append((re.compile(r"\b(%s)\b" % "|".join(sorted((k for k in GATE_LABELS if "_" in k), key=len, reverse=True))),
              lambda m: _GATE_PLAIN[m.group(1)]))
    s.append((re.compile(r":\s*ok:false\b"), ": not satisfied"))
    s.append((re.compile(r"\bD8 area proxy\b"), "Steltic design ruling D8 (floor area as the proxy for the number of "
                                                 "occupants)"))
    s.append((re.compile(r"\bsecondary_member\b"), "secondary member"))
    # internal words
    s.append((re.compile(r"\bowner rulings of the gold\b"), "design rules of the published design"))
    s.append((re.compile(r"\b(?:the\s+)?owner rulings\b"), "the project's design rules"))
    s.append((re.compile(r"\bby owner decision(?:\s*\(\d{4}-\d{2}\))?"), "as an adopted design decision"))
    s.append((re.compile(r"\bowner decision(?:\s*\(\d{4}-\d{2}\))?"), "adopted design decision"))
    s.append((re.compile(r"\(\s*brief ruling\s*\)"), "(as set in the design brief)"))
    s.append((re.compile(r"\bbrief ruling\b"), "design-brief rule"))
    s.append((re.compile(r"\bAs designed \(gold\)"), "As designed (published design)"))
    s.append((re.compile(r"\b(IN_Ex\d+) gold package\b"), r"the published \1 design"))
    s.append((re.compile(r"\bgold package\b"), "published design"))
    s.append((re.compile(r"\bthe gold as published\b"), "the published design"))
    s.append((re.compile(r"\bthe gold's\b"), "the published design's"))
    s.append((re.compile(r"\bthe gold\b"), "the published design"))
    s.append((re.compile(r"\bgold sizes\b"), "published sizes"))
    s.append((re.compile(r"\ba gold\b"), "a published"))
    s.append((re.compile(r"\bgold\b"), "published design"))
    # tidy what the removals leave behind
    s += [(re.compile(r"\(\s*[;,]?\s*\)"), ""), (re.compile(r"\(\s*[;,]\s*"), "("), (re.compile(r"\s+([;,)])"), r"\1"),
          (re.compile(r"[ \t]{2,}"), " "), (re.compile(r",\s*,"), ","), (re.compile(r"\(\s*,"), "(")]
    _SUBS = s
    return s


_RULE_RE = re.compile(r"(?P<pre>(?:\bopen\s+)?(?:\bowner\s+)?\bruling\s+)?(?<![\w-])(?P<id>D-T\d+|D8)(?![\w-])"
                      r"(?P<open>\s*\(open\))?(?P<rb>\s+route B)?")


def _rulings(text):
    """Every ruling id with the Steltic prefix and its plain meaning (a bare id alone in a table cell is left: its
    meaning is in the next cell)."""
    if re.fullmatch(r"\s*(?:D-T\d+|D8)(?:\s*\(open\))?\s*", text or ""):
        return text

    def rep(m):
        rid = m.group("id")
        meaning = RULINGS.get(rid)
        if not meaning:
            return m.group(0)
        start = m.start()
        if re.search(r"Steltic design ruling\s*$", text[max(0, m.start("id") - 40): m.start("id")]):
            return m.group(0)                            # already printed with the prefix (and its meaning)
        is_open = bool(m.group("open")) or bool(re.search(r"\bopen\s+", m.group("pre") or ""))
        head = ("open " if is_open and m.group("pre") else "") + RULING_PREFIX + " " + rid + (m.group("open") or "")
        after = text[m.end(): m.end() + 2]
        if after.startswith(":"):
            return head                                  # the meaning follows after the colon
        inside = text[:start].count("(") > text[:start].count(")")
        return head + (": " + meaning if inside else " (" + meaning + ")")
    return _RULE_RE.sub(rep, text)


def public_text(text):
    """The public-text pass on plain text (see the module docstring)."""
    s = str(text if text is not None else "")
    if not s.strip():
        return s
    for rx, rep in _subs():
        s = rx.sub(rep, s)
    return _rulings(s)


_SNAKE = re.compile(r"(?<![\w./-])([A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+)(?![\w-])")
_KEEP = re.compile(r"^(?:[A-Z]{1,3}\d?_[XYZ]\w*|W_[XY]\w*|EQ_[XYZ]\w*|N_[XY]|DL\w*|LL\w*|IN_Ex\w*)$")


def strict_text(text):
    """public_text, then every remaining snake_case token spelt out (load case names such as EQ_X / W_Y_across and
    member ids such as 'lateral_col-WI956X250X14X6' are kept: they are names used throughout the report)."""
    s = public_text(text)
    s = re.sub(r"(?<=\d)_(?=[A-Za-z])", " ", s)            # '12.11.3.2_SCWB' -> '12.11.3.2 SCWB'
    s = _SNAKE.sub(lambda m: m.group(1) if _KEEP.match(m.group(1)) else humanise(m.group(1)), s)
    return public_text(s)                                  # a spelt-out key may form a word the pass replaces


def public_html(html_text, strict=False):
    """public_text (or strict_text) on the text of an HTML fragment; tags, attributes and entities untouched."""
    fn = strict_text if strict else public_text
    parts = re.split(r"(<[^>]+>)", str(html_text or ""))
    return "".join(p if p.startswith("<") else fn(p) for p in parts)


# what the pass refuses to print (used by the tests and the gold scan)
LEAK_PATTERNS = {
    "path": r"(?<![\w.])/(?:home|tmp|root|mnt|usr|var|opt|Users)/\S+",
    "py file": r"\b\w+\.py\b",
    "module": r"\b(?:%s)\.[A-Za-z_]\w*" % _MOD_ALT,
    "repository": r"\bsteltic_(?:india|CFS_india|cfs_india|nonlinear_india|hub_india)\b|\b(?:feat|fix)/20\d\d-",
    "json key": r"\b(?:difference_vs_gold|checks_that_fall_away|code_status_R3|kg_m2_by_group|worst_strength_dc|"
                r"solar_pv|D_roof_pv|wind_defl_[XY])\b|\bcfg\[|\bcfg\s+\w",
    "internal word": r"\bgold\b|\bowner rulings?\b|\bowner decision\b|\bbrief ruling\b|\bspec\s+WP\d|\(was None\)",
    "bare ruling": r"(?<![\w-])(?:D-T\d+|D8)(?![\w-])",
}
_LEAK_RE = {k: re.compile(v) for k, v in LEAK_PATTERNS.items()}


def leaks(text, kinds=None):
    """[(kind, match)] of everything the public-text pass would refuse in plain text (HTML tags are skipped)."""
    s = re.sub(r"<[^>]+>", " | ", str(text or ""))           # a tag boundary reads as a cell boundary
    s = html.unescape(s)
    out = []
    for k, rx in _LEAK_RE.items():
        if kinds and k not in kinds:
            continue
        if k == "bare ruling":
            for m in rx.finditer(s):
                if s[max(0, m.start() - 22): m.start()].endswith(RULING_PREFIX + " "):
                    continue
                if not s[max(0, m.start() - 2): m.start()].strip(" |") and \
                        re.match(r"\s*(?:\(open\))?\s*(?:\||$)", s[m.end(): m.end() + 12]):
                    continue                                 # a lone table cell: its meaning is in the next cell
                out.append((k, m.group(0)))
            continue
        out += [(k, m.group(0)) for m in rx.finditer(s)]
    return out
