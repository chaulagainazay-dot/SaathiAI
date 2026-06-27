"""
r2_storage.py — Cloudflare R2 upload/download helper (S3-compatible).
All video, thumbnail, and reel files go here instead of local disk.
"""
import os
from pathlib import Path
from typing import Optional

R2_ENDPOINT = os.getenv("R2_ENDPOINT_URL", "")          # https://<account_id>.r2.cloudflarestorage.com
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.getenv("R2_BUCKET", "baadar-videos")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "")          # optional CDN URL prefix

def _client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
    )

def is_configured() -> bool:
    return bool(R2_ENDPOINT and R2_ACCESS_KEY and R2_SECRET_KEY)

def upload_file(local_path: "str | Path", key: str, content_type: str = "video/mp4") -> str:
    """Upload a local file to R2. Returns the public URL."""
    if not is_configured():
        return str(local_path)   # fallback: return local path if R2 not set up
    _client().upload_file(
        str(local_path), R2_BUCKET, key,
        ExtraArgs={"ContentType": content_type}
    )
    return _public_url(key)

def upload_bytes(data: bytes, key: str, content_type: str = "video/mp4") -> str:
    """Upload bytes directly to R2. Returns the public URL."""
    if not is_configured():
        return key
    import io
    _client().upload_fileobj(io.BytesIO(data), R2_BUCKET, key,
        ExtraArgs={"ContentType": content_type})
    return _public_url(key)

def download_url_to_r2(url: str, key: str, content_type: str = "video/mp4") -> str:
    """Download a URL and stream it straight to R2. Returns public URL. Never touches disk."""
    if not is_configured():
        return url
    import httpx
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        import io
        buf = io.BytesIO(r.read())
    buf.seek(0)
    _client().upload_fileobj(buf, R2_BUCKET, key,
        ExtraArgs={"ContentType": content_type})
    return _public_url(key)

def _public_url(key: str) -> str:
    if R2_PUBLIC_URL:
        return f"{R2_PUBLIC_URL.rstrip('/')}/{key}"
    return f"{R2_ENDPOINT}/{R2_BUCKET}/{key}"

def list_keys(prefix: str = "") -> list:
    if not is_configured():
        return []
    resp = _client().list_objects_v2(Bucket=R2_BUCKET, Prefix=prefix)
    return [o["Key"] for o in resp.get("Contents", [])]

def delete_key(key: str):
    if is_configured():
        _client().delete_object(Bucket=R2_BUCKET, Key=key)

def cleanup_old_local_dirs():
    """Delete local video/reel/thumbnail directories to free disk."""
    import shutil
    from .. import config
    for dirname in ("videos_output", "reels_output", "thumbnails", "hyperframes_projects"):
        d = config.ROOT / dirname
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
