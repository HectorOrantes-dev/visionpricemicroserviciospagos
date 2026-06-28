"""Middleware de idempotencia (drop-in) para el microservicio de Pagos.

Se activa SOLO para POST/PUT/PATCH que traigan el header `Idempotency-Key`.
Misma llave => no reprocesa: devuelve la respuesta guardada.

Montaje (en main.py):
    from src.shared.database import SessionLocal   # async_sessionmaker
    from src.shared.idempotency import IdempotencyMiddleware
    app.add_middleware(IdempotencyMiddleware, session_factory=SessionLocal)
"""
import base64
import hashlib
import json
import logging
from datetime import datetime, timezone

import sqlalchemy as sa

_log = logging.getLogger("idempotency")
_MUTANTES = {"POST", "PUT", "PATCH"}

# Tabla por Core: no depende de los modelos ORM. Debe existir en la BD
# (ver migración alembic 0002_idempotency_keys).
_metadata = sa.MetaData()
idempotency_keys = sa.Table(
    "idempotency_keys",
    _metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("clave", sa.String(255), unique=True, nullable=False),
    # En este micro el user_id es el claim `sub` del JWT (string).
    sa.Column("usuario_id", sa.String(128)),
    sa.Column("metodo", sa.String(10), nullable=False),
    sa.Column("ruta", sa.String(255), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("estado", sa.String(20), nullable=False, server_default="procesando"),
    sa.Column("status_code", sa.Integer),
    sa.Column("content_type", sa.String(100)),
    sa.Column("response_body", sa.Text),
    sa.Column("fecha_creacion", sa.DateTime, server_default=sa.func.now()),
    sa.Column("fecha_actualizacion", sa.DateTime, server_default=sa.func.now()),
)


def _utcnow() -> datetime:
    # UTC naive: compatible con columnas TIMESTAMP (sin zona) en Postgres.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _header(scope, nombre: bytes) -> bytes | None:
    for k, v in scope["headers"]:
        if k == nombre:
            return v
    return None


async def _leer_body(receive) -> bytes:
    body = b""
    while True:
        message = await receive()
        if message["type"] == "http.request":
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        else:
            break
    return body


def _replay_receive(body: bytes):
    enviado = {"done": False}

    async def receive():
        if enviado["done"]:
            return {"type": "http.disconnect"}
        enviado["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


async def _send_json(send, status: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": body})


class IdempotencyMiddleware:
    def __init__(self, app, session_factory, user_id_extractor=None) -> None:
        self.app = app
        self.session_factory = session_factory        # async_sessionmaker
        self.user_id_extractor = user_id_extractor     # opcional: scope -> str|None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in _MUTANTES:
            return await self.app(scope, receive, send)

        clave_b = _header(scope, b"idempotency-key")
        if not clave_b:
            return await self.app(scope, receive, send)

        clave = clave_b.decode()
        body = await _leer_body(receive)
        req_hash = hashlib.sha256(scope["path"].encode() + b"|" + body).hexdigest()
        receive = _replay_receive(body)

        try:
            return await self._con_idempotencia(scope, receive, send, clave, req_hash)
        except Exception as exc:  # fail-open: nunca romper la petición
            _log.warning("Idempotencia deshabilitada por error: %s", exc)
            return await self.app(scope, receive, send)

    async def _con_idempotencia(self, scope, receive, send, clave, req_hash):
        uid = self.user_id_extractor(scope) if self.user_id_extractor else None

        async with self.session_factory() as session:
            try:
                await session.execute(
                    sa.insert(idempotency_keys).values(
                        clave=clave, usuario_id=uid, metodo=scope["method"],
                        ruta=scope["path"], request_hash=req_hash, estado="procesando",
                    )
                )
                await session.commit()
                primera_vez = True
            except sa.exc.IntegrityError:
                await session.rollback()
                primera_vez = False

            if not primera_vez:
                row = (await session.execute(
                    sa.select(idempotency_keys).where(idempotency_keys.c.clave == clave)
                )).mappings().one()
                if row["request_hash"] != req_hash:
                    return await _send_json(send, 409, "idempotency_key_reuse",
                                            "La llave se usó con otro cuerpo.")
                if row["estado"] != "completado":
                    return await _send_json(send, 409, "request_in_progress",
                                            "La petición ya se está procesando.")
                cuerpo = base64.b64decode(row["response_body"] or "")
                await send({"type": "http.response.start",
                            "status": row["status_code"] or 200,
                            "headers": [
                                (b"content-type",
                                 (row["content_type"] or "application/json").encode()),
                                (b"idempotent-replay", b"true")]})
                return await send({"type": "http.response.body", "body": cuerpo})

        # Primera vez: ejecuta y captura la respuesta.
        captura = {"status": 200, "body": b"", "content_type": "application/json"}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                captura["status"] = message["status"]
                for k, v in message.get("headers", []):
                    if k == b"content-type":
                        captura["content_type"] = v.decode()
            elif message["type"] == "http.response.body":
                captura["body"] += message.get("body", b"")
            await send(message)

        await self.app(scope, receive, send_wrapper)

        async with self.session_factory() as session:
            if captura["status"] < 500:
                await session.execute(
                    sa.update(idempotency_keys)
                    .where(idempotency_keys.c.clave == clave)
                    .values(estado="completado", status_code=captura["status"],
                            content_type=captura["content_type"],
                            response_body=base64.b64encode(captura["body"]).decode(),
                            fecha_actualizacion=_utcnow())
                )
            else:
                # error de servidor: borrar para permitir reintento
                await session.execute(
                    sa.delete(idempotency_keys).where(idempotency_keys.c.clave == clave)
                )
            await session.commit()
