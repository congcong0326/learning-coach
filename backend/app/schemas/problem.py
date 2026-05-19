from pydantic import BaseModel


class ProblemTag(BaseModel):
    slug: str
    name: str
    translated_name: str


class ProblemCategorySummary(BaseModel):
    slug: str
    name: str
    description: str


class ProblemListItem(BaseModel):
    id: int
    frontend_id: str
    slug: str
    title: str
    translated_title: str
    difficulty: str
    tags: list[ProblemTag]
    categories: list[ProblemCategorySummary]


class ProblemListResponse(BaseModel):
    items: list[ProblemListItem]
    total: int
    page: int
    page_size: int


class ProblemDetailResponse(ProblemListItem):
    statement_md: str
    leetcode_url: str
    sample_test_case: str
    python3_snippet: str


class ProblemCategoryListResponse(BaseModel):
    items: list[ProblemCategorySummary]
