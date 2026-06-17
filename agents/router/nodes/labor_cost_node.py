"""인건비 에이전트 노드 (stub — 추후 construction_risk_agent-labor_cost 연결)"""
from logger import get_logger

log = get_logger(__name__)


def labor_cost_node(state: dict) -> dict:
    log.debug('labor_cost_node 진입 (stub)')
    print('\n[인건비 에이전트] stub')
    return {'labor_cost_response': '[인건비 에이전트 미구현]'}
