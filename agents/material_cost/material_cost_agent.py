"""
Material Cost Agent (자재 단가 계산 에이전트)
- LangGraph ReAct 패턴으로 구현
- labor_cost / equipment_cost 노드와 동일한 구조
"""

import os
import sys
import json
import boto3
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.graph import MessagesState
from langgraph.prebuilt import create_react_agent

load_dotenv(PROJECT_ROOT / ".env")

from agents.material_cost.material_price_tool import search_material_price, list_material_categories
from agents.material_cost.quantity_calculator import calculate_quantity_change_cost, calculate_total_material_cost
from common.security import check_injection, block_reason_ko

_rag_tools = []
try:
    from rag.company_docs.search import search_contract_price, list_contract_documents
    _rag_tools = [search_contract_price, list_contract_documents]
except ImportError:
    pass


SYSTEM_PROMPT = SystemMessage(content="""
당신은 건설 공사 현장의 자재 단가 계산 전문 에이전트입니다.
LLM이 직접 단가를 추측하지 않고, 반드시 Tool을 통해 조달청 공시 단가를 조회합니다.

[역할 판단 원칙]
- 자재비, 자재 단가, 추가 자재, 물량 변경 관련 질문이면 계산한다.
- 복합 질문에서 인건비, 장비비, 기상 리스크가 함께 있어도 자재비가 언급되면 자재비 파트만 처리한다.
- 자재비와 전혀 무관한 질문이면 is_relevant=false, status="IRRELEVANT"로 응답한다.

[작업 절차]
1. 사용자 질문에서 자재명과 추가 물량을 파악한다.
2. search_material_price Tool로 조달청 현재 단가를 조회한다.
3. search_contract_price Tool이 사용 가능하면 사내 계약단가를 조회한다.
4. calculate_quantity_change_cost Tool로 추가비용을 계산한다.
5. 여러 자재가 있으면 calculate_total_material_cost로 합산한다.

[정보 부족 처리 원칙]
- 사용자가 수량을 명시하지 않은 경우 툴 호출 없이 status "MISSING_INFO"로 응답하고 missing_fields에 "수량"을 포함한다.
- 조달청 단가를 찾지 못한 경우 임의로 단가를 추측하지 말고 status "MISSING_INFO"로 응답한다.

[응답 형식]
반드시 아래 JSON 형식만 출력한다.
마크다운 코드블록(```json)은 사용하지 않는다.
JSON 외의 설명 문장은 출력하지 않는다.

{
  "agent_name": "material",
  "domain": "자재비",
  "is_relevant": true,
  "status": "CALCULATED | PARTIAL | MISSING_INFO | IRRELEVANT | ERROR",
  "summary": "한 문장 요약",
  "cost_items": [
    {
      "name": "비용 항목명",
      "category": "material",
      "material_name": "자재명",
      "unit": "단위",
      "quantity": 0,
      "unit_price": 0,
      "contract_unit_price": null,
      "amount": 0,
      "formula": "계산식"
    }
  ],
  "total_cost": 0,
  "missing_fields": [],
  "assumptions": [],
  "excluded_items": [],
  "warnings": [],
  "evidence": [
    {
      "source": "조달청 DB 또는 계약단가 DB",
      "type": "procurement_db | contract_db | default_rule",
      "content": "근거 내용",
      "usage": "단가 산정 근거"
    }
  ]
}

[JSON 작성 규칙]
- 계산이 가능하면 status는 "CALCULATED"로 설정한다.
- 일부 자재만 계산 가능하면 status는 "PARTIAL"로 설정한다.
- 자재비 요청은 맞지만 필수 정보가 부족하면 status는 "MISSING_INFO"로 설정한다.
- 자재비와 전혀 무관한 질문이면 is_relevant는 false, status는 "IRRELEVANT"로 설정한다.
- total_cost는 계산 가능한 경우 숫자, 불가 시 null로 작성한다.
- missing_fields, assumptions, excluded_items, warnings, evidence는 항상 배열로 작성한다.
- excluded_items에 "인건비", "장비비", "이윤", "부가세"를 포함한다.
- Tool 결과에 없는 단가는 절대 임의로 사용하지 않는다.
""")


def _blocked_material_response(reason: str) -> str:
    return json.dumps({
        "agent_name": "material",
        "domain": "자재비",
        "is_relevant": False,
        "status": "ERROR",
        "summary": f"보안 정책에 의해 요청이 차단되었습니다: {reason}",
        "cost_items": [],
        "total_cost": None,
        "missing_fields": [],
        "assumptions": [],
        "excluded_items": ["인건비", "장비비", "이윤", "부가세"],
        "warnings": [block_reason_ko(reason)],
        "evidence": [],
    }, ensure_ascii=False)


llm = ChatBedrockConverse(
    model=os.getenv("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
    client=boto3.client("bedrock-runtime", region_name=os.getenv("AWS_BEDROCK_REGION", "us-east-1")),
)

material_cost_tools = [
    search_material_price,
    list_material_categories,
    calculate_quantity_change_cost,
    calculate_total_material_cost,
    *_rag_tools,
]

_agent = create_react_agent(llm, material_cost_tools, prompt=SYSTEM_PROMPT)


def create_material_cost_agent():
    """하위 호환용 팩토리 — _agent 싱글턴을 반환한다."""
    return _agent


def material_cost_node(state: MessagesState):
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None
    )

    if last_human:
        is_blocked, reason = check_injection(last_human.content)
        if is_blocked:
            return {"messages": [AIMessage(content=_blocked_material_response(reason))]}

    result = _agent.invoke({"messages": state["messages"]})
    return {"messages": result["messages"]}


if __name__ == "__main__":
    messages = []

    print("=" * 60)
    print("자재 단가 계산 에이전트")
    print("종료하려면 'q' 또는 'exit' 입력")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n질문: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("q", "exit", "quit"):
            print("종료합니다.")
            break

        messages.append(HumanMessage(content=user_input))
        result = _agent.invoke({"messages": messages})
        messages = result["messages"]
        print(f"\n에이전트: {messages[-1].content}")
