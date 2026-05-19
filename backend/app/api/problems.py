from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_session
from backend.app.schemas.problem import (
    ProblemCategoryListResponse,
    ProblemDetailResponse,
    ProblemListResponse,
)
from backend.app.services.problem_service import (
    get_problem_detail,
    list_problem_categories,
    list_problems,
)


router = APIRouter()


@router.get("/problems", response_model=ProblemListResponse)
async def problem_list(
    keyword: str | None = None,
    difficulty: str | None = Query(default=None, pattern="^(Easy|Medium|Hard)$"),
    tag: str | None = None,
    category: str | None = None,
    sort: str = Query(default="frontend_id", pattern="^(frontend_id|difficulty|title)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await list_problems(
        session,
        keyword=keyword,
        difficulty=difficulty,
        tag=tag,
        category=category,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/problems/{slug}", response_model=ProblemDetailResponse)
async def problem_detail(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    problem = await get_problem_detail(session, slug)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem


@router.get("/problem-categories", response_model=ProblemCategoryListResponse)
async def problem_categories(session: AsyncSession = Depends(get_session)) -> dict:
    return await list_problem_categories(session)
