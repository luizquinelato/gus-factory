from fastapi import APIRouter

from app.routers.health_router import router as health_router
from app.routers.auth_router import router as auth_router
from app.routers.users_router import router as users_router
from app.routers.tenant_colors_router import router as colors_router
from app.routers.admin_router import router as admin_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router,  prefix="/auth",         tags=["auth"])
api_router.include_router(users_router, prefix="/users",        tags=["users"])
api_router.include_router(colors_router,prefix="/tenant/colors",tags=["colors"])
api_router.include_router(admin_router, prefix="/admin",        tags=["admin"])
