"""
end-to-end 테스트 — 실행할 때마다 랜덤 케이스 1개 선택
실행: python test.py (construction_risk_agent-router 폴더에서)
"""
import random
import sys
from langchain_core.messages import HumanMessage
from logger import get_logger

# weather 테스트 모드에서는 graph import 스킵
if len(sys.argv) <= 1 or sys.argv[1] != 'weather':
    from graph import graph
else:
    graph = None

log = get_logger(__name__)

TEST_CASES = [
    # ── A타입 (기상 악화) ─────────────────────────────────────────
    {
        'name': 'A-1 | 기상악화 — 태풍 작업 중단',
        'expected_type': 'A',
        'query': '내일 태풍 예보가 있는데 철골 세우기 작업을 중단해야 할까요?',
    },
    {
        'name': 'A-2 | 기상악화 — 폭설 공정 지연',
        'expected_type': 'A',
        'query': '폭설로 콘크리트 타설이 이틀째 멈춰 있습니다. 대응 방안을 알려주세요.',
    },
    # ── B타입 — 규격·일수 모두 명시 ──────────────────────────────
    {
        'name': 'B-1 | 장비 대기 — 타워크레인 4일',
        'expected_type': 'B',
        'query': '타워크레인 50×12 1대가 자재 반입 지연으로 4일 대기 중입니다. 추가 비용이 얼마인가요?',
    },
    {
        'name': 'B-2 | 장비 대기 — 다수 장비 합산',
        'expected_type': 'B',
        'query': '콘크리트 펌프차 32m 1대와 콘크리트 믹서트럭 6.0㎥ 2대가 3일 공정 지연으로 대기할 때 총 장비 대기 비용은?',
    },
    # ── B타입 — 규격 미명시 ───────────────────────────────────────
    {
        'name': 'B-3 | 장비 대기 — 규격 미명시 범위 요청',
        'expected_type': 'B',
        'query': '크레인(타이어) 1대가 5일 대기 중인데 규격을 모릅니다. 대기 비용 범위를 알려주세요.',
    },
    # ── B타입 — 일수 미명시 ───────────────────────────────────────
    {
        'name': 'B-4 | 장비 대기 — 일수 미명시',
        'expected_type': 'B',
        'query': '지게차 3.5ton 2대가 공정 지연으로 대기 중입니다. 비용이 얼마인가요?',
    },
    # ── 경계 케이스 — 기상 언급 + 비용 요청 → B ──────────────────
    {
        'name': 'B-5 | 경계 — 기상 언급 + 비용 산정 (B 분류 확인)',
        'expected_type': 'B',
        'query': '강풍으로 크레인(타이어) 50ton이 3일 대기했습니다. 장비 대기 추가 비용이 얼마인가요?',
    },
    # ── B타입 — 자재 납기 지연으로 일수 추론 ────────────────────
    {
        'name': 'B-6 | 장비 대기 — 납기 지연 일수 추론',
        'expected_type': 'B',
        'query': '철근 납기가 2주 지연되면서 고소작업차가 현장에 묶여 있습니다. 대기 비용을 산정해 주세요.',
    },
    # ── B타입 — 공종명만 언급 ─────────────────────────────────────
    {
        'name': 'B-7 | 장비 대기 — 공종명만 언급',
        'expected_type': 'B',
        'query': '방수공사 공정이 2일 지연됐습니다. 투입 장비 대기 비용을 산정해 주세요.',
    },
    # ── 도메인 외 질문 — 장비 에이전트 거절 확인 ─────────────────
    {
        'name': 'B-8 | 도메인 외 — 인건비 질문 거절 확인',
        'expected_type': 'B',
        'query': '철골 세우기 공정이 3일 지연됐을 때 인건비 추가 비용은 얼마인가요?',
    },
]

_STUB_MARKER = '미구현'


def run_test(case: dict):
    print(f'\n{"="*65}')
    print(f'[테스트] {case["name"]}')
    print(f'예상 분류: {case["expected_type"]}')
    print(f'질문: {case["query"]}')
    print('=' * 65)

    log.info(f"=== 테스트 시작: {case['name']} ===")
    log.info(f"질문: {case['query']}")

    try:
        result = graph.invoke({'messages': [HumanMessage(content=case['query'])]})
    except Exception:
        log.exception('graph.invoke 실패')
        raise

    actual_type = result.get('question_type', '?')

    # 분류 정확도 출력
    match = '✅' if actual_type == case['expected_type'] else '❌'
    print(f'\n{match} 분류 결과: {actual_type} (예상: {case["expected_type"]})')
    log.info(f"분류 결과: {actual_type} (예상: {case['expected_type']}, 일치: {match == '✅'})")

    # 에이전트 응답 출력 (stub 제외) — 콘솔에만 표시, 로그는 디버깅 정보만 기록
    for key, label in [
        ('weather_response', '기상 에이전트'),
        ('equipment_response', '장비 에이전트'),
        ('labor_cost_response', '인건비 에이전트'),
        ('material_response', '자재 에이전트'),
    ]:
        resp = result.get(key)
        if resp and _STUB_MARKER not in resp:
            print(f'\n[{label}]\n{resp}')

    log.debug("--- 처리 완료 ---")


def test_weather_node():
    """weather_node 직접 테스트 (graph 의존성 제거)"""
    print("\n" + "="*65)
    print("[T10 weather_node 테스트]")
    print("="*65)

    try:
        # weather_node 직접 import
        from nodes.weather_node import weather_node

        state = {
            "messages": [HumanMessage(content="내일 콘크리트 타설 기상 악화 있나?")],
            "project_id": "PJT-001"
        }

        print(f"\n[입력]")
        print(f"  project_id: {state['project_id']}")
        print(f"  message: {state['messages'][0].content}")

        result = weather_node(state)

        weather_response = result.get("weather_response")

        if weather_response:
            print(f"\n[기상 평가 응답]")
            print(f"  length: {len(weather_response)} chars")

            # JSON 파싱해서 status 확인
            try:
                import json as json_lib
                resp_json = json_lib.loads(weather_response)
                status = resp_json.get("status")
                risk_level = resp_json.get("risk_result", {}).get("risk_level")
                site_name = resp_json.get("site", {}).get("site_name")

                print(f"  status: {status}")
                print(f"  site_name: {site_name}")
                print(f"  risk_level: {risk_level}")

                if status == "SUCCESS":
                    print("\n[OK] weather_node 성공")
                else:
                    print(f"\n[ERROR] status={status}")
                    error = resp_json.get("error")
                    if error:
                        print(f"  error: {error}")
            except Exception as e:
                print(f"[ERROR] JSON 파싱 실패: {e}")
                print(f"  response: {weather_response[:200]}...")
        else:
            print("[ERROR] weather_response가 없습니다")

    except Exception as e:
        log.exception("weather_node 테스트 실패")
        print(f"[ERROR] {e}")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'weather':
        test_weather_node()
    else:
        case = random.choice(TEST_CASES)
        run_test(case)
