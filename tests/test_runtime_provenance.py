"""Runtime provenance: prove which checkout answered, leak nothing else.

Two properties are load-bearing and are asserted separately:

  1. The provenance describes *this* checkout. If it named another worktree the
     certificate it feeds would be worthless, which is the exact failure the
     repository-root import guard exists to prevent on the test side.
  2. Filesystem paths appear only outside production-class environments. Build
     identity (SHA, branch, repository name) is not secret and is always
     present; absolute paths describe the host and are not.
"""
from __future__ import annotations

import pathlib
import subprocess

import pytest
from fastapi.testclient import TestClient

from saathi import provenance
from saathi.server import app

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

PROD_ENVIRONMENTS = ["production", "prod", "staging", "canary"]
LOCAL_ENVIRONMENTS = ["development", "test", "local", "ci"]


@pytest.fixture(autouse=True)
def _clear_cache():
    provenance.reset_cache()
    yield
    provenance.reset_cache()


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestProvenanceDescribesThisCheckout:
    def test_repo_root_is_this_checkout(self):
        assert provenance.REPO_ROOT == REPO_ROOT

    def test_package_path_is_inside_this_checkout(self):
        assert provenance.PACKAGE_PATH.parent == REPO_ROOT

    def test_sha_matches_git_head(self):
        head = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if head.returncode != 0:  # no git available — env override path is tested below
            pytest.skip("not a git checkout")
        payload = provenance.runtime_provenance("development")
        assert payload["backendSha"] == head.stdout.strip()
        assert payload["shaSource"] == "git"

    def test_worktree_path_is_this_checkout(self):
        payload = provenance.runtime_provenance("development")
        assert payload["worktreePath"] == str(REPO_ROOT)
        assert payload["packagePath"] == str(REPO_ROOT / "saathi")

    def test_repository_name_is_reported(self):
        payload = provenance.runtime_provenance("development")
        assert payload["repository"] == REPO_ROOT.name


class TestBuildShaOverride:
    """Deployments built from an archive have no .git; the env var answers."""

    def test_env_sha_wins(self, monkeypatch):
        monkeypatch.setenv("SAATHI_BUILD_SHA", "deadbeef" * 5)
        monkeypatch.setenv("SAATHI_BUILD_REF", "release/x")
        payload = provenance.runtime_provenance("development")
        assert payload["backendSha"] == "deadbeef" * 5
        assert payload["backendBranch"] == "release/x"
        assert payload["shaSource"] == "env"


class TestProductionHidesHostPaths:
    @pytest.mark.parametrize("env", PROD_ENVIRONMENTS)
    def test_no_filesystem_paths(self, env):
        payload = provenance.runtime_provenance(env)
        assert payload["worktreePath"] is None
        assert payload["packagePath"] is None
        assert not provenance.exposes_local_paths(env)

    @pytest.mark.parametrize("env", PROD_ENVIRONMENTS)
    def test_build_identity_still_present(self, env):
        payload = provenance.runtime_provenance(env)
        assert payload["backendSha"]
        assert payload["repository"] == REPO_ROOT.name

    @pytest.mark.parametrize("env", PROD_ENVIRONMENTS)
    def test_home_directory_never_appears_anywhere_in_payload(self, env):
        payload = provenance.runtime_provenance(env)
        blob = repr(payload)
        assert str(REPO_ROOT) not in blob
        assert str(pathlib.Path.home()) not in blob

    @pytest.mark.parametrize("env", LOCAL_ENVIRONMENTS)
    def test_local_environments_do_expose_paths(self, env):
        payload = provenance.runtime_provenance(env)
        assert payload["worktreePath"] == str(REPO_ROOT)
        assert provenance.exposes_local_paths(env)


class TestProvenanceCarriesNoSecrets:
    SECRET_ENV_NAMES = [
        "BAADAR_PASSWORD",
        "BAADAR_PASSWORD_HASH",
        "SAATHI_TOKEN",
        "BAADAR_API_KEY",
    ]

    def test_payload_keys_are_the_declared_set(self):
        payload = provenance.runtime_provenance("development")
        assert set(payload) == {
            "schema",
            "environment",
            "repository",
            "backendSha",
            "backendBranch",
            "backendDirty",
            "shaSource",
            "worktreePath",
            "packagePath",
        }

    def test_no_credential_material_is_reflected(self, monkeypatch):
        for name in self.SECRET_ENV_NAMES:
            monkeypatch.setenv(name, f"canary-{name.lower()}")
        provenance.reset_cache()
        blob = repr(provenance.runtime_provenance("development"))
        for name in self.SECRET_ENV_NAMES:
            assert f"canary-{name.lower()}" not in blob


class TestHealthSurfaceExposesProvenance:
    def test_platform_provenance_endpoint(self, client):
        r = client.get("/api/v1/platform/provenance")
        assert r.status_code == 200
        body = r.json()
        assert body["schema"] == provenance.SCHEMA
        assert body["backendSha"]

    def test_platform_health_carries_provenance(self, client):
        r = client.get("/api/v1/platform/health")
        assert r.status_code == 200
        body = r.json()
        assert "provenance" in body, "health must identify the code answering it"
        assert body["provenance"]["backendSha"]

    def test_provenance_is_readable_without_authentication(self, client):
        """A certification harness must be able to identify the runtime before
        it has a session; that is the point. It stays non-secret in return."""
        r = client.get("/api/v1/platform/provenance")
        assert r.status_code == 200
