import json

import pytest

from steel_engine.openbim_handoff import export_handoff


def test_native_occurrence_uses_saved_workline_and_partial_status(tmp_path):
    (tmp_path/"design").mkdir()
    (tmp_path/"design/calc_package.json").write_text(json.dumps({
        "units":{"length":"mm"},"code":"IS 800:2007 LSD","design_status":{"status":"partial"}}))
    model={"nodes":{"1":[0,0,0],"2":[0,0,3500]},
           "elements":[{"tag":5,"sec":"MB300","n":[1,2]}]}
    (tmp_path/"viewer_3d.html").write_text("<script>const DATA = "+json.dumps(model)+";</script>")
    data={"schema_version":"1.0","project":{"id":"unit","name":"Unit","module":"HR","units":"mm"},
          "members":[{"id":"C1","source_element":{"tag":5}}]}
    path=export_handoff(tmp_path,data)
    value=json.loads(path.read_bytes())
    assert value["members"][0]["end"]==[0,0,3500]
    assert value["members"][0]["profile"]=="MB300"
    assert value["profiles"]["MB300"]["dimensions_mm"]["d"]==300
    assert value["source_evidence"]["bound_elements"]==1
    assert "design/calc_package.json" in value["source_evidence"]["files"]
    assert any(c["status"]=="review" for c in value["checks"])
    prior=path.read_bytes()
    assert export_handoff(tmp_path,path).read_bytes()==prior
    data["members"][0]["end"]=[0,0,3000]
    with pytest.raises(ValueError,match="coverage disagree"):
        export_handoff(tmp_path,data)
    assert path.read_bytes()==prior
    data["members"][0].pop("end")
    data["profiles"]={"MB300":{"family":"I","dimensions_mm":{"tw":99}}}
    with pytest.raises(ValueError,match="native section dimension"):
        export_handoff(tmp_path,data)
