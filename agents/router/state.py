from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages


class RiskState(TypedDict):
    messages: Annotated[list, add_messages]
    question_type: Optional[str]       # 'A' (기상악화) | 'B' (현장변경)
    project_id: Optional[str]          # 프로젝트 ID (프론트에서 설정)
    labor_cost_response: Optional[str]
    equipment_response: Optional[str]
    weather_response: Optional[str]
    material_response: Optional[str]
