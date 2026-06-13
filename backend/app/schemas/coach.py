from pydantic import BaseModel, Field


class CoachChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class CoachToolCallSummary(BaseModel):
    name: str


class CoachChatResponse(BaseModel):
    answer: str
    tool_calls: list[CoachToolCallSummary]
