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
from langchain_core.messages import AIMessage
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


# ── 노드 함수 ────────────────────────────────────────────────
def labor_cost_node(state: dict) -> dict:
    log.debug('labor_cost_node 진입')
    print('\n[인건비 에이전트] 처리 시작')

    try:
        result   = _labor_cost_node(state)
        messages = result.get('messages', [])

        last_ai = next(
            (m for m in reversed(messages)
             if isinstance(m, AIMessage) and not getattr(m, 'tool_calls', None)),
            None,
        )

        raw_content = last_ai.content if last_ai else '[인건비 에이전트 응답 없음]'
        response    = _message_content_to_text(raw_content)
        structured  = _parse_json_response(response)

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
