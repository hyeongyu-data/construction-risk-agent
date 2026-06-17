"""
인건비 에이전트 노드
- agents/labor_cost/labor_cost_node.py의 실제 구현을 호출
- 결과를 labor_cost_response 문자열로 변환해 RiskState에 반환
"""
import os
import sys
from langchain_core.messages import AIMessage
from logger import get_logger

log = get_logger(__name__)

# agents/labor_cost/ 경로 추가 (tools.py, common/ 접근용)
_ROUTER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_LABOR_PATH  = os.path.abspath(os.path.join(_ROUTER_ROOT, '..', 'labor_cost'))
_PROJECT_ROOT = os.path.abspath(os.path.join(_ROUTER_ROOT, '..', '..'))

for p in [_LABOR_PATH, _PROJECT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from labor_cost_node import labor_cost_node as _labor_cost_node


def labor_cost_node(state: dict) -> dict:
    log.debug('labor_cost_node 진입')
    print('\n[인건비 에이전트] 처리 시작')

    result = _labor_cost_node(state)

    # 실제 노드는 {'messages': [AIMessage(...)]} 형태로 반환
    messages = result.get('messages', [])
    last_ai = next(
        (m for m in reversed(messages) if isinstance(m, AIMessage) and not getattr(m, 'tool_calls', None)),
        None
    )
    response = last_ai.content if last_ai else '[인건비 에이전트 응답 없음]'

    log.debug('labor_cost_node 종료')
    print('[인건비 에이전트] 완료')
    return {'labor_cost_response': response}
