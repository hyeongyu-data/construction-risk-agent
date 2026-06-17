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

from weather_risk.services.weather_risk_service import analyze_weather_risk
from weather_risk.clients.exceptions import KmaApiError
from project_store import get_project
from logger import get_logger

log = get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")


def weather_node(state: dict) -> dict:
    """
    기상 리스크 평가 노드.

    입력:
        state['project_id']: 프로젝트 ID
    출력:
        {'weather_response': WeatherRiskResponse JSON 문자열}
    """
    log.debug('weather_node 진입')

    try:
        # 1. project_id 추출
        project_id = state.get('project_id')
        if not project_id:
            log.error('project_id 없음')
            return {'weather_response': json.dumps(
                {'status': 'ERROR', 'error': 'project_id가 제공되지 않았습니다'},
                ensure_ascii=False
            )}

        # 2. project_store에서 WeatherRiskRequest 로드
        try:
            request = get_project(project_id)
            log.debug(f'프로젝트 로드: {project_id} → {request.site_name}')
        except KeyError:
            log.error(f'프로젝트 없음: {project_id}')
            return {'weather_response': json.dumps(
                {'status': 'ERROR', 'error': f'프로젝트를 찾을 수 없습니다: {project_id}'},
                ensure_ascii=False
            )}

        # 3. 기상 리스크 분석
        # TODO: messages에서 날짜/시간 파싱이 필요하면
        #       get_project(project_id, query_date=파싱된날짜) 형태로 확장
        response = analyze_weather_risk(request)
        log.info(f'기상 리스크 평가 완료: {response.risk_result.risk_level}')

        return {'weather_response': response.model_dump_json(ensure_ascii=False)}

    except KmaApiError as e:
        log.exception(f'기상청 API 에러: {e}')
        return {'weather_response': json.dumps(
            {'status': 'ERROR', 'error': f'기상 데이터 조회 실패: {str(e)}'},
            ensure_ascii=False
        )}
    except Exception as e:
        log.exception(f'weather_node 예외: {e}')
        return {'weather_response': json.dumps(
            {'status': 'ERROR', 'error': f'기상 평가 중 오류 발생: {str(e)}'},
            ensure_ascii=False
        )}
