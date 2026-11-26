"""Export a source-bound, metric openBIM handoff from a finished India HR job.

Run `python -m steel_engine.openbim_handoff JOB PHYSICAL_DECLARATION.json`.
The declaration supplies the physical occurrence layout for the India openBIM
contract. A single source_element can supply its native workline and section.
"""
import argparse
from copy import deepcopy
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile


def _sha(path):
    with path.open("rb") as stream:
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _viewer(path):
    text = path.read_text(encoding="utf-8-sig")
    _, marker, tail = text.partition("const DATA = ")
    if not marker:
        raise ValueError(f"{path.name} has no native JSON frame geometry")
    data, _ = json.JSONDecoder().raw_decode(tail.lstrip())
    return {int(r["tag"]): (r["sec"], [data["nodes"][str(n)] for n in r["n"]]) for r in data["elements"]}


def _units(job):
    if not (job/"units_summary.json").is_file():
        return [("Main",job)]
    paths = sorted(p for p in (job/"units").iterdir() if p.is_dir())
    if not paths:
        raise ValueError("The multi-unit summary has no unit directories")
    return [(p.name,p) for p in paths]


def _catalogue():
    result={}
    for filename in ("is808_shapes.csv","is1161_tubes.csv"):
        with Path(__file__).with_name(filename).open(encoding="utf-8-sig",newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("validated")!="ok":
                    continue
                kind=row["Type"]
                if kind=="CHS":
                    family="CHS"
                    dims={"diameter":float(row["D_mm"]),"t":float(row["t_mm"])}
                else:
                    family="L" if kind=="ISA" else "C" if kind in ("MC","MPC","LC","SC","JC") else "I"
                    dims={k:float(row[n]) for k,n in (("d","D_mm"),("b","B_mm"),("tw","tw_mm"),("tf","tf_mm"))}
                    for k,n in (("r","R1_mm"),("r2","R2_mm")):
                        if row.get(n):
                            dims[k]=float(row[n])
                    if family=="I" and row.get("flange_slope_deg"):
                        dims["slope_deg"]=float(row["flange_slope_deg"])-90
                result[row["Label"]] = (family,dims)
    return result


def _verify_section(name, native, profiles):
    family,dims=native
    declared=profiles.setdefault(name,{"family":family,"dimensions_mm":{}})
    if declared.get("family")!=family or "contours_mm" in declared:
        raise ValueError(f"{name}: profile family disagrees with the native rolled catalogue")
    values=declared.setdefault("dimensions_mm",{})
    for k,v in dims.items():
        current=values.setdefault(k,v)
        if not isinstance(current,(int,float)) or not math.isclose(current,v,abs_tol=.005,rel_tol=1e-6):
            raise ValueError(f"{name}: {k} differs from native section dimension {v}")


def _scheduled_grades(calc, schedule):
    """Attach the calculation group's selected grade to each scheduled element."""
    if not schedule.is_file():
        return {}
    selected = {}
    for member in calc.get("members", []):
        inputs = member.get("inputs", {})
        key = inputs.get("role"), inputs.get("section")
        grade = inputs.get("grade")
        if grade and selected.setdefault(key, grade) != grade:
            raise ValueError(f"Ambiguous native grade for {key}")
    grades = {}
    with schedule.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            grade = selected.get((row.get("role"), row.get("section")))
            if grade:
                grades[int(row["ele_tag"])] = grade
    return grades


def _binding(row, views):
    refs = row.get("source_elements")
    if refs is None:
        refs = [row["source_element"]] if "source_element" in row else []
    if not isinstance(refs,list):
        raise ValueError("source_elements must be a list")
    used, segments = set(), []
    for ref in refs:
        unit = ref.get("unit","Main")
        tag = ref["tag"]
        if isinstance(tag,bool) or not isinstance(tag,int) or tag not in views.get(unit,{}):
            raise ValueError(f"{row['id']}: unknown native element {unit}/{tag}")
        section, points = views[unit][tag]
        delta = ref.get("offset_mm",[0,0,0])
        if len(delta)!=3 or not all(math.isfinite(v) for v in delta):
            raise ValueError(f"{row['id']}: invalid unit set-out")
        ends = [[v+d for v,d in zip(pt,delta)] for pt in points]
        if len(refs)==1:
            row.setdefault("start",ends[0])
            row.setdefault("end",ends[1])
            row.setdefault("profile",section)
        if ref.get("source_profile",row.get("profile")) != section:
            raise ValueError(f"{row['id']}: section disagrees with native {unit}/{tag} ({section})")
        if (unit,tag) in used:
            raise ValueError(f"{row['id']}: repeated source element")
        used.add((unit,tag))
        segments.append(ends)
    if segments:
        a,b = row["start"],row["end"]
        if len(a)!=3 or len(b)!=3 or math.dist(a,b)<1e-6:
            raise ValueError(f"{row['id']}: invalid member endpoints")
        length = math.dist(a,b)
        axis = [(y-x)/length for x,y in zip(a,b)]
        intervals = []
        for ends in segments:
            along = []
            for pt in ends:
                distance = sum((v-x)*d for v,x,d in zip(pt,a,axis))
                projection = [x+distance*d for x,d in zip(a,axis)]
                if math.dist(pt,projection)>.05:
                    raise ValueError(f"{row['id']}: native geometry leaves the declared workline")
                along.append(distance)
            intervals.append(sorted(along))
        intervals.sort()
        if abs(intervals[0][0])>.05 or abs(intervals[-1][1]-length)>.05 or any(abs(p[1]-q[0])>.05 for p,q in zip(intervals,intervals[1:])):
            raise ValueError(f"{row['id']}: declared endpoints or native segment coverage disagree")
    return used


def export_handoff(job_root, declaration):
    """Bind a physical occurrence declaration to this saved job. Return the published JSON path."""
    job = Path(job_root).resolve()
    data = (json.loads(Path(declaration).read_text(encoding="utf-8-sig")) if isinstance(declaration,(str,Path))
            else deepcopy(declaration))
    project = data.get("project",{})
    if data.get("schema_version")!="1.0" or project.get("module")!="HR" or project.get("units")!="mm":
        raise ValueError("Expected an India HR physical declaration with millimetre coordinates")
    members = data.get("members",[])
    if not members or len({m["id"] for m in members})!=len(members):
        raise ValueError("Supply individually identified physical occurrences")
    files, views, status, missing = {}, {}, {}, []
    grades = {}
    if (job/"units_summary.json").is_file():
        files["units_summary.json"] = _sha(job/"units_summary.json")
    for label, directory in _units(job):
        for name in ("design/calc_package.json","design/cfg_snapshot.json","design/member_schedule.csv",
                     "report.html","viewer_3d.html","STATUS.engine.md"):
            file = directory/name
            relative = file.relative_to(job).as_posix()
            if file.is_file():
                files[relative]=_sha(file)
            else:
                missing.append(relative)
        calc_file = directory/"design/calc_package.json"
        if calc_file.is_file():
            calc = json.loads(calc_file.read_text(encoding="utf-8-sig"))
            if calc.get("units",{}).get("length")!="mm" or "800" not in str(calc.get("code","")):
                raise ValueError(f"{label} has no native Indian SI calculation package")
            status[label] = str(calc.get("design_status",{}).get("status") or "unknown").lower()
            grades[label] = _scheduled_grades(calc,directory/"design/member_schedule.csv")
        else:
            status[label]="unavailable"
        viewer = directory/"viewer_3d.html"
        if viewer.is_file():
            views[label]=_viewer(viewer)
    if not files:
        raise ValueError("No native job artifacts were found")
    if "units_summary.json" in files:
        status["composite"] = str(json.loads((job/"units_summary.json").read_text(encoding="utf-8-sig")).get("status","unknown")).lower()
    mapped = set()
    catalogue=_catalogue()
    profiles=data.setdefault("profiles",{})
    verified=set()
    for row in members:
        tags=_binding(row,views)
        selected_grade = data.get("materials",{}).get(row.get("material"),{}).get("grade")
        for unit,tag in tags:
            native_grade = grades.get(unit,{}).get(tag)
            if native_grade and selected_grade != native_grade:
                raise ValueError(f"{row['id']}: grade disagrees with native {unit}/{tag} ({native_grade})")
        mapped.update(tags)
        if len(tags)==1 and not row.get("end_profile"):
            unit,tag=next(iter(tags))
            native_name,_=views[unit][tag]
            token=(native_name,row["profile"])
            if native_name in catalogue and token not in verified:
                _verify_section(row["profile"],catalogue[native_name],profiles)
                verified.add(token)
    known = {(unit,tag) for unit,records in views.items() for tag in records}
    if not mapped and known:
        missing.append("No physical occurrences identify native analysis elements")
    elif known-mapped:
        missing.append(f"{len(known-mapped)} native analysis elements have no physical occurrence binding")
    # The native decision is authoritative even if all author-selected checks passed.
    records = data.setdefault("checks",[])
    records[:] = [r for r in records if r.get("producer")!="steltic_india.openbim_handoff"]
    for unit, outcome in status.items():
        records.append({"id":f"NATIVE-HR-{unit}","description":f"{unit} native HR design status: {outcome}",
                        "status":"pass" if outcome=="complete" else "fail" if outcome in ("failed","fail") else "review",
                        "reference":"IS 800:2007 / native design_status", "producer":"steltic_india.openbim_handoff"})
    if missing:
        records.append({"id":"NATIVE-HR-SCOPE","description":"; ".join(missing), "status":"review",
                        "reference":"Native job evidence", "producer":"steltic_india.openbim_handoff"})
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Check ID collides with an existing declaration")
    data["source_evidence"]={"producer":"steltic_india.openbim_handoff","files":files,"native_status":status,
                             "native_elements":len(known),"bound_elements":len(mapped),"open_items":missing}
    output = job/"design/openbim_handoff.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent,mode="w",encoding="utf-8",suffix=".tmp",delete=False) as temp:
            tmp_name=temp.name
            json.dump(data,temp,ensure_ascii=False,allow_nan=False,separators=(",",":"))
            temp.write("\n")
        if any(_sha(job/name)!=digest for name,digest in files.items()):
            raise ValueError("The native job changed during export; regenerate from a stable run")
        os.replace(tmp_name,output)
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)
    return output


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job",type=Path)
    parser.add_argument("declaration",type=Path)
    args=parser.parse_args()
    print(export_handoff(args.job,args.declaration))
