from fastapi import APIRouter, Depends

from app import __version__
from app.dependencies import get_gateway
from app.services.gateway import GuardrailGateway

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(gateway: GuardrailGateway = Depends(get_gateway)):
    return {"status": "ok", "version": __version__, "provider": gateway.provider.name}
