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


def _build_classify_input(messages: list) -> tuple[str, str]:
    """분류용 입력 구성.

    Returns (latest_query, classify_input)
    - latest_query: 가장 최근 사용자 메시지 (보안 검사 대상)
    - classify_input: 후속 답변일 때 직전 대화 맥락을 함께 담은 분류 입력.
      "B로 해줘", "네 그렇게요" 같은 짧은 후속 답변이 직전 맥락(예: 콘크리트 타설/태풍)을
      잃지 않고 올바른 타입(A/B)으로 분류되도록 한다.
    """
    latest_query = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        '',
    )

    # 직전 대화가 있으면 맥락으로 덧붙인다 (마지막 메시지 제외).
    prior = messages[:-1] if messages else []
    prior_lines = [
        f"{'사용자' if isinstance(m, HumanMessage) else 'AI'}: {m.content}"
        for m in prior
        if isinstance(m, (HumanMessage, AIMessage)) and isinstance(m.content, str) and m.content.strip()
    ]
    if not prior_lines:
        return latest_query, latest_query

    prior_text = "\n".join(prior_lines)[-1500:]  # 과도한 토큰 방지
    classify_input = (
        f"[이전 대화 맥락 — 분류 참고용]\n{prior_text}\n\n"
        f"[현재 분류할 사용자 메시지]\n{latest_query}"
    )
    return latest_query, classify_input


def router_node(state: dict) -> Command:
    log.debug('router_node 진입')
    latest_query, classify_input = _build_classify_input(state['messages'])

    # 입구 보안 검사: 프롬프트 인젝션 / 시스템 정보 탈취 시도 차단.
    # 여기서 한 번 막으면 type A(weather)·type B(장비/자재/인건비) 경로 모두 보호된다.
    # 차단 시 분류·에이전트 호출을 모두 건너뛰고 바로 END로 단락한다.
    # final_response(test.py)와 AIMessage(chat.py) 두 소비 경로를 모두 채운다.
    is_blocked, reason = check_injection(latest_query)
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

    result = classify_question(classify_input)
    needs_weather = result["needs_weather"]
    agents = result.get("agents", [])
    reason = result.get("reason", "")

    question_type = 'A' if needs_weather else 'B'
    print(f'\n[라우터] {"A(기상악화)" if needs_weather else "B(현장변경)"} - {reason}')
    print(f'[라우터] 실행 에이전트: {agents}')

    # 건설 무관 질문 — 에이전트 호출 없이 바로 종료
    if not needs_weather and not agents:
        off_topic = (
            "안녕하세요! 저는 건설 현장 리스크 분석 AI입니다.\n\n"
            "다음과 같은 질문에 도움을 드릴 수 있습니다:\n"
            "- **기상 리스크**: 날씨로 인한 공정 지연 분석\n"
            "- **인건비 산출**: 표준품셈 기반 직접노무비\n"
            "- **장비 비용**: 장비 대기 및 임대 비용\n"
            "- **자재 가격**: 건설 자재 시세 및 조달 리스크\n\n"
            "건설 현장 관련 질문을 입력해 주세요."
        )
        log.info("router_node: 건설 무관 질문 -> 즉시 종료")
        return Command(
            update={
                'question_type': question_type,
                'needs_weather': False,
                'target_agents': [],
                'final_response': off_topic,
                'messages': [AIMessage(content=off_topic)],
            },
            goto=END,
        )

    if needs_weather:
        goto = 'weather'
        goto_names = 'weather'
    else:
        goto = [Send(agent, state) for agent in agents]
        goto_names = ', '.join(agents)

    log.info(f"router_node 분기: {question_type} -> {goto_names}")
    return Command(
        update={'question_type': question_type, 'needs_weather': needs_weather, 'target_agents': agents},
        goto=goto,
    )
