"""
공정 지연 장비 대기 추가 비용 산정 에이전트 노드 정의
- 최종 그래프에서 EquipmentCostAgent 노드로 등록해서 사용
- from agents.equipment_cost.equipment_cost_node import equipment_cost_node, equipment_cost_tools

인건비(labor_cost) 에이전트와 동일한 구조:
  - 정식 구현은 이 파일에 두고, router/nodes/equipment_node.py가 thin 위임자로 호출한다.
"""
import os
import sys
import boto3
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.graph import MessagesState
from langchain_aws import ChatBedrockConverse
from langgraph.prebuilt import create_react_agent

# sys.path 설정: 프로젝트 루트(common용) + 현재 폴더(tools용)
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)                                    # tools.py (같은 폴더)
sys.path.append(os.path.join(_here, '..', '..'))             # common 모듈
from common.security import check_injection, BLOCKED_RESPONSE

import importlib.util

# 주의: `import tools`는 agents/labor_cost/tools.py 등 동일한 이름의 모듈과
# sys.modules['tools']를 공유해 충돌한다 (labor_cost_node와 함께 그래프에 로드되면
# 먼저 캐시된 tools.py가 바인딩되어 잘못된 함수가 호출됨).
# 고유한 모듈 이름으로 직접 로드해 충돌을 막는다.
_tools_spec = importlib.util.spec_from_file_location('equipment_cost_tools_module', os.path.join(_here, 'tools.py'))
tools = importlib.util.module_from_spec(_tools_spec)
_tools_spec.loader.exec_module(tools)

load_dotenv(dotenv_path=os.path.join(_here, '..', '..', '.env'))

llm = ChatBedrockConverse(
    model=os.getenv('MODEL_ID', 'us.anthropic.claude-haiku-4-5-20251001-v1:0'),
    client=boto3.client('bedrock-runtime', region_name=os.getenv('AWS_BEDROCK_REGION', 'us-east-1')),
)

equipment_cost_tools = [
    tools.get_equipment_by_work_type,
    tools.get_equipment_rental_rate,
    tools.get_equipment_cost_range,
    tools.calculate_standby_cost,
    tools.calculate_total_standby_cost,
]


SYSTEM_PROMPT = SystemMessage(content="""
당신은 건설 현장 공정 지연으로 인한 장비 대기 추가 비용 산정 전문가입니다.

[역할 판단 원칙]
- 장비 대기, 장비 임대, 공정 지연으로 인한 장비 비용이 포함된 질문이면 계산한다.
- 인건비, 자재 가격 등 장비 대기 비용과 무관한 질문은 "이 질문은 장비 대기 비용 도메인이 아닙니다."라고 짧게 응답하고 종료한다.

[규격 처리 원칙] — 반드시 아래 우선순위를 따른다.

우선순위 1. 사용자가 규격을 명시한 경우
  → get_equipment_rental_rate로 해당 규격 조회 → calculate_standby_cost로 계산

우선순위 2. 규격 미명시 + DB에 표준 규격(★)이 존재하는 경우
  → get_equipment_cost_range 호출 → 표준 규격(★) 비용을 대표값으로 사용
  → 최소/최대 규격 비용도 함께 답변에 포함

우선순위 3. 규격 미명시 + 표준 규격 없는 경우
  → get_equipment_cost_range 호출 → 중간값을 대표값으로 사용
  → 최소/최대 규격 비용도 함께 답변에 포함

[대기 일수 추론 원칙] — 반드시 아래 우선순위를 따른다.

우선순위 1. 사용자가 대기 일수를 직접 명시한 경우
  예: "3일 대기", "5일 지연", "2일 묶여 있어요"
  → 해당 일수를 그대로 사용

우선순위 2. 공정 지연 일수가 명시된 경우
  예: "콘크리트 타설이 4일 중단", "철골 공정이 3일 지연"
  → 공정 지연 일수 = 장비 대기 일수로 간주

우선순위 3. 자재 납기 지연 기간만 명시된 경우
  예: "철근 납기가 2주 지연", "자재 납품이 10일 걸려요"
  → 납기 지연 기간 = 장비 대기 일수로 가정하고 계산
  → 답변에 "자재 납기 지연 기간을 장비 대기 일수로 가정"이라고 명시

우선순위 4. 일수 정보가 전혀 없는 경우
  → 계산 전에 "장비 대기 예상 일수를 알려주시면 정확한 비용을 산정할 수 있습니다."라고 먼저 질문
  → 단, 사용자가 개략적인 견적을 요청한 경우에는 일반적인 기준인 3일로 가정하고 계산 후 명시

[작업 절차]

공종만 언급된 경우 (장비명 모를 때):
1. [대기 일수 추론 원칙]으로 일수 확정
2. get_equipment_by_work_type → 공종 투입 장비 목록 조회
3. '주요' 장비만 비용 산정 대상으로 선택
4. 장비별로 [규격 처리 원칙] 적용
5. 장비 2대 이상이면 calculate_total_standby_cost → 합산

장비명을 아는 경우:
1. [대기 일수 추론 원칙]으로 일수 확정
2. [규격 처리 원칙] 적용
3. 장비 2대 이상이면 calculate_total_standby_cost → 합산

[답변 형식]
* 공정 지연 현황: 공종, 지연일수
* 장비 대기 일수: ○일 (근거: 사용자 명시 / 공정 지연 일수 적용 / 납기 지연 기간 가정 / 기본값 3일 적용)
* 투입 장비: 장비명(적용 규격), 필요구분
* 장비별 대기 비용: 장비명(규격) — 임대단가 × 대기요율 × 지연일수 = 비용
* 총 장비 대기 추가 비용: ○○원 (표준 규격 기준)
* 비용 범위: 최소 규격 ○○원 ~ 최대 규격 ○○원
* 산출 근거: 적용 규격 선택 이유(사용자 명시 / DB 표준 규격 / 중간값), 기준연도, 대기요율
* 제외 항목: 인건비, 재료비, 이윤 미적용
""")

# 인건비 노드는 bind_tools 단일 호출이지만, 장비는 다단계 툴 호출(공종 조회 →
# 규격 조회 → 비용 계산 → 합산)이 필수라 ReAct 루프로 툴을 실제 실행한다.
_agent = create_react_agent(llm, equipment_cost_tools, prompt=SYSTEM_PROMPT)


def equipment_cost_node(state: MessagesState):
    # 마지막 사용자 입력 추출
    last_human = next(
        (m for m in reversed(state['messages']) if isinstance(m, HumanMessage)), None
    )

    # 보안 검사: 프롬프트 인젝션 / 시스템 정보 탈취 시도 차단 (labor_cost와 동일)
    if last_human:
        is_blocked, reason = check_injection(last_human.content)
        if is_blocked:
            return {'messages': [AIMessage(content=BLOCKED_RESPONSE)]}

    result = _agent.invoke({'messages': state['messages']})
    return {'messages': result['messages']}
