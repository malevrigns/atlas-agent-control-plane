from fastapi import APIRouter, Depends

from app.application.app_settings_service import (
    AppSettingsService,
    get_app_settings_service,
)
from app.application.llm_service import LLMService
from app.core.exceptions import AppException
from app.schemas.common import ApiResponse
from app.schemas.app_settings import (
    AppSettingsResponse,
    SettingsIntegrationCreateRequest,
    SettingsIntegrationResponse,
    SettingsItemUpdateRequest,
    SettingsItemResponse,
    SettingsModuleResponse,
    SettingsModuleUpdateRequest,
)
from app.schemas.llm import LLMConfigResponse

router = APIRouter(prefix="/config", tags=["config"])


# ===================== 第1步：创建应用服务依赖 =====================
def build_llm_service() -> LLMService:
    return LLMService()


# ===================== 第2步：暴露不含密钥的 LLM 配置接口 =====================
@router.get("/llm", response_model=ApiResponse[LLMConfigResponse])
async def get_llm_config(
    service: LLMService = Depends(build_llm_service),
) -> ApiResponse[LLMConfigResponse]:
    return ApiResponse(data=LLMConfigResponse.model_validate(service.get_public_config()))


# ===================== 第3步：把设置领域对象转换为响应模型 =====================
def to_settings_module_response(module) -> SettingsModuleResponse:
    # 1. module.items 是应用服务整理好的配置项字典列表。
    # 2. 在路由层统一转成 Pydantic 响应模型，避免前端收到非预期字段。
    return SettingsModuleResponse(
        key=module.key,
        name=module.name,
        description=module.description,
        enabled=module.enabled,
        default_item=module.default_item,
        status=module.status,
        status_message=module.status_message,
        source=module.source,
        verify_command=module.verify_command,
        items=[
            SettingsItemResponse(
                name=str(item["name"]),
                description=str(item.get("description") or ""),
                enabled=bool(item.get("enabled", False)),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in module.items
        ],
    )


def to_integration_response(integration) -> SettingsIntegrationResponse:
    return SettingsIntegrationResponse(
        id=integration.id,
        kind=integration.kind,
        name=integration.name,
        description=integration.description,
        endpoint=integration.endpoint,
        enabled=integration.enabled,
    )


def to_app_settings_response(service: AppSettingsService) -> AppSettingsResponse:
    snapshot = service.get_snapshot()
    return AppSettingsResponse(
        modules=[to_settings_module_response(module) for module in snapshot.modules],
        integrations=[
            to_integration_response(integration)
            for integration in snapshot.integrations
        ],
    )


def refresh_settings_module(
    service: AppSettingsService,
    module_key: str,
) -> SettingsModuleResponse:
    """重新读取设置快照，并返回指定模块。"""

    for module in service.get_snapshot().modules:
        if module.key == module_key:
            return to_settings_module_response(module)
    raise AppException(
        message=f"settings module not found: {module_key}",
        code=404,
        status_code=404,
    )


# ===================== 第4步：读取完整应用设置 =====================
@router.get("/app", response_model=ApiResponse[AppSettingsResponse])
async def get_app_settings(
    service: AppSettingsService = Depends(get_app_settings_service),
) -> ApiResponse[AppSettingsResponse]:
    # 设置页一次请求就能拿到 LLM、MCP、A2A 和多 Agent 的配置摘要。
    return ApiResponse(data=to_app_settings_response(service))


# ===================== 第5步：更新模块启用状态或默认项 =====================
@router.patch("/modules/{module_key}", response_model=ApiResponse[SettingsModuleResponse])
async def update_settings_module(
    module_key: str,
    payload: SettingsModuleUpdateRequest,
    service: AppSettingsService = Depends(get_app_settings_service),
) -> ApiResponse[SettingsModuleResponse]:
    try:
        module = service.update_module(
            module_key=module_key,
            enabled=payload.enabled,
            default_item=payload.default_item,
        )
    except KeyError as exc:
        raise AppException(
            message=f"settings module not found: {module_key}",
            code=404,
            status_code=404,
        ) from exc
    return ApiResponse(data=to_settings_module_response(module))


# ===================== 第6步：新增和删除运行时集成记录 =====================
@router.post("/integrations", response_model=ApiResponse[SettingsIntegrationResponse])
async def create_settings_integration(
    payload: SettingsIntegrationCreateRequest,
    service: AppSettingsService = Depends(get_app_settings_service),
) -> ApiResponse[SettingsIntegrationResponse]:
    integration = service.add_integration(
        kind=payload.kind,
        name=payload.name,
        description=payload.description,
        endpoint=payload.endpoint,
    )
    return ApiResponse(data=to_integration_response(integration))


@router.patch(
    "/modules/{module_key}/items/{item_name}",
    response_model=ApiResponse[SettingsModuleResponse],
)
async def update_settings_item(
    module_key: str,
    item_name: str,
    payload: SettingsItemUpdateRequest,
    service: AppSettingsService = Depends(get_app_settings_service),
) -> ApiResponse[SettingsModuleResponse]:
    try:
        service.update_config_item(
            module_key=module_key,
            item_name=item_name,
            enabled=payload.enabled,
        )
    except KeyError as exc:
        raise AppException(
            message=f"settings item not found: {module_key}.{item_name}",
            code=404,
            status_code=404,
        ) from exc
    return ApiResponse(data=refresh_settings_module(service, module_key))


@router.delete(
    "/modules/{module_key}/items/{item_name}",
    response_model=ApiResponse[SettingsModuleResponse],
)
async def delete_settings_item(
    module_key: str,
    item_name: str,
    service: AppSettingsService = Depends(get_app_settings_service),
) -> ApiResponse[SettingsModuleResponse]:
    try:
        service.delete_config_item(module_key=module_key, item_name=item_name)
    except KeyError as exc:
        raise AppException(
            message=f"settings item not found: {module_key}.{item_name}",
            code=404,
            status_code=404,
        ) from exc
    return ApiResponse(data=refresh_settings_module(service, module_key))


@router.delete(
    "/integrations/{integration_id}",
    response_model=ApiResponse[SettingsIntegrationResponse],
)
async def delete_settings_integration(
    integration_id: str,
    service: AppSettingsService = Depends(get_app_settings_service),
) -> ApiResponse[SettingsIntegrationResponse]:
    try:
        integration = service.delete_integration(integration_id)
    except KeyError as exc:
        raise AppException(
            message=f"settings integration not found: {integration_id}",
            code=404,
            status_code=404,
        ) from exc
    return ApiResponse(data=to_integration_response(integration))
