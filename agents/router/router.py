"""
건설 리스크 라우터 — 질문 분류만 담당.
HTTP 디스패치는 LangGraph(graph.py)가 처리하므로 이 파일은 classify_question()만 노출한다.
"""
import json
import os
import re
import boto3
from config import MODEL_ID, MAX_TOKENS, TEMPERATURE, QUESTION_TYPES
from logger import get_logger

log = get_logger(__name__)

# boto3 클라이언트 모듈 레벨 싱글턴 (호출마다 재생성 방지)
_bedrock = boto3.client(
    "bedrock-runtime",
    region_name=os.getenv("AWS_BEDROCK_REGION", "us-east-1"),
)

# 비용 도메인 = 그래프 노드 이름과 1:1 매칭 (weather는 선행 게이트라 별도 처리)
_COST_AGENTS = ("equipment", "material", "labor_cost")
_DEFAULT_AGENTS = ["equipment", "material", "labor_cost"]   # 무관/파싱실패 시 폴백(전부)
_WEATHER_DEFAULT_AGENTS = ["equipment", "labor_cost"]       # 기상 지연 → 장비·인력 대기

_MATERIAL_LOOKUP_TERMS = (
    "조달청", "가격정보", "단가", "가격", "자재", "시세", "공시",
    "콘크리트", "레미콘", "시멘트", "철근", "파일", "블록",
)
_MATERIAL_LOOKUP_INTENTS = (
    "조회", "검색", "찾", "알려", "볼 수", "볼수", "가능", "할 수", "할수",
)


def _looks_like_material_lookup(query: str) -> bool:
    """Route procurement/material price lookup questions to the material agent."""
    q = query.lower()
    has_material_term = any(term.lower() in q for term in _MATERIAL_LOOKUP_TERMS)
    has_lookup_intent = any(intent.lower() in q for intent in _MATERIAL_LOOKUP_INTENTS)
    return has_material_term and has_lookup_intent


def classify_question(query: str) -> dict:
    """질문을 분석해 실행 계획을 반환한다.

    Returns:
        {
          "needs_weather": bool,        # 기상 분석 선행 필요 여부
          "agents": [<cost agent>...],  # equipment/material/labor_cost 중 관련된 것만
          "reason": str,
        }
    """
    log.debug(f"classify_question 호출 — query={query!r}")
    if _looks_like_material_lookup(query):
        return {
            "needs_weather": False,
            "agents": ["material"],
            "reason": "자재 가격 또는 조달청 단가 조회 의도",
        }

    prompt = f"""다음 건설 현장 질문을 분석해 실행 계획을 JSON으로 반환하세요.

[비용 도메인] — 질문에 실제로 관련된 것만 고른다.
- equipment: 장비 대기비 (크레인·펌프차·타워크레인·굴착기·고소작업대·임대료·장비 대기 등)
- material: 자재비 (자재 단가·추가 물량·발주·철근·레미콘·H파일 등)
- labor_cost: 인건비 (노임단가·인부·품셈·직접노무비·인력 투입 등)

[기상 선행 판단 — needs_weather]
- true: 비·눈·바람·태풍·한파·폭염 등 기상 사유가 있고, 지연 일수가 아직 확정되지 않아
  기상 예보를 먼저 확인·추정해야 하는 경우. (예: "내일 비온다는데 확인하고 지연 추측해서 비용 산정")
  → 기상 분석이 먼저 지연 일수를 산출한 뒤 그 결과로 비용 에이전트가 산정한다.
- false: 지연 일수가 이미 확정됐거나(예: "3일 대기했다", "이틀째 멈춰 있다") 기상과 무관한 경우.

[규칙]
1. needs_weather=true인데 비용 도메인이 명확하지 않으면 agents=["equipment","labor_cost"] (기상 지연 → 장비·인력 대기).
2. 어떤 비용 도메인과도 무관하고 기상도 아니면 agents=[] (빈 배열).
3. 애매하면 관련 가능성이 있는 도메인을 모두 포함한다.

질문: {query}

JSON으로만 응답하세요:
{{"needs_weather": true 또는 false, "agents": ["equipment"|"material"|"labor_cost", ...], "reason": "한 줄 이유"}}"""

    response = _bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    result = json.loads(response["body"].read())
    text = result["content"][0]["text"].strip()
    log.debug(f"모델 원본 응답: {text!r}")

    # 마크다운 코드블록 제거 (```json ... ``` 등 모든 형태 처리)
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.MULTILINE).strip()

    if not text:
        log.error(f"모델 응답이 비어있음. 원본 응답: {result}")
        raise ValueError(f"모델 응답이 비어있습니다. 원본 응답: {result}")

    try:
        parsed = json.loads(text)
        needs_weather = bool(parsed.get("needs_weather", False))
        raw_agents = parsed.get("agents", []) or []
        # 허용된 비용 도메인만, 순서·중복 정리
        agents = [a for a in _COST_AGENTS if a in raw_agents]
        reason = parsed.get("reason", "")
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        log.warning(f"분류 파싱 실패 ({e}), 전체 에이전트로 기본 처리. 원본: {text!r}")
        return {
            "needs_weather": False,
            "agents": list(_DEFAULT_AGENTS),
            "reason": "파싱 실패, 전체 비용 에이전트로 기본 처리",
        }

    # 폴백 보정
    if needs_weather and not agents:
        agents = list(_WEATHER_DEFAULT_AGENTS)

    log.info(f"분류 결과: needs_weather={needs_weather}, agents={agents} — 근거: {reason}")
    return {"needs_weather": needs_weather, "agents": agents, "reason": reason}


if __name__ == "__main__":
    # 분류 단독 테스트 (python router.py)
    samples = [
        "태풍으로 철골 세우기 공정이 3일 지연될 것 같습니다.",
        "굴착기 0.7㎥ 1대가 3일 공정이 지연되어 대기 중입니다. 장비 대기 추가 비용이 얼마인가요?",
        "내일 비온다는데 확인하고 지연 일자 추측해서 추가비용 산정해줘",
        "철근 200톤 추가 발주 자재비 알려줘",
    ]
    for q in samples:
        r = classify_question(q)
        print(f"[weather={r['needs_weather']}] agents={r['agents']} — {r['reason']}")
        print(f"  질문: {q}\n")
