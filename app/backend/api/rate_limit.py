"""Rate limiting thread-safe por IP e usuário para endpoints custosos."""
from __future__ import annotations

import threading
import time
from collections import deque

from flask import current_app, g, jsonify, request

_LOCK = threading.Lock()
_BUCKETS: dict[str, deque[float]] = {}
_MAX_KEYS = 10_000


def reset_rate_limits() -> None:
    """Limpa todos os contadores de rate limit (uso em testes)."""
    with _LOCK:
        _BUCKETS.clear()


def _client_ip() -> str:
    return (request.remote_addr or "unknown").strip()[:64]


def _consume(key: str, limit: int, window_seconds: int, now: float) -> tuple[bool, int]:
    """Registra tentativa em janela deslizante e retorna (permitido, retry_after_s)."""
    cutoff = now - window_seconds
    with _LOCK:
        dq = _BUCKETS.get(key)
        if dq is None:
            if len(_BUCKETS) >= _MAX_KEYS:
                # Evicção simples do registro mais antigo para impedir crescimento ilimitado
                oldest_key = next(iter(_BUCKETS))
                _BUCKETS.pop(oldest_key, None)
            dq = deque()
            _BUCKETS[key] = dq

        while dq and dq[0] <= cutoff:
            dq.popleft()

        if len(dq) >= limit:
            retry_after = max(1, int(dq[0] + window_seconds - now) + 1)
            return False, retry_after

        dq.append(now)
        return True, 0


def check_rate_limit(
    bucket: str,
    *,
    auth_limit: int,
    guest_limit: int,
    window_seconds: int = 60,
    ip_limit: int | None = None,
):
    """Retorna resposta 429 caso o limite por usuário/guest ou IP tenha sido excedido, senão None."""
    if current_app.config.get("TESTING") and not current_app.config.get("RATE_LIMIT_ENABLED"):
        return None

    user_id = str(getattr(g, "user_id", "") or "").strip()
    is_guest = not user_id or user_id.startswith("guest:")
    limit = guest_limit if is_guest else auth_limit
    now = time.monotonic()

    if user_id:
        ok_user, retry_u = _consume(f"u:{bucket}:{user_id}", limit, window_seconds, now)
        if not ok_user:
            resp = jsonify({
                "error": "Muitas requisições em pouco tempo. Aguarde antes de tentar novamente.",
                "code": "RATE_LIMIT_EXCEEDED",
            })
            resp.status_code = 429
            resp.headers["Retry-After"] = str(retry_u)
            return resp

    effective_ip_limit = ip_limit if ip_limit is not None else max(guest_limit * 2, limit)
    ok_ip, retry_ip = _consume(f"ip:{bucket}:{_client_ip()}", effective_ip_limit, window_seconds, now)
    if not ok_ip:
        resp = jsonify({
            "error": "Limite de requisições por IP atingido. Tente novamente em instantes.",
            "code": "RATE_LIMIT_EXCEEDED",
        })
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_ip)
        return resp

    return None
