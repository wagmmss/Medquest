"""Serviço de autenticação OAuth2 e proxy HTTP 206 Range para aulas no Google Drive."""
from __future__ import annotations

import configparser
import json
import os
import threading
import time

import requests
from flask import Response, stream_with_context

from ..auth import create_lesson_stream_token

STREAM_CHUNK_BYTES = 256 * 1024

_DRIVE_TOKEN_LOCK = threading.Lock()
_DRIVE_TOKEN_CACHE: dict[str, object] = {
    "access_token": None,
    "expires_at": 0.0,
}


def resolve_drive_oauth_credentials() -> tuple[str, str, str] | None:
    """Resolve credenciais OAuth do Google Drive via variáveis de ambiente ou rclone.conf local."""
    env_cid = (os.environ.get("GOOGLE_DRIVE_CLIENT_ID") or "").strip()
    env_csec = (os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET") or "").strip()
    env_rtok = (os.environ.get("GOOGLE_DRIVE_REFRESH_TOKEN") or "").strip()
    if env_cid and env_csec and env_rtok:
        return env_cid, env_csec, env_rtok

    if os.environ.get("RENDER"):
        return None

    rclone_path = os.path.expanduser("~/.config/rclone/rclone.conf")
    if not os.path.exists(rclone_path):
        return None
    try:
        cfg = configparser.ConfigParser()
        cfg.read(rclone_path, encoding="utf-8")
        if "Drive" not in cfg:
            return None
        sec = cfg["Drive"]
        cid = (sec.get("client_id") or "").strip()
        csec = (sec.get("client_secret") or "").strip()
        tok_raw = sec.get("token") or ""
        tok_obj = json.loads(tok_raw) if tok_raw else {}
        rtok = (tok_obj.get("refresh_token") or "").strip()
        if cid and csec and rtok:
            return cid, csec, rtok
    except Exception:
        return None
    return None


def get_drive_access_token(
    force_refresh: bool = False, *, post_fn=None, creds_resolver=None
) -> str | None:
    """Obtém access_token válido para leitura (alt=media) na Google Drive API v3."""
    with _DRIVE_TOKEN_LOCK:
        now = time.time()
        cached_token = _DRIVE_TOKEN_CACHE.get("access_token")
        expires_at = float(_DRIVE_TOKEN_CACHE.get("expires_at") or 0.0)
        if not force_refresh and isinstance(cached_token, str) and cached_token and now < expires_at - 90:
            return cached_token

        creds = (creds_resolver or resolve_drive_oauth_credentials)()
        if not creds:
            return None
        client_id, client_secret, refresh_token = creds
        try:
            resp = (post_fn or requests.post)(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            access_token = (data.get("access_token") or "").strip()
            expires_in = int(data.get("expires_in") or 3500)
            if not access_token:
                return None
            _DRIVE_TOKEN_CACHE["access_token"] = access_token
            _DRIVE_TOKEN_CACHE["expires_at"] = now + max(120, expires_in)
            return access_token
        except Exception:
            return None


def build_stream_url(
    lesson_id: int, user_id: str, user_email: str, *, creds_resolver=None
) -> str | None:
    """Constrói URL assinada para streaming direto HTML5 <video> (720p/1080p original)."""
    if not (creds_resolver or resolve_drive_oauth_credentials)():
        return None
    st = create_lesson_stream_token(
        lesson_id=lesson_id,
        user_id=str(user_id or ""),
        user_email=str(user_email or ""),
    )
    if not st:
        return None
    base = (
        os.environ.get("BACKEND_PUBLIC_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or ("https://medquest-188y.onrender.com" if os.environ.get("RENDER") else "")
    ).rstrip("/")
    return f"{base}/api/lessons/{lesson_id}/stream?st={st}"


def open_drive_video_stream(
    drive_file_id: str,
    range_header: str | None,
    *,
    token_loader=None,
    http_get=None,
    chunk_bytes: int = STREAM_CHUNK_BYTES,
) -> tuple[Response | dict, int]:
    """Abre stream upstream no Google Drive e constrói Response Flask 200/206."""
    load_token = token_loader or get_drive_access_token
    do_get = http_get or requests.get

    access_token = load_token(force_refresh=False)
    if not access_token:
        return {"error": "Stream direto do Google Drive não configurado."}, 503

    drive_url = f"https://www.googleapis.com/drive/v3/files/{drive_file_id}?alt=media"

    def _open_upstream(token: str):
        req_headers = {"Authorization": f"Bearer {token}"}
        if range_header:
            req_headers["Range"] = range_header
        return do_get(drive_url, headers=req_headers, stream=True, timeout=(10, 60))

    try:
        upstream = _open_upstream(access_token)
        if upstream.status_code == 401:
            upstream.close()
            refreshed = load_token(force_refresh=True)
            if not refreshed:
                return {"error": "Falha ao renovar autorização do Google Drive."}, 503
            upstream = _open_upstream(refreshed)
    except Exception:
        return {"error": "Erro de conexão com o Google Drive."}, 502

    if upstream.status_code not in (200, 206):
        status_code = upstream.status_code
        upstream.close()
        return {"error": f"Google Drive respondeu HTTP {status_code}."}, 502

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=chunk_bytes):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    resp = Response(stream_with_context(generate()), status=upstream.status_code)
    resp.headers["Content-Type"] = upstream.headers.get("Content-Type") or "video/mp4"
    resp.headers["Accept-Ranges"] = "bytes"
    resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    resp.headers["Cache-Control"] = "private, no-store"
    for hdr in ("Content-Length", "Content-Range"):
        val = upstream.headers.get(hdr)
        if val:
            resp.headers[hdr] = val
    return resp, upstream.status_code
