"""
Material Cost Agent (자재 단가 계산 에이전트)
- LangGraph ReAct 패턴으로 구현
- 자연어 질문 → Tool 호출 → 추가 자재비 계산 → 공무용 리포트 생성
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_aws import ChatBedrock
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

# 프로젝트 루트의 .env 로드
load_dotenv(PROJECT_ROOT / ".env")

# Tools import
from agents.material_cost.material_price_tool import search_material_price, list_material_categories
from agents.material_cost.quantity_calculator import calculate_quantity_change_cost, calculate_total_material_cost
from rag.company_docs.search import search_contract_price, list_contract_documents


# ── 시스템 프롬프트 ──────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 건설 공사 현장의 자재 단가 계산 전문 에이전트입니다.

## 역할
- 공무 담당자의 자연어 질문을 받아, 추가 자재비를 정확하게 계산합니다.
- LLM이 직접 단가를 추측하지 않고, 반드시 Tool을 통해 조달청 공시 단가를 조회합니다.
- 계산 결과를 공무용 리포트 형식으로 정리합니다.

## 처리 절차
1. 사용자 질문에서 자재명과 추가 물량을 파악합니다.
2. `search_material_price` Tool로 조달청 현재 단가를 조회합니다.
3. `search_contract_price` Tool로 사내 과거 계약단가(전체 공사별)를 조회합니다.
4. `calculate_quantity_change_cost` Tool로 추가비용을 계산합니다.
5. 여러 자재가 있으면 `calculate_total_material_cost`로 합산합니다.
6. 결과를 공무용 리포트로 정리합니다.

## 리포트 형식
계산 완료 후 반드시 아래 형식으로 출력하세요:

---
## 📋 자재 추가비용 산정 리포트
**산정일시**: [현재일시]
**질의 내용**: [사용자 질문 요약]

### 자재 단가 조회 결과
| 항목 | 내용 |
|------|------|
| 자재명 | [자재명] |
| 단위 | [단위] |
| 현재단가 (조달청) | [금액]원 |
| 공사별 계약단가 | [공사명 연도: 금액원, 공사명 연도: 금액원, ...] |
| 계약단가 평균 | [평균금액]원 (N개 공사 기준) / 미확인 |
| 시황성 자재 여부 | 예/아니오 |

### 추가비용 계산
| 항목 | 금액 |
|------|------|
| 계약단가 기준 추가자재비 | [금액]원 |
| 현재단가 기준 추가자재비 | [금액]원 |
| 단가 차액 | [금액]원 |

### 주의사항
[주의사항 나열]

### 검토 의견
[계약 조건 확인 필요 사항, 시황성 자재 관련 의견]
---

## 중요 원칙
- Tool 결과에 없는 단가는 절대 임의로 사용하지 않습니다.
- 계약단가가 없으면 "계약 DB 미연동 - 팀원 B 확인 필요"라고 명시합니다.
- 부가세 포함 여부를 항상 명시합니다.
"""


def create_material_cost_agent():
    """Material Cost Agent 생성 및 반환."""
    llm = ChatBedrock(
        model_id=os.getenv("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
        region_name=os.getenv("AWS_BEDROCK_REGION", "us-east-1"),
        model_kwargs={"temperature": 0},  # 계산 일관성을 위해 temperature=0
    )

    tools = [
        search_material_price,
        list_material_categories,
        calculate_quantity_change_cost,
        calculate_total_material_cost,
        search_contract_price,
        list_contract_documents,
    ]

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SYSTEM_PROMPT,
    )
    return agent


def run_material_cost_agent(user_query: str, verbose: bool = True) -> dict:
    """
    자재 단가 계산 에이전트 실행.

    Args:
        user_query: 공무 담당자의 자연어 질문
                    예) "H파일이 추가로 500ton 필요한데 추가비용 계산해줘"
        verbose: Tool 호출 과정 출력 여부

    Returns:
        {
            "query": str,
            "report": str,          # 공무용 리포트 (마크다운)
            "tool_calls": list,     # 사용된 Tool 목록
            "timestamp": str,
        }
    """
    agent = create_material_cost_agent()

    if verbose:
        print(f"\n{'='*60}")
        print(f"[Material Cost Agent] 질의 처리 시작")
        print(f"질의: {user_query}")
        print(f"{'='*60}\n")

    # 에이전트 실행
    result = agent.invoke({"messages": [HumanMessage(content=user_query)]})

    # 마지막 AI 메시지 추출 (최종 리포트)
    final_message = result["messages"][-1].content

    # Tool 호출 이력 추출
    tool_calls_used = []
    for msg in result["messages"]:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls_used.append(tc.get("name", "unknown"))

    if verbose:
        print("\n[최종 리포트]")
        print(final_message)

    return {
        "query": user_query,
        "report": final_message,
        "tool_calls": tool_calls_used,
        "timestamp": datetime.now().isoformat(),
    }


# ── 직접 실행 테스트 ──────────────────────────────────────────────
if __name__ == "__main__":
    # 테스트할 질의를 아래에서 선택 (index 변경)
    test_queries = [
        # [0] 기본 - 추가 물량 자재비 계산
        "이번 공정에서 ㄱ형강이 추가로 500ton 필요한데, 이에 따른 추가비용 계산해줘.",
        # [1] 자재명 + 단위 명시
        "방수재가 추가로 300㎡ 필요해. 계약단가랑 현재단가 기준으로 각각 얼마야?",
        # [2] 여러 자재 동시 조회
        "합판이랑 시멘트가 각각 100매, 50포대 추가로 필요한데 총 추가비용 계산해줘.",
        # [3] 자재 카테고리 확인
        "조회 가능한 자재 종류가 뭐가 있어?",
        # [4] 시황성 자재 여부 확인
        "철근은 시황성 자재야? 현재 단가도 알려줘.",
    ]

    # 테스트할 번호 선택 (0~4)
    TEST_INDEX = 2

    run_material_cost_agent(test_queries[TEST_INDEX], verbose=True)