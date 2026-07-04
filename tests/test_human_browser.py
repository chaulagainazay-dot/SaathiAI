"""Human Browser Driver — signed jobs, VM→agent round-trip, tier escalation."""
import threading
import time

import pytest

from saathi.infrastructure.human_browser import (
    HumanJob, sign, verify, NonceStore, BadSignature, JobExpired, JobReplayed, JobError,
    InMemoryQueue, Envelope, HumanBrowser, HumanBrowserProxy, MacAgent, ProfileStore,
)

SECRET = "shared-mac-vm-secret"


# ── signing / security core ──────────────────────────────────────────────────
def test_valid_signature_verifies():
    job = HumanJob("open", {"url": "https://youtube.com"}, profile="ajay/youtube")
    verify(job, sign(job, SECRET), SECRET)          # no raise


def test_tampered_payload_fails_signature():
    job = HumanJob("open", {"url": "https://youtube.com"})
    sig = sign(job, SECRET)
    job.payload["url"] = "https://evil.com"         # tamper after signing
    with pytest.raises(BadSignature):
        verify(job, sig, SECRET)


def test_wrong_secret_fails():
    job = HumanJob("screenshot")
    with pytest.raises(BadSignature):
        verify(job, sign(job, SECRET), "attacker-secret")


def test_expired_job_rejected():
    job = HumanJob("open", {"url": "x"}, ttl_seconds=-1)   # already expired
    with pytest.raises(JobExpired):
        verify(job, sign(job, SECRET), SECRET)


def test_replayed_nonce_rejected():
    job = HumanJob("open", {"url": "x"})
    sig = sign(job, SECRET)
    nonces = NonceStore()
    verify(job, sig, SECRET, nonces=nonces)          # first time ok
    with pytest.raises(JobReplayed):
        verify(job, sig, SECRET, nonces=nonces)      # replay blocked


# ── end-to-end: VM proxy → queue → Mac Agent → backend → result ──────────────
class FakeBackend(HumanBrowser):
    def available(self): return True
    def execute(self, capability, *, profile="", **payload):
        return {"echo": capability, "profile": profile, **payload}


def test_round_trip_vm_to_agent():
    q = InMemoryQueue()
    proxy = HumanBrowserProxy(q, secret=SECRET, timeout=5)
    agent = MacAgent(q, FakeBackend(), secret=SECRET)

    out = {}
    def call():
        out["r"] = proxy.execute("publish_video", profile="ajay/youtube", path="clip.mp4")
    t = threading.Thread(target=call); t.start()
    time.sleep(0.05)
    assert agent.run_once() is not None      # agent claims + verifies + runs
    t.join(timeout=5)
    assert out["r"]["echo"] == "publish_video" and out["r"]["path"] == "clip.mp4"


def test_agent_rejects_forged_job():
    q = InMemoryQueue()
    agent = MacAgent(q, FakeBackend(), secret=SECRET)
    job = HumanJob("open", {"url": "x"})
    env = Envelope(job=job.to_dict(), signature=sign(job, SECRET))
    env.job["payload"] = {"url": "evil"}     # tamper the enqueued envelope
    q.enqueue(env)
    res = agent.run_once()
    assert not res.ok and "rejected" in res.error


def test_agent_rejects_replay():
    q = InMemoryQueue()
    agent = MacAgent(q, FakeBackend(), secret=SECRET)
    job = HumanJob("screenshot")
    env = Envelope(job=job.to_dict(), signature=sign(job, SECRET))
    q.enqueue(env); q.enqueue(env)           # same job twice
    assert agent.run_once().ok is True
    assert agent.run_once().ok is False      # replay rejected


def test_proxy_unavailable_without_secret():
    assert HumanBrowserProxy(InMemoryQueue(), secret="").available() is False
    with pytest.raises(JobError):
        HumanBrowserProxy(InMemoryQueue(), secret="").execute("open", url="x")


# ── profiles ─────────────────────────────────────────────────────────────────
def test_profile_paths_and_traversal(tmp_path):
    ps = ProfileStore(root=str(tmp_path))
    ps.ensure("ajay/youtube"); ps.ensure("ajay/instagram")
    assert set(ps.list()) == {"ajay/youtube", "ajay/instagram"}
    with pytest.raises(ValueError):
        ps.path("ajay/../../etc")


# ── HTTP transport (Mac Agent ↔ VM endpoints) ────────────────────────────────
def test_http_queue_client_claim_and_complete():
    import httpx
    from saathi.infrastructure.human_browser import HttpQueueClient, JobResult
    completed = {}
    def handler(req):
        if req.url.path.endswith("/human/claim"):
            job = HumanJob("screenshot", profile="ajay/youtube")
            return httpx.Response(200, json={"envelope": {"job": job.to_dict(),
                                                          "signature": sign(job, SECRET)}})
        if req.url.path.endswith("/human/complete"):
            import json; completed.update(json.loads(req.content)); return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)
    cli = HttpQueueClient("https://vm.test", "tok", transport=httpx.MockTransport(handler))
    env = cli.claim()
    assert env.job["capability"] == "screenshot"
    cli.complete(JobResult(job_id="j1", ok=True, data={"done": 1}))
    assert completed["job_id"] == "j1" and completed["ok"] is True


def test_http_queue_client_claim_empty_204():
    import httpx
    from saathi.infrastructure.human_browser import HttpQueueClient
    cli = HttpQueueClient("https://vm.test", "tok",
                          transport=httpx.MockTransport(lambda r: httpx.Response(204)))
    assert cli.claim() is None


# ── browser-tier escalation to Human ─────────────────────────────────────────
def test_human_tier_serves_as_top_escalation():
    from saathi.browser import BrowserService, Tier
    from saathi.browser.types import Page, Capabilities
    from saathi.browser.base import BrowserTier
    from saathi.infrastructure.human_browser.browser_tier import HumanTier

    class BlockedHttp(BrowserTier):
        name, tier = "http", Tier.HTTP
        def capabilities(self): return Capabilities(fetch=True)
        def available(self): return True
        def open(self, url, *, timeout=30, session=None):
            return Page(url=url, status=403, blocked=True, tier=Tier.HTTP)

    class FakeProxy:
        def available(self): return True
        def execute(self, capability, *, profile="", **p): return {"url": p.get("url"), "title": "Home"}

    svc = BrowserService(tiers=[BlockedHttp(), HumanTier(FakeProxy())])
    page = svc.open("https://youtube.com")           # HTTP blocked → escalate to Human
    assert page.ok and page.tier == Tier.HUMAN and page.title == "Home"
