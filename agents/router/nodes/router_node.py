"""라우터 노드 — 분류 후 Command로 다음 에이전트에 직접 핸드오프"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, '..')))
# 프로젝트 루트(common 모듈 접근용)
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import END
from langgraph.types import Command, Send
from router import classify_question
from common.security import check_injection, BLOCKED_RESPONSE
from logger import get_logger

log = get_logger(__name__)


def router_node(state: dict) -> Command:
    log.debug('router_node 진입')
    query = next(
        (m.content for m in reversed(state['messages']) if isinstance(m, HumanMessage)),
        '',
    )

    # 입구 보안 검사: 프롬프트 인젝션 / 시스템 정보 탈취 시도 차단.
    # 여기서 한 번 막으면 type A(weather)·type B(장비/자재/인건비) 경로 모두 보호된다.
    # 차단 시 분류·에이전트 호출을 모두 건너뛰고 바로 END로 단락한다.
    # final_response(test.py)와 AIMessage(chat.py) 두 소비 경로를 모두 채운다.
    is_blocked, reason = check_injection(query)
    if is_blocked:
        log.warning(f'router_node 보안 차단: reason={reason}')
        print(f'\n[라우터] 보안 차단 ({reason}) → 요청 거절')
        return Command(
            update={
                'final_response': BLOCKED_RESPONSE,
                'messages': [AIMessage(content=BLOCKED_RESPONSE)],
            },
            goto=END,
        )

    result = classify_question(query)
    print(f'\n[라우터] {result["type"]} ({result["type_name"]}) — {result["reason"]}')

    if result['type'] == 'A':
        goto = 'weather'
        goto_names = 'weather'
    else:
        goto = [
            Send('equipment', state),
            Send('material', state),
            Send('labor_cost', state),
        ]
        goto_names = 'equipment, material, labor_cost'

    log.info(f"router_node 분기: {result['type']} → {goto_names}")
    return Command(update={'question_type': result['type']}, goto=goto)
