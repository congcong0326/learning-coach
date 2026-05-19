from fastapi import APIRouter, HTTPException, status

from backend.app.db.health import check_database


router = APIRouter()


@router.get("/db/health")
async def db_health() -> dict[str, str]:
    if not await check_database():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unreachable",
        )

    return {
        "status": "ok",
        "database": "reachable",
    }
