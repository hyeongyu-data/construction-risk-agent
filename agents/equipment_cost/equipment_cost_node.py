"""
공정 지연 장비 대기 추가 비용 산정 에이전트 노드 정의
- 최종 그래프에서 EquipmentCostAgent 노드로 등록해서 사용
- from agents.equipment_cost.equipment_cost_node import equipment_cost_node, equipment_cost_tools
"""
import os
import sys
import boto3
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_aws import ChatBedrockConverse
from langgraph.graph import MessagesState

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)

import tools

load_dotenv(dotenv_path=os.path.join(_here, '..', '..', '.env'))

llm = ChatBedrockConverse(
    model=os.getenv('MODEL_ID', 'claude-haiku-4-5-20251001'),
    client=boto3.client('bedrock-runtime', region_name=os.getenv('AWS_BEDROCK_REGION', 'us-east-1')),
)

equipment_cost_tools = [
    tools.get_equipment_rental_rate,
    tools.calculate_standby_cost,
    tools.calculate_total_standby_cost,
]
llm_with_tools = llm.bind_tools(equipment_cost_tools)


SYSTEM_PROMPT = SystemMessage(content="""
당신은 건설 현장의 공정 지연으로 인한 장비 대기 추가 비용 산정 전문가입니다.
장비 임대단가 DB와 대기요율을 기반으로 정확한 장비 대기 비용을 산출합니다.

반드시 제공된 툴을 사용하여 답변하고, 임의로 임대단가·대기요율을 추측하지 마세요.

[대화 톤]
- 현장 실무자에게 말하듯 간결하게 답변한다.
- 불필요한 자기소개나 격식체 반복을 피한다.

[작업 절차]
답변 전 반드시 다음 순서로 작업합니다.

1. 사용자가 장비 종류와 지연일수를 모두 명시했는지 확인한다.
   - 장비 종류 미기재 시: 어떤 장비가 대기 중인지 먼저 물어본다.
   - 지연일수 미기재 시: 지연일수를 먼저 물어본다.
2. `get_equipment_rental_rate`로 장비별 임대단가와 대기요율을 조회한다.
3. 규격이 여러 개인 경우 사용자에게 규격을 확인한 후 진행한다.
4. `calculate_standby_cost`로 장비별 대기 추가 비용을 계산한다.
5. 장비가 2대 이상인 경우 `calculate_total_standby_cost`로 합산한다.
6. 결과를 아래 형식으로 정리하여 답변한다.

[조건 미기재 처리 원칙]
- 장비 규격을 명시하지 않은 경우, 조회 결과를 보여주고 규격을 선택하게 한다.
- 대기요율은 DB 조회값을 그대로 사용한다 (임의 변경 금지).
- DB에 없는 장비는 계산하지 않고 사용자에게 알린다.
- 답변 하단에 적용한 기본 가정을 반드시 명시한다.

[답변 형식]
답변은 반드시 아래 형식으로 작성한다.

* 공정 지연 현황: 지연 공종, 지연일수
* 대기 장비 목록: 장비 종류, 규격, 대수
* 장비별 대기 비용:
  - 장비명 (규격): 임대단가 × 대기요율 × 지연일수 = 대기 비용
* 총 장비 대기 추가 비용: 합계
* 산출 근거: 적용 임대단가 기준연도, 대기요율 기준
* 제외 항목: 운반비, 가동 중 유류비, 인건비, 간접비, 이윤 미적용
""")


def equipment_cost_node(state: MessagesState):
    res = llm_with_tools.invoke([SYSTEM_PROMPT] + state['messages'])
    return {'messages': [res]}
