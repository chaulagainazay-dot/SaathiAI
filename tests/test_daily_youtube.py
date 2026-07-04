"""Daily publisher — queue → publish → record → move → report."""
import json

from saathi.infrastructure.human_browser.daily import publish_next, next_in_queue
from saathi.infrastructure.human_browser.run_store import RunStore


def _queue(tmp_path, name="a.mp4", meta=None):
    q = tmp_path / "youtube"; q.mkdir()
    (q / name).write_bytes(b"video")
    if meta:
        (q / name.replace(".mp4", ".json")).write_text(json.dumps(meta))
    return str(q)


def test_empty_queue_is_noop(tmp_path):
    (tmp_path / "youtube").mkdir()
    out = publish_next(str(tmp_path / "youtube"), publisher=lambda **k: {})
    assert out["status"] == "empty"


def test_next_in_queue_reads_metadata(tmp_path):
    q = _queue(tmp_path, meta={"title": "Ep 1", "visibility": "Public"})
    vid, meta = next_in_queue(q)
    assert vid.name == "a.mp4" and meta["title"] == "Ep 1"


def test_publish_records_moves_and_reports(tmp_path):
    q = _queue(tmp_path, meta={"title": "Mr Yeti Ep 1", "visibility": "Unlisted"})
    store = RunStore(db_path=str(tmp_path / "runs.db"))
    reported = []
    called = {}

    def publisher(*, path, title, description, visibility):
        called.update(path=path, title=title, visibility=visibility)
        return {"video_url": "https://youtu.be/x", "timeline": [{"action": "publish"}]}

    out = publish_next(q, publisher=publisher, store=store, reporter=reported.append)
    assert out["status"] == "ok" and out["video_url"] == "https://youtu.be/x"
    assert called["title"] == "Mr Yeti Ep 1" and called["visibility"] == "Unlisted"
    # recorded to the flight recorder
    assert store.list()[0]["title"] == "Mr Yeti Ep 1" and store.list()[0]["ok"] is True
    # reported (→ VM dashboard) and moved to published/
    assert reported and reported[0]["ok"] is True
    assert not (tmp_path / "youtube" / "a.mp4").exists()
    assert (tmp_path / "youtube" / "published" / "a.mp4").exists()


def test_failed_publish_keeps_file_and_records_failure(tmp_path):
    q = _queue(tmp_path)
    store = RunStore(db_path=str(tmp_path / "runs.db"))

    def bad_publisher(**k):
        raise RuntimeError("selector not found")

    out = publish_next(q, publisher=bad_publisher, store=store)
    assert out["status"] == "failed" and "selector not found" in out["error"]
    assert (tmp_path / "youtube" / "a.mp4").exists()            # not moved on failure
    assert store.list()[0]["ok"] is False
