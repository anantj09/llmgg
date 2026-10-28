"""FastAPI dependencies: service lookup and API-key auth."""

import hmac

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings, get_settings
from app.services.gateway import GuardrailGateway


def get_gateway(request: Request) -> GuardrailGateway:
    return request.app.state.gateway


def require_api_key(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    keys = settings.api_keys
    if not keys:
        return  # auth disabled (local demo)
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not any(hmac.compare_digest(token, k) for k in keys):  # constant-time compare
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing gateway API key")
