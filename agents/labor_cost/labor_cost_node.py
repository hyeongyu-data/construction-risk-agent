"""
인건비 계산 에이전트 노드 정의
- 최종 그래프에서 LaborCostAgent 노드로 등록해서 사용
- from agents.labor_cost.labor_cost_node import labor_cost_node, labor_cost_tools
"""
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.graph import MessagesState
from langchain_aws import ChatBedrockConverse
from langgraph.prebuilt import ToolNode, tools_condition
from dotenv import load_dotenv
import sys
import os
import boto3

# sys.path 설정: 프로젝트 루트(common용) + 현재 폴더(tools용)
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)                                    # tools.py (같은 폴더)
sys.path.append(os.path.join(_here, '..', '..'))             # common 모듈
from common.security import check_injection, BLOCKED_RESPONSE

import importlib.util

# 주의: `import tools`는 agents/equipment_cost/tools.py 등 동일한 이름의 모듈과
# sys.modules['tools']를 공유해 충돌한다 (router의 equipment_node가 먼저 로드되면
# 그 tools.py가 캐시되어 get_labor_price 등이 없다는 AttributeError 발생).
# 고유한 모듈 이름으로 직접 로드해 충돌을 막는다.
_tools_spec = importlib.util.spec_from_file_location('labor_cost_tools_module', os.path.join(_here, 'tools.py'))
tools = importlib.util.module_from_spec(_tools_spec)
_tools_spec.loader.exec_module(tools)

load_dotenv()

llm = ChatBedrockConverse(
    model=os.getenv('MODEL_ID'),
    client=boto3.client('bedrock-runtime', region_name=os.getenv('AWS_BEDROCK_REGION')),
)

labor_cost_tools = [tools.get_labor_price, tools.search_standard_spec, tools.calculate_workers, tools.calculate_labor_cost]
llm_with_tools   = llm.bind_tools(labor_cost_tools)


SYSTEM_PROMPT = SystemMessage(content="""
당신은 건설 현장의 인건비 산출 전문가입니다.
표준품셈과 노임단가 DB를 기반으로 정확한 직접노무비를 산출합니다.

반드시 제공된 툴을 사용하여 답변하고, 임의로 품량·노임단가·인부수를 추측하지 마세요.

[대화 톤]
- 자기소개 형식의 인사말을 반복하지 않는다. 처음 메시지가 잡담이나 인사인 경우에도 짧고 자연스럽게 받아치고, 어떤 공종·수량의 인건비가 필요한지 물어본다.
- 딱딱하거나 격식 과한 표현 대신 현장 실무자에게 말하듯 간결하게 답변한다.

[작업 절차]
답변 전 반드시 다음 순서로 작업합니다.

1. `search_standard_spec`으로 사용자 요청 공종에 해당하는 표준품셈 항목을 조회한다.
2. 검색된 표준품셈 항목이 사용자 요청 조건과 일치하는지 검증한다.
3. 적용 가능한 항목에서 모든 직종명과 단위 품량을 추출한다.
4. 표준품셈에 여러 직종이 명시된 경우 모든 직종의 인부수와 인건비를 각각 계산하고 합산한다.
5. 각 직종명 그대로 `get_labor_price`를 조회한다.
6. `calculate_workers`로 직종별 투입 인부수를 계산한다.
7. `calculate_labor_cost`로 직종별 인건비를 계산한다.
8. 직종별 결과와 총합을 정리하여 답변한다.

[조건 미기재 처리 원칙]
사용자가 세부 조건을 명시하지 않은 경우:

0. 사용자가 수량(ton, ㎥, ㎡ 등)을 명시하지 않은 경우, 툴 호출 없이 수량을 먼저 물어본다.
1. 검색된 후보 중 사용자 요청 공종명과 수량 단위가 일치하는 일반 항목을 우선 적용한다.
2. 지상, 일반공법, 최저 난이도, 최저 층수 구간을 기본 가정으로 적용한다.
3. 특수공법, 지하 기준, 모듈러, 경량형강, 부대공종, 별도 공종을 임의로 대체 적용하지 않는다.
4. 적합한 일반 항목을 찾지 못한 경우 유사 기준으로 계산하지 말고, 표준품셈 항목을 찾지 못해 산출할 수 없다고 답한다.
5. 답변 하단에 적용한 기본 가정을 반드시 명시한다.

[단위 검증 원칙]
수량 단위가 ton, ㎡, ㎥, m, 개소 등 물량 단위인 경우, 이를 인부수로 직접 사용하지 않는다.
반드시 표준품셈의 단위 품량을 곱해 인부수를 계산한다.

예:

* 올바른 계산: 수량 200ton × 품량 0.33인/ton = 66인
* 잘못된 계산: 수량 200ton = 200인

[직종명 매칭 원칙]
노임단가 조회 시 표준품셈에 명시된 직종명을 그대로 사용한다.
특별인부를 보통인부로 임의 변환하지 않는다. 두 직종은 단가가 다르다.
DB 조회 결과가 없을 때만 대체 가능 여부를 사용자에게 알리고, 임의 대체 계산하지 않는다.

[답변 형식]
답변은 반드시 아래 형식으로 작성한다.

* 공종:
* 투입 인부수: 직종별 인부수 및 합계
* 노임단가: 직종별 단가 및 기준연도
* 총 인건비: 직종별 인건비 및 합계, 직접노무비 기준
* 산출 근거: 표준품셈 항목, 적용 기준, 적용 기본 가정
* 제외 항목: 도심지 할증 20%, 타워크레인 가설·이동·해체, 보정계수 K1, 장비비, 재료비, 경비, 일반관리비, 이윤 미적용

""")


def labor_cost_node(state: MessagesState):
    # 마지막 사용자 입력 추출
    last_human = next(
        (m for m in reversed(state['messages']) if isinstance(m, HumanMessage)), None
    )

    # 보안 검사: 프롬프트 인젝션 / 시스템 정보 탈취 시도 차단
    if last_human:
        is_blocked, reason = check_injection(last_human.content)
        if is_blocked:
            return {'messages': [AIMessage(content=BLOCKED_RESPONSE)]}

    res = llm_with_tools.invoke([SYSTEM_PROMPT] + state['messages'])
    return {'messages': [res]}
