"""기상 에이전트 노드"""
import json
import os
import sys
from zoneinfo import ZoneInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, '../../..'))
_AGENTS = os.path.abspath(os.path.join(_HERE, '../..'))
sys.path.insert(0, _ROOT)
sys.path.insert(0, _AGENTS)

from langchain_core.messages import HumanMessage
from langgraph.types import Command, Send

from weather_risk.services.weather_risk_service import analyze_weather_risk
from weather_risk.clients.exceptions import KmaApiError
from project_store import get_project
from logger import get_logger

log = get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")


def _cost_request_message(response_json: dict) -> HumanMessage:
    """기상 리스크 분석 결과를 장비/인건비 에이전트용 비용 산정 요청 메시지로 변환."""
    risk = response_json.get('risk_result', {}) or {}
    site = response_json.get('site', {}) or {}
    work = response_json.get('work', {}) or {}
    risk_level = risk.get('risk_level', '-')
    stoppage = risk.get('work_stoppage_required', False)
    delay_days = risk.get('delay_day_equivalent') or 0

    # FULL_DAY 정책 보정: 작업 중단이 필요하면 시간 환산값(delay_day_equivalent)이
    # 최소 지연일수(minimum_delay_days)보다 작아도 최소 일수를 적용한다.
    # (예: 콘크리트 타설 중단 0.5일 → 정책상 최소 1일)
    policy = risk.get('delay_policy') or {}
    min_days = policy.get('minimum_delay_days')
    if stoppage and min_days:
        delay_days = max(delay_days, min_days)

    return HumanMessage(content=(
        f"[기상 리스크 분석 결과 — 참고용]\n"
        f"현장: {site.get('site_name', '-')} / 공종: {work.get('work_type', '-')}\n"
        f"위험도: {risk_level} / 작업 중단 필요: {'예' if stoppage else '아니오'}\n"
        f"기상 분석 권장 지연일수: {delay_days}일\n\n"
        f"[일수·수량 적용 우선순위]\n"
        f"1. 사용자가 원문에서 직접 명시한 대기일수·지연일수·투입 인원/일수가 있으면 그 값을 최우선으로 사용한다.\n"
        f"   (예: '펌프카 1대 1일 대기', '콘크리트공 4명·보통인부 3명 2일 추가 투입')\n"
        f"2. 사용자가 명시하지 않은 항목에 한해, 위 기상 분석 권장 지연일수({delay_days}일)를 참고값으로 사용한다.\n"
        f"3. 기상 권장 지연일수가 사용자 명시 수치를 덮어쓰지 않는다. "
        f"   특히 권장 지연일수가 0일이어도 사용자가 대기/투입을 명시했으면 그 값으로 비용을 산정한다.\n\n"
        f"위 원칙에 따라 장비 대기 비용과 인건비를 산정해 주세요."
    ))


def weather_node(state: dict) -> Command:
    """
    기상 리스크 평가 노드.

    입력:
        state['project_id']: 프로젝트 ID
    출력:
        Command(update={'weather_response': ...}, goto=...)
        - 분석 성공: 비용 산정 요청 메시지를 추가해 equipment/labor_cost로 병렬 핸드오프
        - 분석 실패: synthesize로 직행 (비용 산정 불가)
    """
    log.debug('weather_node 진입')

    def _fail(error_json: dict) -> Command:
        return Command(
            update={'weather_response': json.dumps(error_json, ensure_ascii=False)},
            goto='synthesize',
        )

    try:
        # 1. project_id 추출
        project_id = state.get('project_id')
        if not project_id:
            log.error('project_id 없음')
            return _fail({'status': 'ERROR', 'error': 'project_id가 제공되지 않았습니다'})

        # 2. project_store에서 WeatherRiskRequest 로드
        try:
            request = get_project(project_id)
            log.debug(f'프로젝트 로드: {project_id} → {request.site_name}')
        except KeyError:
            log.error(f'프로젝트 없음: {project_id}')
            return _fail({'status': 'ERROR', 'error': f'프로젝트를 찾을 수 없습니다: {project_id}'})

        # 3. 기상 리스크 분석
        # TODO: messages에서 날짜/시간 파싱이 필요하면
        #       get_project(project_id, query_date=파싱된날짜) 형태로 확장
        response = analyze_weather_risk(request)
        log.info(f'기상 리스크 평가 완료: {response.risk_result.risk_level}')

        weather_response_str = response.model_dump_json(ensure_ascii=False)

        # 4. 장비/인건비 에이전트가 비용을 산정할 수 있도록 분석 결과를 메시지로 추가해 핸드오프
        # mode='json'으로 직렬화해야 enum이 값(예: 'CONCRETE_POURING', 'LOW')으로
        # 변환된다. 기본 model_dump()는 enum 객체를 그대로 둬서 메시지에
        # 'WorkType.CONCRETE_POURING' 같은 repr이 새어 나간다.
        cost_request = _cost_request_message(response.model_dump(mode='json'))
        payload = {**state, 'messages': state['messages'] + [cost_request]}

        # 플래너가 정한 비용 에이전트로만 핸드오프 (기본: 장비·인력 대기).
        # material은 기상 지연과 무관하므로 플래너가 명시했을 때만 포함된다.
        targets = state.get('target_agents') or ['equipment', 'labor_cost']
        print(f'\n[기상 에이전트] 완료 → {targets}로 전달')
        return Command(
            update={'weather_response': weather_response_str},
            goto=[Send(a, payload) for a in targets],
        )

    except KmaApiError as e:
        log.exception(f'기상청 API 에러: {e}')
        return _fail({'status': 'ERROR', 'error': f'기상 데이터 조회 실패: {str(e)}'})
    except Exception as e:
        log.exception(f'weather_node 예외: {e}')
        return _fail({'status': 'ERROR', 'error': f'기상 평가 중 오류 발생: {str(e)}'})
