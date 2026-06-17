"""
장비 대기 비용 에이전트 노드
- construction_risk_agent-equipment_standby 폴더의 tools를 직접 임포트
- 질문이 장비 대기 비용 관련인지 스스로 판단 후 계산
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

_ROUTER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# equipment_cost/tools.py 경로
_EQUIP_TOOLS_PATH = os.path.abspath(
    os.path.join(_ROUTER_ROOT, '..', 'equipment_cost')
)

import importlib.util

# 주의: 단순히 `import tools`를 쓰면 agents/labor_cost/tools.py 등 동일한 이름의
# 다른 모듈과 sys.modules['tools']를 공유하게 되어 잘못된 함수가 바인딩될 수 있다.
# (labor_cost_node와 함께 그래프에 로드될 때 실제로 발생하는 버그였음)
# 고유한 모듈 이름으로 직접 로드해 충돌을 막는다.
equip_tools = None
_EQUIP_TOOLS_FILE = os.path.join(_EQUIP_TOOLS_PATH, 'tools.py')
try:
    _equip_tools_spec = importlib.util.spec_from_file_location('equipment_cost_tools_module', _EQUIP_TOOLS_FILE)
    equip_tools = importlib.util.module_from_spec(_equip_tools_spec)
    _equip_tools_spec.loader.exec_module(equip_tools)
except Exception:
    log.warning(f"Failed to import tools from {_EQUIP_TOOLS_FILE} - equipment node will be unavailable")
    equip_tools = None

load_dotenv(dotenv_path=os.path.join(_ROUTER_ROOT, '.env'))

_llm = ChatBedrockConverse(
    model=os.getenv('MODEL_ID', 'claude-haiku-4-5-20251001'),
    client=boto3.client('bedrock-runtime', region_name=os.getenv('AWS_BEDROCK_REGION', 'us-east-1')),
)

_TOOLS = [
    equip_tools.get_equipment_by_work_type,
    equip_tools.get_equipment_rental_rate,
    equip_tools.get_equipment_cost_range,
    equip_tools.calculate_standby_cost,
    equip_tools.calculate_total_standby_cost,
]

_PROMPT = SystemMessage(content="""
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

_agent = create_react_agent(_llm, _TOOLS, prompt=_PROMPT)


def equipment_node(state: dict) -> dict:
    log.debug('equipment_node 진입')
    print('\n[장비 에이전트] 처리 시작')
    result = _agent.invoke({'messages': state['messages']})

    # ReAct 루프에서 호출된 툴 이름을 순서대로 기록 (디버깅용)
    tool_calls = [
        tc['name']
        for m in result['messages']
        for tc in getattr(m, 'tool_calls', None) or []
    ]
    if tool_calls:
        log.debug(f"equipment_node 툴 호출 순서: {' → '.join(tool_calls)}")

    response = result['messages'][-1].content
    log.debug('equipment_node 종료')
    print(f'[장비 에이전트] 완료')
    return {'equipment_response': response}
