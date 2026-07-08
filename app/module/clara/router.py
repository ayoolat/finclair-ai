from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.common.dto.pagination import PageQueryDto
from app.common.response import ApiResponse, PaginatedResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.clara.dto.clara import ClaraChatRequestDto, ClaraMessageDto
from app.module.clara.service.clara_chat_service import ClaraChatService, get_clara_chat_service

router = APIRouter(prefix="/clara", tags=["clara"])


@router.post("/chat")
async def chat(
    dto: ClaraChatRequestDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: ClaraChatService = Depends(get_clara_chat_service),
) -> JSONResponse:
    result = await service.chat(ctx.user_id, dto.message)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.get("/messages", response_model=PaginatedResponse[ClaraMessageDto])
async def messages(
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: ClaraChatService = Depends(get_clara_chat_service),
) -> JSONResponse:
    result = await service.get_history(ctx.user_id, filters)
    return JSONResponse(status_code=200, content=result.data.model_dump())
