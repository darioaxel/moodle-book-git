"""Webhook receiver ``POST /hooks/git`` (ENG-093, §10.4/§27).

La plataforma Git aún no está elegida (§27: GitHub/GitLab); por eso el
payload se acepta como **JSON genérico**: si trae campos reconocibles
(``event``, ``ref``, ``repository``/``repo``, ``commits``…) se extraen; si no,
se registra el evento tal cual. Al recibir un webhook válido el servicio:

1. Registra el evento ``webhook.received`` en el log estructurado (ENG-101).
2. **Invalida el caché de renders** (ENG-103): un push/merge/tag puede haber
   movido ramas o creado tags; las entradas cacheadas bajo commits
   inmutables son seguras, pero la invalidación completa es la política
   conservadora de la Beta (el caché se repuebla solo).
3. Deja el evento en ``AuditEvent`` (ENG-095, actor ``git-platform``).

Seguridad (§25): firma HMAC-SHA256 del **body crudo** con el secreto
compartido ``COURSEASCODE_WEBHOOK_SECRET``, en el header
``X-CourseAsCode-Signature`` con formato ``sha256=<hex>`` (mismo estilo que
los webhooks de GitHub). Verificación con ``hmac.compare_digest``.

- Sin secreto configurado → el endpoint queda **deshabilitado** (503 JSON).
- Firma ausente o inválida → 401 JSON (no se registra nada).

Todo webhook válido queda en ``AuditEvent`` (ENG-095, actor ``git-platform``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request

from courseascode.content.cache import RenderCache
from courseascode.releases.store import ReleaseStore

SIGNATURE_HEADER = "X-CourseAsCode-Signature"
SIGNATURE_PREFIX = "sha256="


def create_hooks_router(
    store: ReleaseStore | None,
    webhook_secret: str | None,
    cache: RenderCache[Any] | None = None,
) -> APIRouter:
    """Router del webhook; sin store o sin secreto responde 503 (deshabilitado)."""
    router = APIRouter()

    @router.post("/hooks/git")
    async def git_hook(request: Request) -> dict[str, object]:
        if store is None or not webhook_secret:
            raise HTTPException(
                status_code=503,
                detail=(
                    "webhook deshabilitado: configura COURSEASCODE_DB y "
                    "COURSEASCODE_WEBHOOK_SECRET en el servicio"
                ),
            )
        body = await request.body()
        signature = request.headers.get(SIGNATURE_HEADER, "")
        expected = (
            SIGNATURE_PREFIX + hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        )
        if not signature or not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="firma del webhook inválida o ausente")

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=f"payload JSON inválido: {exc}") from exc

        event, detail = _describe(payload)
        structlog.get_logger().info("webhook.received", git_event=event, actor="git-platform")
        if cache is not None:
            cache.clear()
        store.record_event(
            "webhook.git",
            actor="git-platform",
            detail=detail,
        )
        return {
            "received": True,
            "event": event,
            "action": "recalculate",
            "note": "caché de renders invalidado y recálculo de estados registrado",
        }

    return router


def _describe(payload: object) -> tuple[str, dict[str, object]]:
    """Extrae (evento, detalle) de un payload genérico de plataforma Git."""
    if not isinstance(payload, dict):
        return ("generic", {"payload": str(payload)[:200]})
    event = str(payload.get("event") or payload.get("event_name") or "generic")
    detail: dict[str, object] = {"event": event}
    for key in ("ref", "before", "after", "repository", "repo", "commits", "action"):
        if key in payload:
            value = payload[key]
            if isinstance(value, (str, int, float, bool)) or value is None:
                detail[key] = value
            else:
                detail[key] = json.dumps(value, ensure_ascii=False)[:500]
    return (event, detail)
