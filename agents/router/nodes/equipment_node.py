"""
장비 대기 비용 에이전트 노드 (router 위임자)
- agents/equipment_cost/equipment_cost_node.py의 실제 구현을 호출
- 결과를 equipment_response 문자열로 변환해 RiskState에 반환
- 인건비(labor_cost_node)와 동일한 위임 구조
"""
import os
import sys
from langchain_core.messages import AIMessage
from logger import get_logger

log = get_logger(__name__)

# agents/equipment_cost/ 경로 추가 (tools.py, common/ 접근용)
_ROUTER_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_EQUIP_PATH   = os.path.abspath(os.path.join(_ROUTER_ROOT, '..', 'equipment_cost'))
_PROJECT_ROOT = os.path.abspath(os.path.join(_ROUTER_ROOT, '..', '..'))

for p in [_EQUIP_PATH, _PROJECT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from equipment_cost_node import equipment_cost_node as _equipment_cost_node


def equipment_node(state: dict) -> dict:
    log.debug('equipment_node 진입')
    print('\n[장비 에이전트] 처리 시작')

    result = _equipment_cost_node(state)

    # 실제 노드는 {'messages': [...]} 형태로 반환 — tool_calls 없는 마지막 AIMessage가 최종 응답
    messages = result.get('messages', [])
    last_ai = next(
        (m for m in reversed(messages) if isinstance(m, AIMessage) and not getattr(m, 'tool_calls', None)),
        None
    )
    response = last_ai.content if last_ai else '[장비 에이전트 응답 없음]'

    log.debug('equipment_node 종료')
    print('[장비 에이전트] 완료')
    return {'equipment_response': response}
