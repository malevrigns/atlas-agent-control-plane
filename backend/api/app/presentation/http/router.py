from fastapi import APIRouter

from app.presentation.http.routes import (
    a2a,
    acceptance,
    agent_core,
    agent_thinking,
    auth,
    config,
    control_plane,
    files,
    harness,
    llm,
    mcp,
    memories,
    multi_agent,
    observability,
    rag,
    sandboxes,
    security,
    sessions,
    skills,
    status,
    todos,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(a2a.router)
api_router.include_router(acceptance.router)
api_router.include_router(status.router)
api_router.include_router(sessions.router)
api_router.include_router(todos.router)
api_router.include_router(files.router)
api_router.include_router(harness.router)
api_router.include_router(config.router)
api_router.include_router(control_plane.router)
api_router.include_router(llm.router)
api_router.include_router(mcp.router)
api_router.include_router(memories.router)
api_router.include_router(multi_agent.router)
api_router.include_router(agent_thinking.router)
api_router.include_router(agent_core.router)
api_router.include_router(rag.router)
api_router.include_router(skills.router)
api_router.include_router(sandboxes.router)
api_router.include_router(observability.router)
api_router.include_router(security.router)
