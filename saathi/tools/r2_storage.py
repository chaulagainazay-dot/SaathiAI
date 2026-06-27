"""
r2_storage.py — Firebase Storage upload helper.
All video, thumbnail, and reel files go here instead of local disk.
Falls back to local path if Firebase Storage is not configured.

Same public interface as the original R2 version so no callers need changes.
"""
import os
from pathlib import Path

# Firebase Storage bucket (default: <project_id>.appspot.com)
_FB_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "")


def is_configured() -> bool:
    try:
        _bucket()
        return True
    except Exception:
        return False


def _bucket():
    """Return a firebase_admin.storage bucket handle, initialising the app if needed."""
    import firebase_admin
    from firebase_admin import credentials, storage

    bucket_name = _FB_BUCKET or _default_bucket()
    if not bucket_name:
        raise RuntimeError("FIREBASE_STORAGE_BUCKET not set and project_id unknown")

    # Reuse existing app if already initialised
    try:
        app = firebase_admin.get_app()
    except ValueError:
        sa_key = os.getenv("FIREBASE_SA_KEY", "")
        if not sa_key:
            raise RuntimeError("FIREBASE_SA_KEY not set")
        cred = credentials.Certificate(sa_key)
        app = firebase_admin.initialize_app(cred, {"storageBucket": bucket_name})

    return storage.bucket(bucket_name, app=app)


def _default_bucket() -> str:
    """Read project_id from the service-account JSON and derive bucket name."""
    sa_key = os.getenv("FIREBASE_SA_KEY", "")
    if not sa_key:
        return ""
    try:
        import json
        with open(sa_key) as f:
            data = json.load(f)
        pid = data.get("project_id", "")
        return f"{pid}.appspot.com" if pid else ""
    except Exception:
        return ""


def _public_url(blob) -> str:
    """Return a long-lived signed URL (1 year) for a GCS blob."""
    import datetime
    return blob.generate_signed_url(
        expiration=datetime.timedelta(days=365),
        method="GET",
        version="v4",
    )


def upload_file(local_path: "str | Path", key: str, content_type: str = "video/mp4") -> str:
    """Upload a local file to Firebase Storage. Returns a signed public URL."""
    try:
        bucket = _bucket()
    except Exception:
        return str(local_path)   # fallback: local path
    blob = bucket.blob(key)
    blob.upload_from_filename(str(local_path), content_type=content_type)
    return _public_url(blob)


def upload_bytes(data: bytes, key: str, content_type: str = "video/mp4") -> str:
    """Upload bytes directly to Firebase Storage. Returns a signed public URL."""
    try:
        bucket = _bucket()
    except Exception:
        return key
    blob = bucket.blob(key)
    blob.upload_from_string(data, content_type=content_type)
    return _public_url(blob)


def download_url_to_r2(url: str, key: str, content_type: str = "video/mp4") -> str:
    """Download a URL and upload it to Firebase Storage. Never touches disk."""
    try:
        bucket = _bucket()
    except Exception:
        return url
    import httpx
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        data = r.read()
    blob = bucket.blob(key)
    blob.upload_from_string(data, content_type=content_type)
    return _public_url(blob)


def list_keys(prefix: str = "") -> list:
    try:
        return [b.name for b in _bucket().list_blobs(prefix=prefix)]
    except Exception:
        return []


def delete_key(key: str):
    try:
        _bucket().blob(key).delete()
    except Exception:
        pass


def cleanup_old_local_dirs():
    """Delete local video/reel/thumbnail directories to free disk."""
    import shutil
    from .. import config
    for dirname in ("videos_output", "reels_output", "thumbnails", "hyperframes_projects"):
        d = config.ROOT / dirname
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
