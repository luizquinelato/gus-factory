from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "healthy", "service": "saas-blueprint-v1-backend"}



