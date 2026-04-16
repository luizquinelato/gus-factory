from fastapi import APIRouter

from app.routers.auth_router import router as auth_router
from app.routers.token_router import router as token_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(token_router, prefix="/token", tags=["token"])
