import functools
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from flask import Response, g, jsonify, request

from .auth import is_valid_uuid_v4
from .db import db_transaction, get_db

LEASE_DURATION_SECONDS = 30.0
logger = logging.getLogger(__name__)


class LostLeaseError(RuntimeError):
    """Raised when an obsolete worker tries to commit protected effects."""


def _owns_lease(db, user_id: str, key: str, lease_token: str, status: str) -> bool:
    cursor = db.execute(
        """SELECT 1 AS owned FROM idempotency_keys
           WHERE user_id = ? AND key = ? AND lease_owner_token = ? AND status = ?""",
        (user_id, key, lease_token, status),
    )
    rows = cursor.fetchall()
    row = rows[0] if rows else None
    cursor.close()
    return row is not None


def _database_unavailable():
    return jsonify({"error": "Idempotency storage is temporarily unavailable"}), 503


def reserve_idempotency(db, user_id: str, path: str, method: str, raw_payload: bytes):
    """
    Tenta reservar atomicamente a chave de idempotência antes de qualquer efeito.
    
    Retorna uma tupla (cached_response, error_tuple, lease_token):
      - Se cached_response não for None: chave já concluída com mesmo payload -> retornar resposta.
      - Se error_tuple não for None: conflito (409) ou erro de validação (400) -> retornar erro.
      - Se lease_token não for None: requisição reservou a chave com sucesso -> prosseguir e chamar complete_idempotency ao final.
      - Se todos forem None: requisição não enviou X-Idempotency-Key -> executar sem idempotência.
    """
    key = request.headers.get("X-Idempotency-Key")
    if not key:
        return None, None, None

    if not is_valid_uuid_v4(key):
        return None, (jsonify({"error": "Invalid X-Idempotency-Key: must be a canonical UUID v4"}), 400), None

    normalized_key = key.lower()
    payload_hash = hashlib.sha256(raw_payload).hexdigest()
    now_ts = time.time()
    lease_expires_at = now_ts + LEASE_DURATION_SECONDS
    created_at = datetime.now(timezone.utc).isoformat()
    lease_owner_token = str(uuid.uuid4())

    # INSERT OR IGNORE has the same conflict semantics on SQLite and libSQL.
    try:
        with db_transaction(db, immediate=True):
            db.execute(
                """INSERT OR IGNORE INTO idempotency_keys (user_id, key, method, path, payload_hash, status, status_code, response_body, lease_expires_at, lease_owner_token, created_at)
                   VALUES (?, ?, ?, ?, ?, 'processing', 0, '', ?, ?, ?)""",
                (user_id, normalized_key, method, path, payload_hash, lease_expires_at, lease_owner_token, created_at)
            )
            reserved = _owns_lease(db, user_id, normalized_key, lease_owner_token, "processing")
        if reserved:
            return None, None, lease_owner_token
    except Exception:
        logger.exception("Unable to reserve idempotency key")
        return None, _database_unavailable(), None

    # 2. Investigar o registro existente
    cursor = db.execute(
        "SELECT status, method, path, payload_hash, status_code, response_body, lease_expires_at FROM idempotency_keys WHERE user_id = ? AND key = ?",
        (user_id, normalized_key)
    )
    rows = cursor.fetchall()
    existing = rows[0] if rows else None
    cursor.close()

    if not existing:
        return None, (jsonify({"error": "Idempotency state changed concurrently; retry the request", "code": "idempotency_processing"}), 409, {"Retry-After": "2"}), None

    # Verificar divergência de rota, método ou payload
    if (existing["payload_hash"] != payload_hash or 
        existing["path"] != path or 
        existing["method"] != method):
        return None, (jsonify({"error": "Conflict: X-Idempotency-Key already used with different payload or route"}), 409), None

    # Se já foi concluída com sucesso
    if existing["status"] == "completed" and existing["response_body"] is not None:
        return Response(existing["response_body"], status=existing["status_code"] or 200, mimetype="application/json"), None, None

    # Se está em 'processing' ou 'failed'
    if existing["status"] in ("processing", "failed"):
        current_lease = existing["lease_expires_at"] or 0
        if existing["status"] == "failed" or now_ts > current_lease:
            # Lease expirado ou status failed -> tentativa de recuperação atômica
            try:
                with db_transaction(db, immediate=True):
                    db.execute(
                        """UPDATE idempotency_keys 
                           SET status = 'processing', lease_expires_at = ?, payload_hash = ?, method = ?, path = ?, lease_owner_token = ?
                           WHERE user_id = ? AND key = ?
                             AND (status = 'failed' OR (status = 'processing' AND lease_expires_at <= ?))""",
                        (lease_expires_at, payload_hash, method, path, lease_owner_token, user_id, normalized_key, now_ts)
                    )
                    took_over = _owns_lease(db, user_id, normalized_key, lease_owner_token, "processing")
                if took_over:
                    return None, None, lease_owner_token
            except Exception:
                logger.exception("Unable to take over an expired idempotency lease")
                return None, _database_unavailable(), None

        # Aguardar brevemente (polling de até 1.5s) caso a requisição concorrente esteja finalizando
        for _ in range(15):
            time.sleep(0.1)
            cursor = db.execute(
                "SELECT status, status_code, response_body FROM idempotency_keys WHERE user_id = ? AND key = ?",
                (user_id, normalized_key)
            )
            rows = cursor.fetchall()
            row = rows[0] if rows else None
            cursor.close()
            if row and row["status"] == "completed" and row["response_body"] is not None:
                return Response(row["response_body"], status=row["status_code"] or 200, mimetype="application/json"), None, None

        return None, (jsonify({"error": "Conflict: Operation with this idempotency key is currently processing", "code": "idempotency_processing"}), 409, {"Retry-After": "2"}), None

    return None, (jsonify({"error": "Invalid idempotency state"}), 409), None


def complete_idempotency(db, user_id: str, status_code: int, response_data: dict | list, lease_token: str):
    """
    Marca a chave de idempotência como completed gravando atomicamente a resposta.
    """
    key = request.headers.get("X-Idempotency-Key")
    if not key or not is_valid_uuid_v4(key) or not lease_token:
        return

    normalized_key = key.lower()
    response_body = json.dumps(response_data)

    cursor = db.execute(
        """UPDATE idempotency_keys
           SET status = 'completed', status_code = ?, response_body = ?, lease_expires_at = 0
           WHERE user_id = ? AND key = ? AND lease_owner_token = ? AND status = 'processing'""",
        (status_code, response_body, user_id, normalized_key, lease_token)
    )
    cursor.close()

    if not _owns_lease(db, user_id, normalized_key, lease_token, "completed"):
        raise LostLeaseError("Idempotency lease was lost before completion")


def fail_idempotency(db, user_id: str, lease_token: str):
    """
    Libera a chave em caso de falha não-recuperável ou erro interno do servidor.
    """
    key = request.headers.get("X-Idempotency-Key")
    if not key or not is_valid_uuid_v4(key) or not lease_token:
        return False

    with db_transaction(db, immediate=True):
        cursor = db.execute(
            """UPDATE idempotency_keys
               SET status = 'failed', lease_expires_at = 0
               WHERE user_id = ? AND key = ? AND lease_owner_token = ? AND status = 'processing'""",
            (user_id, key.lower(), lease_token)
        )
        cursor.close()
        changed = _owns_lease(db, user_id, key.lower(), lease_token, "failed")
    return changed


def cleanup_idempotency_keys(db, max_age_days: int = 7):
    """
    Limpa chaves antigas concluídas ou falhas para liberar espaço.
    """
    now = datetime.now(timezone.utc)
    cutoff_completed = (now - timedelta(days=max_age_days)).isoformat()
    cutoff_failed = (now - timedelta(days=1)).isoformat()
    try:
        with db_transaction(db, immediate=True):
            db.execute(
                """DELETE FROM idempotency_keys
                   WHERE (status = 'completed' AND julianday(created_at) < julianday(?))
                      OR (status = 'failed' AND julianday(created_at) < julianday(?))""",
                (cutoff_completed, cutoff_failed),
            )
        return
    except Exception:
        logger.exception("Unable to clean old idempotency keys")
        raise


class IdempotencyLease:
    """Reserva ativa de idempotência vinculada à requisição HTTP atual."""

    def __init__(self, db, user_id: str, token: str | None) -> None:
        self.db = db
        self.user_id = user_id
        self.token = token
        self.settled = False

    def complete(self, status_code: int, response_data: dict | list) -> None:
        """Persiste o resultado na mesma transação ativa quando há chave reservada."""
        if not self.token or self.settled:
            return
        complete_idempotency(self.db, self.user_id, status_code, response_data, self.token)
        self.settled = True

    def fail(self) -> None:
        """Marca a chave como falha em erros ou retornos não-2xx."""
        if not self.token or self.settled:
            return
        self.settled = True
        fail_idempotency(self.db, self.user_id, self.token)


def complete_active_lease(status_code: int, response_data: dict | list) -> None:
    """Conclui o lease ativo da requisição (`g.idempotency_lease`), se existir."""
    lease = getattr(g, "idempotency_lease", None)
    if lease is not None:
        lease.complete(status_code, response_data)


def idempotent(user_resolver=None):
    """Decorator que garante reserva/reaproveitamento e limpeza de `X-Idempotency-Key`.

    Rotas transacionais podem chamar `complete_active_lease(status, payload)` dentro de seu
    próprio `db_transaction(...)` para manter atomicidade com a escrita de domínio. Caso a
    rota retorne 2xx sem chamar explicitamente, o decorator conclui ao final; em retornos
    >=400 ou exceções, marca o lease como `failed`.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            db = get_db()
            uid = user_resolver() if user_resolver else g.user_id
            raw_payload = request.get_data()

            cached_resp, err_resp, lease_token = reserve_idempotency(
                db, uid, request.path, request.method, raw_payload
            )
            if cached_resp is not None:
                return cached_resp
            if err_resp is not None:
                return err_resp

            lease = IdempotencyLease(db=db, user_id=uid, token=lease_token)
            prev_lease = getattr(g, "idempotency_lease", None)
            g.idempotency_lease = lease
            try:
                res = fn(*args, **kwargs)
            except Exception:
                lease.fail()
                raise
            finally:
                g.idempotency_lease = prev_lease

            if lease.token and not lease.settled:
                resp_obj = res[0] if isinstance(res, tuple) else res
                status_code = (
                    int(res[1])
                    if isinstance(res, tuple) and len(res) >= 2
                    else int(getattr(resp_obj, "status_code", 200))
                )
                if 200 <= status_code < 300:
                    payload = resp_obj.get_json(silent=True) if hasattr(resp_obj, "get_json") else None
                    if payload is not None:
                        with db_transaction(db, immediate=True):
                            lease.complete(status_code, payload)
                    else:
                        lease.fail()
                else:
                    lease.fail()

            return res

        return wrapper

    return decorator
