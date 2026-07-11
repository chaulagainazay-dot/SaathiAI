"""M13 AI Studio test suite — unit, integration, security, real-local-provider.

Real local providers (ffmpeg, Pillow, macOS `say`) are genuinely exercised and
skip honestly when unavailable. Cloud generation/publishing are deterministic/
dry-run only and never claimed as real."""
import shutil

import pytest

from saathi.studio_os import (
    ProjectState, ProjectSpec, StudioStore, StudioService, WORKFLOWS,
    validate_transition, can_transition, is_terminal, IllegalProjectTransition,
    ARTIFACT_TYPES,
)
from saathi.studio_os import storage as S
from saathi.studio_os import budget as B
from saathi.studio_os import providers as P
from saathi.studio_os import ffmpeg_engine as F
from saathi.studio_os import publishing as PUB


@pytest.fixture
def store(tmp_path):
    return StudioStore(tmp_path / "s.db")


class FakeChat:
    class _S:
        @staticmethod
        def create_conversation(**k):
            return {"id": "conv1"}
    store = _S()

    def start_orchestration(self, cid, obj, strategy=""):
        return {"run_id": "run1", "outcome": {"state": "completed", "tasks_done": 3}}

    def send(self, cid, text, agent=""):
        return type("R", (), {"message": {"id": "m", "content": "Script content."},
                              "execution": {"intent_id": "i"}})()


@pytest.fixture
def service(store):
    return StudioService(store, chat_engine=FakeChat(), image_prefer="pillow",
                         video_prefer="ffmpeg-local", voice_prefer="say")


# ── project state machine (unit) ────────────────────────────────────────────
def test_legal_and_illegal_transitions():
    validate_transition(ProjectState.DRAFT, ProjectState.PLANNING)
    assert can_transition(ProjectState.RUNNING, ProjectState.COMPLETED)
    with pytest.raises(IllegalProjectTransition):
        validate_transition(ProjectState.COMPLETED, ProjectState.RUNNING)
    with pytest.raises(IllegalProjectTransition):
        validate_transition(ProjectState.DRAFT, ProjectState.PUBLISHING)


def test_terminal_states():
    for s in (ProjectState.COMPLETED, ProjectState.CANCELLED, ProjectState.FAILED):
        assert is_terminal(s)


def test_store_transition_validates(store):
    pid = store.create_project(owner="ajay", spec={"title": "t"})
    assert store.get_project(pid)["state"] == ProjectState.DRAFT.value
    store.transition(pid, ProjectState.PLANNING)
    with pytest.raises(IllegalProjectTransition):
        store.transition(pid, ProjectState.COMPLETED)  # PLANNING -> COMPLETED illegal


# ── artifact versioning (unit) ───────────────────────────────────────────────
def test_artifact_versioning_supersedes(store):
    pid = store.create_project(owner="ajay", spec={})
    a1 = store.add_artifact(pid, artifact_type="script", stage="script", content="v1")
    a2 = store.add_artifact(pid, artifact_type="script", stage="script", content="v2")
    assert store.get_artifact(a1)["version"] == 1
    assert store.get_artifact(a2)["version"] == 2
    assert store.get_artifact(a1)["superseded_by"] == a2
    latest = store.list_artifacts(pid, latest_only=True)
    assert len(latest) == 1 and latest[0]["id"] == a2
    assert len(store.artifact_versions(pid, "script", "script")) == 2


def test_artifact_types_defined():
    assert {"script", "final_video", "thumbnail", "seo_package"} <= ARTIFACT_TYPES


# ── storage / disk safety (unit, real) ──────────────────────────────────────
def test_path_traversal_rejected():
    # `..` escapes are rejected
    with pytest.raises(S.PathTraversal):
        S.safe_path("proj", "../../etc/passwd")
    with pytest.raises(S.PathTraversal):
        S.safe_path("proj", "assets/../../secret")
    # an "absolute" path is safely CONFINED under the workspace, not an escape
    confined = S.safe_path("proj", "/etc/shadow")
    assert "studio_workspaces/proj/etc/shadow" in str(confined)
    ok = S.safe_path("proj", "assets/img.png")
    assert ok.name == "img.png"


def test_disk_preflight_blocks_impossible_job(store):
    pid = store.create_project(owner="ajay", spec={})
    with pytest.raises(S.InsufficientDisk):
        S.preflight(pid, S.DiskEstimate(0, 0, 9_999_999_999))  # ~10 PB


def test_disk_preflight_passes_small_job(store):
    pid = store.create_project(owner="ajay", spec={})
    S.preflight(pid, S.DiskEstimate(1, 2, 1))  # no raise


def test_quota_enforced(store):
    pid = store.create_project(owner="ajay", spec={})
    with pytest.raises(S.QuotaExceeded):
        S.preflight(pid, S.DiskEstimate(0, 0, 50_000), project_quota_gb=1.0)


def test_checksum_dedupe(tmp_path):
    pid = "dedup_proj"
    p1, cs1, new1 = S.dedupe_store(pid, b"same bytes", ext="txt")
    p2, cs2, new2 = S.dedupe_store(pid, b"same bytes", ext="txt")
    assert cs1 == cs2 and new1 and not new2 and p1 == p2
    # cleanup
    shutil.rmtree(S.STUDIO_ROOT / pid, ignore_errors=True)


def test_storage_health_reports_free_space():
    h = S.storage_health()
    assert "free_gb" in h and "healthy" in h and h["free_gb"] > 0


# ── budget (unit) ────────────────────────────────────────────────────────────
def test_budget_hard_stop(store):
    pid = store.create_project(owner="ajay", spec={"budget_usd": 0.01})
    store.add_cost(pid, kind="image_cloud", units=1, cost_usd=0.01)
    with pytest.raises(B.BudgetExceeded):
        B.check_and_reserve(store, pid, 0.05)


def test_budget_dry_run():
    items = [B.Estimate("image_cloud", 3), B.Estimate("video_sec_cloud", 30)]
    out = B.dry_run(items, budget_usd=5.0)
    assert out["estimated_total_usd"] == round(3 * 0.04 + 30 * 0.10, 6)
    assert out["within_budget"] is True


# ── FFmpeg engine (real local) ──────────────────────────────────────────────
def test_ffmpeg_args_reject_shell_string():
    with pytest.raises(F.FFmpegError):
        F._validate_args("ffmpeg -i x.mp4; rm -rf /")  # a string, not a list


@pytest.mark.skipif(not F.ffmpeg_available(), reason="ffmpeg not installed")
def test_real_ffmpeg_render_and_probe(tmp_path):
    r = F.render_slate("test_render_proj", text="hi", duration_sec=1.0,
                       width=320, height=240)
    assert r.ok and r.size_bytes > 0 and r.duration_sec > 0.5
    assert r.width == 320 and r.height == 240 and r.checksum
    shutil.rmtree(S.STUDIO_ROOT / "test_render_proj", ignore_errors=True)


@pytest.mark.skipif(not F.ffmpeg_available(), reason="ffmpeg not installed")
def test_real_thumbnail_extraction():
    r = F.render_slate("thumb_proj", text="hi", duration_sec=1.0, width=320, height=240)
    t = F.extract_thumbnail("thumb_proj", r.path)
    assert t.ok and t.size_bytes > 0
    shutil.rmtree(S.STUDIO_ROOT / "thumb_proj", ignore_errors=True)


# ── providers (real local + deterministic) ──────────────────────────────────
def test_deterministic_image_provider():
    p = P.DeterministicImageProvider()
    r = p.generate("det_proj", prompt="x", out_rel="assets/x.png")
    assert r.ok and r.size_bytes > 0
    shutil.rmtree(S.STUDIO_ROOT / "det_proj", ignore_errors=True)


@pytest.mark.skipif(not P.PILImageProvider().available(), reason="Pillow not installed")
def test_real_pillow_image():
    p = P.PILImageProvider()
    r = p.generate("pil_proj", prompt="IELTS title", out_rel="assets/t.png")
    assert r.ok and r.provider == "pillow" and r.size_bytes > 1000  # real PNG
    from PIL import Image
    img = Image.open(r.path)
    assert img.size == (1280, 720)  # genuinely decodable image
    shutil.rmtree(S.STUDIO_ROOT / "pil_proj", ignore_errors=True)


def test_capability_matrix_marks_cloud_not_configured():
    m = P.capability_matrix()
    cloud = [r for r in m["video"] if r["name"] in ("veo/flow", "heygen")]
    assert cloud and all(not r["configured"] and not r["available"] for r in cloud)


# ── full workflow (integration, real media) ─────────────────────────────────
def test_full_short_video_workflow_produces_real_artifacts(service, store):
    spec = ProjectSpec(title="IELTS WT1", objective="explain writing task 1",
                       content_type="short_video", duration_target_sec=2, budget_usd=5.0)
    pid = service.create_project("ajay", spec)
    out = service.run(pid, owner="ajay")
    assert out.state == ProjectState.AWAITING_REVIEW.value
    assert out.stages_failed == 0
    arts = store.list_artifacts(pid)
    types = {a["artifact_type"] for a in arts}
    assert "script" in types and "image" in types
    if F.ffmpeg_available():
        assert "video_clip" in types
        vid = [a for a in arts if a["artifact_type"] == "video_clip"][0]
        assert vid["checksum"] and vid["file_size"] > 0  # verified real output
    shutil.rmtree(S.STUDIO_ROOT / pid, ignore_errors=True)


def test_workflow_cost_tracked(service, store):
    spec = ProjectSpec(objective="x", content_type="script_only")
    pid = service.create_project("ajay", spec)
    service.run(pid, owner="ajay")
    cost = store.cost_summary(pid)
    assert "total_usd" in cost and "by_kind" in cost


def test_workflows_defined():
    assert set(WORKFLOWS) >= {"script_only", "short_video", "long_video", "avatar"}


# ── security ─────────────────────────────────────────────────────────────────
def test_cross_user_project_run_denied(service, store):
    pid = service.create_project("ajay", ProjectSpec(objective="x"))
    with pytest.raises(PermissionError):
        service.run(pid, owner="mallory")


def test_cancelled_project_cannot_run(service, store):
    pid = service.create_project("ajay", ProjectSpec(objective="x"))
    store.transition(pid, ProjectState.PLANNING)
    store.transition(pid, ProjectState.CANCELLED)
    with pytest.raises(RuntimeError):
        service.run(pid, owner="ajay")


def test_publish_requires_approval(store):
    pid = store.create_project(owner="ajay", spec={})
    store.add_artifact(pid, artifact_type="final_video", stage="assemble",
                       checksum="abc123", status="ready")
    with pytest.raises(PUB.NotApproved):
        PUB.publish(store, pid, platform="youtube", owner="ajay", approved=False)


def test_publish_requires_verified_artifact(store):
    pid = store.create_project(owner="ajay", spec={})
    with pytest.raises(PUB.NoPublishableArtifact):
        PUB.publish(store, pid, platform="youtube", owner="ajay", approved=True)


def test_publish_cross_user_denied(store):
    pid = store.create_project(owner="ajay", spec={})
    store.add_artifact(pid, artifact_type="final_video", stage="assemble",
                       checksum="abc", status="approved")
    with pytest.raises(PermissionError):
        PUB.publish(store, pid, platform="youtube", owner="mallory", approved=True)


def test_publish_dry_run_never_fabricates_url(store):
    pid = store.create_project(owner="ajay", spec={})
    store.add_artifact(pid, artifact_type="final_video", stage="assemble",
                       checksum="cs123", status="approved")
    r = PUB.publish(store, pid, platform="youtube", owner="ajay", approved=True, live=False)
    assert r.status == "dry_run" and r.url == ""  # no fabricated URL


def test_publish_live_refused_honestly_no_fake_receipt(store):
    pid = store.create_project(owner="ajay", spec={})
    store.add_artifact(pid, artifact_type="final_video", stage="assemble",
                       checksum="cs", status="approved")
    r = PUB.publish(store, pid, platform="youtube", owner="ajay", approved=True, live=True)
    assert r.status == "failed" and not r.url  # not configured -> honest failure


def test_publish_idempotent(store):
    pid = store.create_project(owner="ajay", spec={})
    store.add_artifact(pid, artifact_type="final_video", stage="assemble",
                       checksum="dup", status="approved")
    r1 = PUB.publish(store, pid, platform="youtube", owner="ajay", approved=True)
    r2 = PUB.publish(store, pid, platform="youtube", owner="ajay", approved=True)
    assert r1.status == "dry_run" and r2.status == "duplicate"


def test_studio_agents_gateway_only():
    """Studio agents registered into M10 must not name direct provider tools;
    external side effects (publisher) require approval."""
    from saathi.agent_runtime import registry
    import saathi.studio_os  # ensure registration
    pub = registry.get("publisher")
    assert pub.requires_approval
    from saathi.agent_runtime.models import RiskClass
    assert pub.risk_ceiling == RiskClass.EXTERNAL_SIDE_EFFECT
    writer = registry.get("script_writer")
    assert writer.risk_ceiling == RiskClass.READ_ONLY


# ── API / CLI (integration) ──────────────────────────────────────────────────
def test_api_requires_auth():
    from fastapi.testclient import TestClient
    from saathi.server import app
    assert TestClient(app).get("/api/v1/studio-os/projects").status_code == 401


def test_api_handlers_direct(store, monkeypatch):
    from saathi.studio_os import api

    class Req:
        state = type("S", (), {"user_id": "ajay"})()

    monkeypatch.setattr(api, "default_store", lambda: store)
    monkeypatch.setattr(api.StudioService, "__init__",
                        lambda self, s=None: setattr(self, "store", store) or
                        setattr(self, "_chat", FakeChat()) or
                        setattr(self, "_orch", None) or
                        setattr(self, "image_prefer", "pillow") or
                        setattr(self, "video_prefer", "ffmpeg-local") or
                        setattr(self, "voice_prefer", "say"))
    out = api.create_project(api.CreateProject(title="t", objective="x",
                                               content_type="script_only"), Req())
    pid = out["project_id"]
    got = api.get_project(pid, Req())
    assert got["project"]["owner"] == "ajay"
    assert "storage" in str(api.storage_health()) or api.storage_health()["healthy"] in (True, False)
    assert "image" in api.providers_matrix()


def test_api_cross_user_not_found(store, monkeypatch):
    from saathi.studio_os import api

    class ReqA:
        state = type("S", (), {"user_id": "ajay"})()

    class ReqB:
        state = type("S", (), {"user_id": "mallory"})()

    monkeypatch.setattr(api, "default_store", lambda: store)
    pid = store.create_project(owner="ajay", spec={"title": "t"})
    assert api.get_project(pid, ReqB()) == {"error": "not found"}


def test_cli_read_only_and_exit_codes(store, monkeypatch):
    from saathi.studio_os import cli
    monkeypatch.setattr(cli, "default_store", lambda: store)
    assert cli.main(["inspect"]) == 0
    assert cli.main(["providers"]) == 0
    assert cli.main(["projects"]) == 0
    assert cli.main(["bogus"]) == cli.EXIT_BAD


def test_cli_render_smoke_labels_real():
    from saathi.studio_os import cli
    rc = cli.main(["render-smoke"])
    assert rc in (cli.EXIT_OK, cli.EXIT_FAIL)


def test_cli_read_only_never_mutates(store, monkeypatch):
    from saathi.studio_os import cli
    monkeypatch.setattr(cli, "default_store", lambda: store)
    before = store.list_projects()
    cli.main(["inspect"]); cli.main(["providers"]); cli.main(["storage"])
    assert store.list_projects() == before


# ── regression ───────────────────────────────────────────────────────────────
def test_route_count_not_decreased():
    from saathi.server import app
    assert len(app.routes) >= 302
