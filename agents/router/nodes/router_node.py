"""라우터 노드 — 분류 후 Command로 다음 에이전트에 직접 핸드오프"""
import os
import re
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


_LIST_QUERY_TERMS = (
    "리스트", "목록", "가지고 있는", "보유", "전체 항목", "등록된", "보유 중",
    "전체 알려", "전체 보여",
)


def _detect_rag_source(query: str) -> str:
    if any(term in query for term in ("시방서", "표준시방서")):
        return "standard_specification"
    if any(term in query for term in ("계약", "특약", "계약서")):
        return "contract"
    return "standard_spec"


def _detect_rag_query_type(query: str) -> str:
    return "list_items" if any(term in query for term in _LIST_QUERY_TERMS) else "item_search"


def _build_rag_query(query: str) -> str:
    cleaned = query
    remove_terms = (
        "표준품셈에서", "표준품셈", "품셈", "표준시방서", "시방서",
        "계약 기준", "계약서", "계약", "특약", "기준", "근거",
        "알려줘", "알려 주세요", "알려주세요", "찾아줘", "찾아 주세요",
        "찾아주세요", "보여줘", "보여 주세요", "보여주세요", "항목", "공종",
        "리스트", "목록", "현재", "가지고 있는", "보유 중인", "보유", "전체",
        "기준들을", "들을", "에서",
    )
    for term in remove_terms:
        cleaned = cleaned.replace(term, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    compact = cleaned.replace(" ", "")
    if "철골세우기" in compact or "철골" in cleaned:
        return "철골 세우기"
    if "콘크리트" in cleaned and "타설" in cleaned:
        return "콘크리트 타설"
    return cleaned or query


def _extract_keywords(search_query: str) -> list[str]:
    stopwords = {
        "표준품셈", "품셈", "기준", "근거", "알려줘", "찾아줘", "항목", "공종",
        "리스트", "목록", "현재", "가지고", "있는", "보유", "전체", "들을",
        "를", "을", "은", "는", "이", "가",
    }
    return [
        token
        for token in re.split(r"\s+", search_query.strip())
        if token and token not in stopwords and len(token) > 1
    ]


def _extract_rag_item_name(content: str) -> str | None:
    for line in content.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("[주의"):
            continue
        return clean
    return None


def _is_keyword_relevant(search_query: str, content: str, item_name: str | None) -> bool:
    keywords = _extract_keywords(search_query)
    if not keywords:
        return False

    haystack = f"{item_name or ''}\n{content}"
    item_text = item_name or ""
    matched_in_all = [keyword for keyword in keywords if keyword in haystack]
    matched_in_item = [keyword for keyword in keywords if keyword in item_text]

    if len(matched_in_item) == len(keywords):
        return True
    return len(matched_in_all) == len(keywords)


def _list_standard_spec_items(limit: int = 50) -> dict:
    from agents.labor_cost.tools import _get_pg_connection

    conn = _get_pg_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT content
        FROM rag.standard_spec
        LIMIT %s
    """, [limit * 3])
    rows = cur.fetchall()
    cur.close()
    conn.close()

    items = []
    seen = set()
    for idx, (content,) in enumerate(rows, start=1):
        item_name = _extract_rag_item_name(str(content))
        if not item_name or item_name in seen:
            continue
        seen.add(item_name)
        items.append({
            "document": "2026 건설공사 표준품셈",
            "item_name": item_name,
            "page": None,
            "chunk_id": f"row_{idx}",
        })
        if len(items) >= limit:
            break

    return {
        "status": "success",
        "rag_query_type": "list_items",
        "rag_source": "standard_spec",
        "query": "",
        "search_query": "",
        "content": "",
        "items": items,
        "evidence": [],
    }


def _search_standard_spec_for_rag(query: str) -> dict:
    rag_source = _detect_rag_source(query)
    rag_query_type = _detect_rag_query_type(query)
    rag_query = _build_rag_query(query)

    if rag_source != "standard_spec":
        label = "표준시방서" if rag_source == "standard_specification" else "계약 기준"
        return {
            "status": "not_available",
            "rag_query_type": rag_query_type,
            "rag_source": rag_source,
            "query": rag_query,
            "search_query": rag_query,
            "content": "",
            "evidence": [],
            "message": f"현재 {label} RAG 문서는 연결되어 있지 않습니다.",
        }

    if rag_query_type == "list_items":
        try:
            return _list_standard_spec_items()
        except Exception as e:
            log.exception(f"RAG_QA 표준품셈 목록 조회 실패: {e}")
            return {
                "status": "error",
                "rag_query_type": "list_items",
                "rag_source": rag_source,
                "query": "",
                "search_query": "",
                "content": "",
                "items": [],
                "evidence": [],
                "warnings": [f"표준품셈 항목 목록 조회 실패: {e}"],
            }

    log.info(f"RAG_QA 표준품셈 검색 실행: query={rag_query!r}")
    print(f"[RAG_QA] 표준품셈 검색 실행: {rag_query}")

    try:
        from agents.labor_cost.tools import _get_pg_connection, embedder

        query_vector = embedder.embed_query(rag_query)
        conn = _get_pg_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT content, embedding <=> %s::vector AS distance
            FROM rag.standard_spec
            ORDER BY distance
            LIMIT 5
        """, [query_vector])
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return {
                "status": "no_result",
                "rag_query_type": "item_search",
                "rag_source": rag_source,
                "query": rag_query,
                "search_query": rag_query,
                "distance": None,
                "content": "",
                "evidence": [],
            }

        selected = None
        for content, distance in rows:
            item_name = _extract_rag_item_name(str(content))
            if _is_keyword_relevant(rag_query, str(content), item_name):
                selected = (str(content), float(distance), item_name, True)
                break

        if selected is None:
            content, distance = rows[0]
            selected = (str(content), float(distance), _extract_rag_item_name(str(content)), False)

        content, distance, item_name, keyword_relevant = selected
        distance = float(distance)

        if distance <= 0.45:
            status = "success"
        elif keyword_relevant and distance <= 0.60:
            status = "success"
        elif keyword_relevant and item_name and all(keyword in item_name for keyword in _extract_keywords(rag_query)):
            status = "success"
        elif distance <= 0.60:
            status = "low_confidence"
        else:
            status = "no_result"

        if not keyword_relevant:
            status = "no_result"

        evidence = [] if status != "success" else [{
            "source": "rag.standard_spec",
            "document": "2026 건설공사 표준품셈",
            "item_name": item_name,
            "query": rag_query,
            "search_query": rag_query,
            "distance": distance,
            "chunk_id": "top_match",
            "page": None,
            "content": content[:1200],
            "type": "standard_spec",
        }]

        return {
            "status": status,
            "rag_query_type": "item_search",
            "rag_source": rag_source,
            "query": rag_query,
            "search_query": rag_query,
            "distance": distance,
            "keyword_relevant": keyword_relevant,
            "content": content if status == "success" else "",
            "candidate_preview": content[:300] if status == "low_confidence" else "",
            "evidence": evidence,
        }
    except Exception as e:
        log.exception(f"RAG_QA 표준품셈 검색 실패: {e}")
        return {
            "status": "error",
            "rag_query_type": rag_query_type,
            "rag_source": rag_source,
            "query": rag_query,
            "search_query": rag_query,
            "content": "",
            "evidence": [],
            "warnings": [f"표준품셈 RAG 검색 실패: {e}"],
        }


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
        print(f'\n[라우터] 보안 차단 ({reason}) -> 요청 거절')
        return Command(
            update={
                'final_response': BLOCKED_RESPONSE,
                'messages': [AIMessage(content=BLOCKED_RESPONSE)],
            },
            goto=END,
        )

    plan = classify_question(classify_input)
    needs_weather = plan['needs_weather']
    answer_type = plan.get('answer_type', 'COST_REPORT')
    # 관련 비용 에이전트(플래너 결정). 비어 있으면 폴백: weather면 장비·인력, 아니면 전체.
    agents = plan['agents'] or (['equipment', 'labor_cost'] if needs_weather else ['equipment', 'material', 'labor_cost'])

    print(f'\n[라우터] weather={needs_weather}, agents={agents}, answer_type={answer_type} — {plan["reason"]}')

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
                'question_type': None,
                'answer_type': 'CHAT',
                'needs_weather': False,
                'target_agents': [],
                'final_response': off_topic,
                'messages': [AIMessage(content=off_topic)],
            },
            goto=END,
        )

    # agents가 비어 있으면 폴백: weather면 장비·인력, 아니면 전체
    if not agents:
        agents = ['equipment', 'labor_cost'] if needs_weather else ['equipment', 'material', 'labor_cost']

    # 상태 업데이트(하위호환 question_type A/B + 신규 answer_type/target_agents)
    update = {
        'question_type': 'A' if needs_weather else 'B',
        'answer_type': answer_type,
        'needs_weather': needs_weather,
        'target_agents': agents,
    }

    if needs_weather:
        # 기상 선행: weather가 리스크·지연을 산출한 뒤 계획된 비용 에이전트로 핸드오프.
        goto = 'weather'
        goto_names = f'weather -> {agents}'
    else:
        # 기상 불필요: 계획된 비용 에이전트만 병렬 실행.
        goto = [Send(agent, state) for agent in agents]
        goto_names = ', '.join(agents)

    log.info(f"router_node 분기: weather={needs_weather} → {goto_names}")
    return Command(update=update, goto=goto)
