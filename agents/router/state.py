from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages


class RiskState(TypedDict):
    messages: Annotated[list, add_messages]
    answer_type: Optional[str]         # CHAT | RAG_QA | COST_REPORT | RISK_REPORT | MISSING_INFO
    question_type: Optional[str]       # 'A' (기상악화) | 'B' (현장변경) — 하위호환/로깅용
    needs_weather: Optional[bool]      # 기상 분석 선행 필요 여부 (플래너 결정)
    target_agents: Optional[list]      # 실행할 비용 에이전트 목록 (플래너 결정)
    project_id: Optional[str]          # 프로젝트 ID (프론트에서 설정)
    labor_cost_response: Optional[str]
    labor_cost_result: Optional[dict]
    equipment_response: Optional[str]
    equipment_result: Optional[dict]
    weather_response: Optional[str]
    material_response: Optional[str]
    material_result: Optional[dict]
    rag_response: Optional[str]
    rag_result: Optional[dict]
    rag_query_type: Optional[str]      # item_search | list_items
    structured_response: Optional[dict]
    final_response: Optional[str]      # 합성 노드가 만든 최종 사용자용 답변
