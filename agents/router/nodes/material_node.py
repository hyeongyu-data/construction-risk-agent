"""자재 에이전트 노드 (stub)"""
from logger import get_logger

log = get_logger(__name__)


def material_node(state: dict) -> dict:
    log.debug('material_node 진입 (stub)')
    print('\n[자재 에이전트] stub')
    return {'material_response': '[자재 에이전트 미구현]'}
