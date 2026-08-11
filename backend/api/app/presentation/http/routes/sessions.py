from fastapi import APIRouter

from app.application.agent_runner_service import AgentRunnerService
from app.presentation.http.routes.session_core_routes import router as core_router
from app.presentation.http.routes.session_file_routes import router as file_router
from app.presentation.http.routes.session_plan_task_routes import router as plan_task_router
from app.presentation.http.routes.session_route_dependencies import (
    build_agent_runner_service,
)

router = APIRouter()
router.include_router(core_router, prefix="/sessions", tags=["sessions"])
router.include_router(plan_task_router, prefix="/sessions", tags=["sessions"])
router.include_router(file_router, prefix="/sessions", tags=["sessions"])

__all__ = ["AgentRunnerService", "build_agent_runner_service", "router"]
