from fastapi import APIRouter, Depends

from app import __version__
from app.config import Settings, get_settings
from app.dependencies import get_gateway
from app.services.gateway import GuardrailGateway

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(
    gateway: GuardrailGateway = Depends(get_gateway), settings: Settings = Depends(get_settings)
):
    # "commit" lets the CD pipeline confirm the new version is actually live.
    return {
        "status": "ok",
        "version": __version__,
        "provider": gateway.provider.name,
        "commit": settings.deployed_commit,
    }
