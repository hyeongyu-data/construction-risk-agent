"""
자재 단가 에이전트 노드 (router 위임자)
- agents/material_cost/material_cost_agent.py의 정식 구현을 재사용
- labor_cost / equipment 노드와 동일한 위임 구조 (툴·프롬프트·에이전트 정의 중복 제거)
"""
import os
import sys
from logger import get_logger

log = get_logger(__name__)

# 프로젝트 루트 경로 추가 (agents.material_cost 패키지 접근용)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, '../../..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agents.material_cost.material_cost_agent import create_material_cost_agent

# 에이전트는 모듈 로드 시 한 번만 생성해 재사용한다 (요청마다 재생성 방지).
# run_material_cost_agent()는 호출마다 에이전트를 새로 만들고 단일 문자열만
# 받으므로(메시지 히스토리 유실) 사용하지 않는다.
_agent = create_material_cost_agent()


def material_node(state: dict) -> dict:
    log.debug('material_node 진입')
    print('\n[자재 에이전트] 처리 시작')

    result = _agent.invoke({'messages': state['messages']})

    tool_calls = [
        tc['name']
        for m in result['messages']
        for tc in getattr(m, 'tool_calls', None) or []
    ]
    if tool_calls:
        log.debug(f"material_node 툴 호출 순서: {' → '.join(tool_calls)}")

    response = result['messages'][-1].content
    log.debug('material_node 종료')
    print('[자재 에이전트] 완료')
    return {'material_response': response}
