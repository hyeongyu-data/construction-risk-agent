"""
자재 단가 에이전트 노드 (router 위임자)
- agents/material_cost/material_cost_agent.py의 material_cost_node를 호출
- 결과를 material_response(문자열) + material_result(구조화 dict)로 변환해 RiskState에 반환
- labor_cost_node / equipment_node와 동일한 위임 구조
"""
import os
import sys
import json
import re
import importlib.util
from langchain_core.messages import AIMessage
from logger import get_logger

log = get_logger(__name__)

_ROUTER_ROOT   = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_MATERIAL_PATH = os.path.abspath(os.path.join(_ROUTER_ROOT, '..', 'material_cost'))
_PROJECT_ROOT  = os.path.abspath(os.path.join(_ROUTER_ROOT, '..', '..'))

if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_material_spec = importlib.util.spec_from_file_location(
    'actual_material_cost_node_module',
    os.path.join(_MATERIAL_PATH, 'material_cost_agent.py'),
)
_material_module = importlib.util.module_from_spec(_material_spec)
_material_spec.loader.exec_module(_material_module)

_material_cost_node = _material_module.material_cost_node


# ── 헬퍼: content 타입 정규화 ────────────────────────────────
def _message_content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict):
                texts.append(part.get('text', ''))
            else:
                texts.append(str(part))
        return '\n'.join(texts).strip()
    return str(content)


# ── 헬퍼: JSON 파싱 ──────────────────────────────────────────
def _clean_json_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', cleaned, flags=re.MULTILINE).strip()
    start = cleaned.find('{')
    end   = cleaned.rfind('}')
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
                'source':  item.get('source', 'unknown'),
                'type':    item.get('type', 'unknown'),
                'content': item.get('content', ''),
                'usage':   item.get('usage', ''),
            })
        else:
            normalized.append({
                'source':  'unknown',
                'type':    'unknown',
                'content': str(item),
                'usage':   'LLM 응답 근거',
            })
    return normalized


def _default_result(*, status='ERROR', summary='자재 에이전트 처리 중 오류가 발생했습니다.',
                    raw_response='', is_relevant=False) -> dict:
    return {
        'agent_name':    'material',
        'domain':        '자재비',
        'is_relevant':   is_relevant,
        'status':        status,
        'summary':       summary,
        'cost_items':    [],
        'total_cost':    None,
        'missing_fields': [],
        'assumptions':   [],
        'excluded_items': ['인건비', '장비비', '이윤', '부가세'],
        'warnings':      ['자재 에이전트 응답을 구조화하는 과정에서 문제가 발생했습니다.'],
        'evidence':      [],
        'raw_response':  raw_response,
    }


def _normalize_result(data: dict, raw_response: str) -> dict:
    data.setdefault('agent_name', 'material')
    data.setdefault('domain', '자재비')
    data.setdefault('status', 'ERROR')
    data.setdefault('summary', '')
    data.setdefault('cost_items', [])
    data.setdefault('total_cost', None)
    data.setdefault('missing_fields', [])
    data.setdefault('assumptions', [])
    data.setdefault('excluded_items', [])
    data.setdefault('warnings', [])
    data.setdefault('evidence', [])

    if not isinstance(data['cost_items'], list):
        data['cost_items'] = []

    data['missing_fields'] = _ensure_list(data['missing_fields'])
    data['assumptions']    = _ensure_list(data['assumptions'])
    data['excluded_items'] = _ensure_list(data['excluded_items'])
    data['warnings']       = _ensure_list(data['warnings'])
    data['evidence']       = _normalize_evidence(data['evidence'])

    allowed = {'CALCULATED', 'PARTIAL', 'MISSING_INFO', 'IRRELEVANT', 'ERROR'}
    if data['status'] not in allowed:
        data['status'] = 'ERROR'
        data['warnings'].append('허용되지 않은 status 값이 반환되어 ERROR로 보정했습니다.')

    if data['status'] in {'CALCULATED', 'PARTIAL', 'MISSING_INFO'}:
        data['is_relevant'] = True
    elif data['status'] == 'IRRELEVANT':
        data['is_relevant'] = False
    else:
        data.setdefault('is_relevant', False)

    for item in ['인건비', '장비비', '이윤', '부가세']:
        if item not in data['excluded_items']:
            data['excluded_items'].append(item)

    data['raw_response'] = raw_response
    data = _validate_cost_items(data)
    return data


def _validate_cost_items(data: dict) -> dict:
    warnings = data.setdefault('warnings', [])
    total_from_items = 0
    has_amount = False

    for item in data.get('cost_items', []):
        for key in ['quantity', 'unit_price', 'amount']:
            value = item.get(key)
            if isinstance(value, (int, float)) and value < 0:
                warnings.append(f'{key} 값이 음수입니다: {value}')

        amount = item.get('amount')
        if isinstance(amount, (int, float)):
            total_from_items += amount
            has_amount = True

    if has_amount and isinstance(data.get('total_cost'), (int, float)):
        if int(data['total_cost']) != int(total_from_items):
            warnings.append(
                f'total_cost({data["total_cost"]:,})와 cost_items amount 합계({total_from_items:,})가 일치하지 않습니다.'
            )

    return data


def _parse_json_response(text: str) -> dict:
    try:
        cleaned = _clean_json_text(text)
        data    = json.loads(cleaned)
        if not isinstance(data, dict):
            return _default_result(status='ERROR', summary='응답이 JSON 객체가 아닙니다.',
                                   raw_response=text)
        return _normalize_result(data, text)
    except Exception as e:
        log.exception(f'material_node JSON 파싱 실패: {e}')
        return _default_result(status='ERROR', summary='응답을 JSON으로 파싱하지 못했습니다.',
                               raw_response=text)


# ── 노드 함수 ────────────────────────────────────────────────
def material_node(state: dict) -> dict:
    log.debug('material_node 진입')
    print('\n[자재 에이전트] 처리 시작')

    try:
        result   = _material_cost_node(state)
        messages = result.get('messages', [])

        last_ai = next(
            (m for m in reversed(messages)
             if isinstance(m, AIMessage) and not getattr(m, 'tool_calls', None)),
            None,
        )

        raw_content = last_ai.content if last_ai else '[자재 에이전트 응답 없음]'
        response    = _message_content_to_text(raw_content)
        structured  = _parse_json_response(response)

        log.debug('material_node 종료')
        print('[자재 에이전트] 완료')

        return {
            'material_response': response,
            'material_result':   structured,
        }

    except Exception as e:
        log.exception(f'material_node 실행 실패: {e}')
        fallback = _default_result(
            status='ERROR',
            summary=f'자재 에이전트 실행 중 오류가 발생했습니다: {str(e)}',
        )
        print('[자재 에이전트] 실패')
        return {
            'material_response': fallback['summary'],
            'material_result':   fallback,
        }
