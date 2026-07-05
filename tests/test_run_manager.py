"""Run Manager + Artifact Workspace — reproducibility backbone."""
from saathi.run_manager import RunManager


def test_new_run_allocates_sequential_ids(tmp_path):
    rm = RunManager(root=tmp_path)
    a = rm.new_run(prefix="PAT", now=1_800_000_000)
    b = rm.new_run(prefix="PAT", now=1_800_000_000)
    assert a.id.startswith("PAT-") and a.id.endswith("-001")
    assert b.id.endswith("-002")
    assert a.dir.is_dir() and b.dir.is_dir()


def test_save_and_verify_artifacts(tmp_path):
    rm = RunManager(root=tmp_path)
    run = rm.new_run(prefix="YETI")
    run.save_text("research.md", "# topic\nevidence")
    run.save_json("metadata.json", {"title": "x"})
    run.save_bytes("narration.wav", b"\x00\x01")
    assert run.verify("research.md") and run.verify("metadata.json") and run.verify("narration.wav")
    assert not run.verify("video.mp4")                 # never created
    run.save_text("empty.txt", "")
    assert not run.verify("empty.txt")                 # exists but empty → not a real artifact


def test_timeline_and_stage_flags(tmp_path):
    rm = RunManager(root=tmp_path)
    run = rm.new_run(prefix="PAT")
    run.stage_start("research"); run.save_text("research.md", "x")
    run.stage_end("research", ok=run.verify("research.md"), artifact="research.md")
    run.stage_start("render")
    run.stage_end("render", ok=run.verify("video.mp4"), artifact="video.mp4")
    flags = run.stage_flags()
    assert flags["research"] is True and flags["render"] is False
    assert run.artifacts() == {"research.md": True, "video.mp4": False}


def test_finalize_writes_manifest_and_get_reloads(tmp_path):
    rm = RunManager(root=tmp_path)
    run = rm.new_run(prefix="PAT")
    run.stage_start("script"); run.save_text("script.md", "s")
    run.stage_end("script", ok=True, artifact="script.md")
    run.finalize("published")
    again = rm.get(run.id)
    assert again is not None and again.status == "published"
    assert again.stage_flags()["script"] is True
    assert run.id in [m["id"] for m in rm.recent()]
