from fastapi import APIRouter

import health_strip

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/strip")
def get_health_strip():
    return {
        "lint": health_strip.compute_lint_status(),
        "istefox": health_strip.compute_istefox_status(),
    }
