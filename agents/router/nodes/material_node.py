"""
자재 단가 에이전트 노드
- agents/material_cost/ 의 툴을 직접 임포트
- 조달청 공시 단가 조회 + 추가 자재비 계산
"""
import os
import sys
import boto3
from dotenv import load_dotenv
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent
from logger import get_logger

log = get_logger(__name__)

# ── 경로 설정 ─────────────────────────────────────────────────────
_HERE         = os.path.dirname(os.path.abspath(__file__))
_ROOT         = os.path.abspath(os.path.join(_HERE, '../../..'))
_AGENTS       = os.path.abspath(os.path.join(_HERE, '../..'))

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _AGENTS not in sys.path:
    sys.path.insert(0, _AGENTS)

load_dotenv(dotenv_path=os.path.join(_ROOT, '.env'))

# ── 툴 임포트 ─────────────────────────────────────────────────────
from agents.material_cost.material_price_tool import (
    search_material_price,
    list_material_categories,
)
from agents.material_cost.quantity_calculator import (
    calculate_quantity_change_cost,
    calculate_total_material_cost,
)

_TOOLS = [
    search_material_price,
    list_material_categories,
    calculate_quantity_change_cost,
    calculate_total_material_cost,
]

# RAG 계약단가 툴 (없으면 건너뜀)
try:
    from rag.company_docs.search import search_contract_price, list_contract_documents
    _TOOLS += [search_contract_price, list_contract_documents]
    log.debug('RAG 계약단가 툴 로드 완료')
except ImportError:
    log.debug('RAG 계약단가 툴 없음 — 조달청 단가만 사용')

# ── LLM 초기화 ────────────────────────────────────────────────────
_llm = ChatBedrockConverse(
    model=os.getenv('MODEL_ID', 'us.anthropic.claude-haiku-4-5-20251001-v1:0'),
    client=boto3.client(
        'bedrock-runtime',
        region_name=os.getenv('AWS_BEDROCK_REGION', 'us-east-1'),
    ),
)

# ── 시스템 프롬프트 ───────────────────────────────────────────────
_PROMPT = SystemMessage(content="""
당신은 건설 공사 현장의 자재 단가 계산 전문 에이전트입니다.

[역할 판단 원칙]
- 자재 단가, 추가 물량, 자재비 계산 관련 질문이면 계산한다.
- 인건비, 장비 대기, 기상 리스크 등 자재 비용과 무관한 질문은
  "이 질문은 자재 단가 도메인이 아닙니다."라고 짧게 응답하고 종료한다.

[작업 절차]
1. 자재명과 추가 물량을 파악한다.
2. search_material_price 로 조달청 현재 단가를 조회한다.
3. search_contract_price 가 사용 가능하면 사내 과거 계약단가도 조회한다.
4. calculate_quantity_change_cost 로 추가비용을 계산한다.
5. 자재가 여러 개면 calculate_total_material_cost 로 합산한다.

[답변 형식]
* 자재명 / 단위 / 조달청 현재단가
* 계약단가 (있으면 공사별 목록, 없으면 "계약 DB 미연동" 명시)
* 시황성 자재 여부
* 현재단가 기준 추가자재비 (부가세 별도)
* 계약단가 기준 추가자재비 (계약단가 있을 때만)
* 단가 차이 및 변동률
* 주의사항 (시황성 자재, 계약 유형, 부가세 등)

[중요 원칙]
- Tool 결과에 없는 단가는 절대 임의로 사용하지 않는다.
- 부가세 포함 여부를 항상 명시한다.
""")

_agent = create_react_agent(_llm, _TOOLS, prompt=_PROMPT)


# ── 노드 함수 ─────────────────────────────────────────────────────
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
