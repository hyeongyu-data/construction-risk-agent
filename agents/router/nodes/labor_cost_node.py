"""
인건비 에이전트 노드 (router 위임자)
- agents/labor_cost/labor_cost_node.py의 실제 구현을 호출
- 결과를 labor_cost_response(문자열) + labor_cost_result(구조화 dict)로 변환해 RiskState에 반환
"""
import os
import sys
import json
import re
import importlib.util
from langchain_core.messages import AIMessage, HumanMessage
from logger import get_logger

log = get_logger(__name__)

_ROUTER_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_LABOR_PATH   = os.path.abspath(os.path.join(_ROUTER_ROOT, '..', 'labor_cost'))
_PROJECT_ROOT = os.path.abspath(os.path.join(_ROUTER_ROOT, '..', '..'))

if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 이 파일과 실제 구현 파일이 둘 다 labor_cost_node.py라서
# from labor_cost_node import ... 는 sys.path 순서에 따라 자기 자신을 재귀 import할 위험이 있다.
# 절대 경로로 직접 로드해 충돌을 막는다.
_labor_node_spec = importlib.util.spec_from_file_location(
    "actual_labor_cost_node_module",
    os.path.join(_LABOR_PATH, "labor_cost_node.py"),
)
_labor_node_module = importlib.util.module_from_spec(_labor_node_spec)
_labor_node_spec.loader.exec_module(_labor_node_module)

_labor_cost_node = _labor_node_module.labor_cost_node


# ── 헬퍼: content 타입 정규화 ────────────────────────────────
def _message_content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict):
                texts.append(part.get("text", ""))
            else:
                texts.append(str(part))
        return "\n".join(texts).strip()
    return str(content)


# ── 헬퍼: JSON 파싱 ──────────────────────────────────────────
def _clean_json_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()
    start = cleaned.find("{")
    end   = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]
    return cleaned


def _ensure_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [str(value)]


def _normalize_evidence(value) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    normalized = []
    for item in value:
        if isinstance(item, dict):
            normalized.append({
                "source":  item.get("source", "unknown"),
                "type":    item.get("type", "unknown"),
                "content": item.get("content", ""),
                "usage":   item.get("usage", ""),
            })
        else:
            normalized.append({
                "source":  "unknown",
                "type":    "unknown",
                "content": str(item),
                "usage":   "LLM 응답 근거",
            })
    return normalized


def _default_result(*, status="ERROR", summary="인건비 에이전트 처리 중 오류가 발생했습니다.",
                    raw_response="", is_relevant=False) -> dict:
    return {
        "agent_name":    "labor",
        "domain":        "인건비",
        "is_relevant":   is_relevant,
        "status":        status,
        "summary":       summary,
        "cost_items":    [],
        "total_cost":    None,
        "missing_fields": [],
        "assumptions":   [],
        "excluded_items": ["장비비", "자재비", "이윤", "부가세", "도심지 할증"],
        "warnings":      ["인건비 에이전트 응답을 구조화하는 과정에서 문제가 발생했습니다."],
        "evidence":      [],
        "raw_response":  raw_response,
    }


def _filter_own_domain(data: dict, own_category: str) -> dict:
    """cost_items에서 자기 도메인(또는 카테고리 미지정) 항목만 남기고 total_cost를 재계산한다.
    LLM이 타 도메인(자재/장비 등) 비용을 섞어 넣어 중복 합산되는 것을 막는 결정론적 가드."""
    items = data.get("cost_items") or []
    kept, dropped = [], 0
    for it in items:
        cat = str((it or {}).get("category", "") or "").strip().lower()
        if cat in ("", own_category):
            kept.append(it)
        else:
            dropped += 1
    if dropped:
        data["cost_items"] = kept
        data.setdefault("warnings", []).append(
            f"다른 도메인 비용 {dropped}건을 제거했습니다(이 에이전트는 {own_category} 항목만 산정)."
        )
        amounts = [it.get("amount") for it in kept if isinstance(it.get("amount"), (int, float))]
        data["total_cost"] = sum(amounts) if amounts else None
    return data


def _normalize_result(data: dict, raw_response: str) -> dict:
    data.setdefault("agent_name", "labor")
    data.setdefault("domain", "인건비")
    data.setdefault("status", "ERROR")
    data.setdefault("summary", "")
    data.setdefault("cost_items", [])
    data.setdefault("total_cost", None)
    data.setdefault("missing_fields", [])
    data.setdefault("assumptions", [])
    data.setdefault("excluded_items", [])
    data.setdefault("warnings", [])
    data.setdefault("evidence", [])

    if not isinstance(data["cost_items"], list):
        data["cost_items"] = []

    data["missing_fields"] = _ensure_list(data["missing_fields"])
    data["assumptions"]    = _ensure_list(data["assumptions"])
    data["excluded_items"] = _ensure_list(data["excluded_items"])
    data["warnings"]       = _ensure_list(data["warnings"])
    data["evidence"]       = _normalize_evidence(data["evidence"])

    allowed = {"CALCULATED", "PARTIAL", "MISSING_INFO", "IRRELEVANT", "ERROR"}
    if data["status"] not in allowed:
        data["status"] = "ERROR"
        data["warnings"].append("허용되지 않은 status 값이 반환되어 ERROR로 보정했습니다.")

    # is_relevant를 status 기준으로 보정
    if data["status"] in {"CALCULATED", "PARTIAL", "MISSING_INFO"}:
        data["is_relevant"] = True
    elif data["status"] == "IRRELEVANT":
        data["is_relevant"] = False
    else:
        data.setdefault("is_relevant", False)

    for item in ["장비비", "자재비", "이윤", "부가세"]:
        if item not in data["excluded_items"]:
            data["excluded_items"].append(item)

    # 도메인 침범 방지: labor 카테고리(또는 미지정) 항목만 유지하고 total_cost 재계산.
    data["domain"] = "인건비"
    data = _filter_own_domain(data, "labor")

    data["raw_response"] = raw_response
    return data


def _parse_json_response(text: str) -> dict:
    try:
        cleaned = _clean_json_text(text)
        data    = json.loads(cleaned)
        if not isinstance(data, dict):
            return _default_result(status="ERROR", summary="응답이 JSON 객체가 아닙니다.",
                                   raw_response=text)
        return _normalize_result(data, text)
    except Exception as e:
        log.exception(f"labor_cost_node JSON 파싱 실패: {e}")
        return _default_result(status="ERROR", summary="응답을 JSON으로 파싱하지 못했습니다.",
                               raw_response=text)


# ── 리뷰어(결정론적 검증 게이트) ─────────────────────────────
# 매 호출마다 항상 1회 검증한다(성공·실패 무관). 통과면 [], 문제면 메시지 리스트.
# MISSING_INFO / IRRELEVANT는 정상 종료 상태이므로 재시도 대상이 아니다.
_MAX_REVIEW_RETRIES = 1


def _review_labor(structured: dict) -> list:
    problems = []
    status = structured.get("status")

    if status == "ERROR":
        problems.append(
            "JSON 형식으로 응답하지 않았거나 파싱에 실패했습니다. 지정된 JSON 스키마만 출력하세요."
        )
        return problems

    if status in ("CALCULATED", "PARTIAL"):
        items = structured.get("cost_items") or []
        if not items:
            problems.append("status가 CALCULATED/PARTIAL인데 cost_items가 비어 있습니다.")

        total = structured.get("total_cost")
        item_sum = sum(it.get("amount") for it in items if isinstance(it.get("amount"), (int, float)))
        if items and not isinstance(total, (int, float)):
            problems.append(
                f"status가 CALCULATED/PARTIAL인데 total_cost가 null입니다. "
                f"cost_items amount 합계({int(item_sum):,})를 total_cost에 설정하세요."
            )
        if items and isinstance(total, (int, float)) and int(total) != int(item_sum):
            problems.append(
                f"total_cost({int(total):,})가 cost_items 합계({int(item_sum):,})와 일치하지 않습니다."
            )

        for it in items:
            for k in ("quantity", "unit_price", "amount"):
                v = it.get(k)
                if isinstance(v, (int, float)) and v < 0:
                    problems.append(f"{k} 값이 음수입니다({v}).")
            # 산식 정합성(amount ≈ 수량 × 단가) — 환각·오계산 탐지
            up, qty, amt = it.get("unit_price"), it.get("quantity"), it.get("amount")
            if all(isinstance(x, (int, float)) for x in (up, qty, amt)):
                expected = up * qty
                if abs(amt - expected) > max(1.0, abs(expected) * 0.01):
                    problems.append(
                        f"항목 '{it.get('name', '?')}'의 amount({amt})가 수량×단가({expected})와 "
                        f"일치하지 않습니다(환각·오계산 의심). calculate_labor_cost 결과로 다시 계산하세요."
                    )

        # 노임단가 DB 근거 검사: 단가가 있는데 labor_db 근거가 없으면 툴 미조회로 간주.
        ev = structured.get("evidence") or []
        has_labor_db = any(
            isinstance(e, dict) and str(e.get("type", "")).strip().lower() == "labor_db"
            for e in ev
        )
        priced = any(isinstance(it.get("unit_price"), (int, float)) and it.get("unit_price") > 0 for it in items)
        if priced and not has_labor_db:
            problems.append(
                "노임단가를 DB로 조회한 근거(evidence type=labor_db)가 없습니다. "
                "get_labor_price 툴로 각 직종 단가를 조회해 적용하고, 그 결과를 evidence에 포함하세요."
            )
    return problems


def _run_labor_once(messages: list) -> tuple:
    """인건비 에이전트 1회 실행 → (response_text, structured_dict)."""
    result = _labor_cost_node({'messages': messages})
    msgs = result.get('messages', [])
    last_ai = next(
        (m for m in reversed(msgs)
         if isinstance(m, AIMessage) and not getattr(m, 'tool_calls', None)),
        None,
    )
    raw_content = last_ai.content if last_ai else '[인건비 에이전트 응답 없음]'
    response = _message_content_to_text(raw_content)
    return response, _parse_json_response(response)


# ── 노드 함수 ────────────────────────────────────────────────
def labor_cost_node(state: dict) -> dict:
    log.debug('labor_cost_node 진입')
    print('\n[인건비 에이전트] 처리 시작')

    try:
        messages = list(state['messages'])
        response, structured = _run_labor_once(messages)

        # 항상 1회 리뷰. 문제가 있으면 피드백 붙여 재시도(최대 _MAX_REVIEW_RETRIES회).
        for attempt in range(1, _MAX_REVIEW_RETRIES + 1):
            problems = _review_labor(structured)
            if not problems:
                break
            log.warning(f'[리뷰어] 인건비 검증 실패(시도 {attempt}): {problems}')
            print(f'[인건비 에이전트] 검증 실패 → 재시도 {attempt}/{_MAX_REVIEW_RETRIES}')
            feedback = HumanMessage(content=(
                '[검토 피드백] 직전 응답에 다음 문제가 있습니다. 반드시 고쳐서 '
                '지정된 JSON 스키마로만 다시 답하세요:\n- ' + '\n- '.join(problems)
            ))
            messages = messages + [feedback]
            response, structured = _run_labor_once(messages)
        else:
            remaining = _review_labor(structured)
            if remaining:
                structured.setdefault('warnings', []).append(
                    '자동 검토 재시도 후에도 일부 문제가 남아 있습니다: ' + '; '.join(remaining)
                )

        log.debug('labor_cost_node 종료')
        print('[인건비 에이전트] 완료')

        return {
            'labor_cost_response': response,
            'labor_cost_result':   structured,
        }

    except Exception as e:
        log.exception(f"labor_cost_node 실행 실패: {e}")
        fallback = _default_result(
            status="ERROR",
            summary=f"인건비 에이전트 실행 중 오류가 발생했습니다: {str(e)}",
        )
        print('[인건비 에이전트] 실패')
        return {
            'labor_cost_response': fallback["summary"],
            'labor_cost_result':   fallback,
        }
