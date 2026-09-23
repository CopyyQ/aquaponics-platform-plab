from __future__ import annotations

from fastapi import Request

from app.services.login_rate_limit_service import resolve_client_ip


def resolve_request_client_ip(request: Request) -> str:
    peer = request.client.host if request.client is not None else "unknown"
    return resolve_client_ip(peer, request.headers.get("x-forwarded-for"))
