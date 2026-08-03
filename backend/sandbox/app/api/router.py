from fastapi import APIRouter

from app.api.routes import browser, files, shell, status, supervisor, vnc

api_router = APIRouter()
api_router.include_router(browser.router)
api_router.include_router(files.router)
api_router.include_router(shell.router)
api_router.include_router(status.router)
api_router.include_router(supervisor.router)
api_router.include_router(vnc.router)
