"""Workflows + Tasks — Mission→Department→Director→Workflow→Task."""
import tempfile, os
from saathi.missions.workflow import WorkflowStore, provision_execution, TEMPLATES


def _s():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return WorkflowStore(p)


def test_create_workflow_from_template_seeds_tasks():
    s = _s()
    wf = s.create("M1", director="social_media")
    assert wf["name"] == "Instagram Growth"
    assert [t["title"] for t in wf["tasks"]] == TEMPLATES["social_media"]["tasks"]
    assert all(t["status"] == "todo" for t in wf["tasks"])
    assert wf["progress"] == 0.0


def test_task_status_updates_progress():
    s = _s()
    wf = s.create("M1", director="seo")
    t0 = wf["tasks"][0]["id"]
    assert s.set_task(t0, "done") is True
    assert s.set_task(t0, "nonsense") is False
    got = s.get(wf["id"])
    assert got["tasks"][0]["status"] == "done"
    assert got["progress"] > 0


def test_open_tasks_prioritises_doing():
    s = _s()
    wf = s.create("M1", director="sales")
    ids = [t["id"] for t in wf["tasks"]]
    s.set_task(ids[0], "done")
    s.set_task(ids[3], "doing")
    open_t = s.open_tasks("M1")
    assert open_t[0]["status"] == "doing"                 # doing floats to top
    assert all(t["status"] != "done" for t in open_t)


def test_list_scoped_per_mission():
    s = _s()
    s.create("M1", director="seo"); s.create("M2", director="sales")
    assert len(s.list("M1")) == 1 and len(s.list("M2")) == 1


def test_provision_execution_stands_up_department_kit():
    s = _s()
    wfs = provision_execution("M1", "travel", store=s)
    names = {w["name"] for w in wfs}
    assert "Instagram Growth" in names and "SEO Sprint" in names   # travel kit
    assert len(s.list("M1")) == len(wfs)
    # unknown template → still gets a workflow (generic marketing)
    assert provision_execution("M2", "weird", store=s)
