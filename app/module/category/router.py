from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.common.response import ApiResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.category.dto.category import CategoryDto, CreateCategoryDto
from app.module.category.service.category_service import CategoryService, get_category_service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=ApiResponse[list[CategoryDto]])
async def list_categories(
    ctx: AuthContext = Depends(get_auth_context),
    service: CategoryService = Depends(get_category_service),
) -> JSONResponse:
    result = await service.list_categories(ctx.user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("", response_model=ApiResponse[CategoryDto])
async def create_category(
    dto: CreateCategoryDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: CategoryService = Depends(get_category_service),
) -> JSONResponse:
    result = await service.create_category(ctx.user_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data, message="Category created.").model_dump())
