from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import Settings, get_settings
from app.core.errors import PolicyError
from app.core.policy import load_policy
from app.dependencies import get_gateway, require_api_key
from app.services.gateway import GuardrailGateway

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_api_key)])


@router.get("/stats")
async def stats(gateway: GuardrailGateway = Depends(get_gateway)):
    return await gateway.store.stats()


@router.get("/events")
async def events(limit: int = Query(50, ge=1, le=500), gateway: GuardrailGateway = Depends(get_gateway)):
    return {"events": await gateway.store.recent(limit)}


@router.get("/policy")
async def policy(gateway: GuardrailGateway = Depends(get_gateway)):
    return gateway.describe_policy()


@router.post("/policy/reload")
async def reload_policy(
    gateway: GuardrailGateway = Depends(get_gateway), settings: Settings = Depends(get_settings)
):
    try:
        gateway.reload_policy(load_policy(settings.policy_path))
    except PolicyError as exc:
        # The old policy stays active when the new file is invalid.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"reloaded": True, "policy": gateway.describe_policy()}
