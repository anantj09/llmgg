from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from app.api.schemas import ChatCompletionRequest
from app.dependencies import get_gateway, require_api_key
from app.services.gateway import GuardrailGateway

router = APIRouter(prefix="/v1", tags=["chat"], dependencies=[Depends(require_api_key)])


@router.post("/chat/completions")
async def chat_completions(
    req: ChatCompletionRequest,
    gateway: GuardrailGateway = Depends(get_gateway),
    x_guardrail_debug: str | None = Header(default=None),
) -> JSONResponse:
    result = await gateway.handle_chat(req, debug=(x_guardrail_debug or "").lower() == "true")
    return JSONResponse(result.body, status_code=result.status_code, headers=result.headers)
