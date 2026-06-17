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

# 타입 설명 문자열 — 모듈 레벨 상수로 캐싱 (호출마다 재조립 방지)
_TYPE_DESCRIPTIONS = "\n".join(
    f"- {t}: {info['name']} ({info['description']})"
    for t, info in QUESTION_TYPES.items()
)

def classify_question(query: str) -> dict:
    """질문을 A/B로 분류하고 타입과 이유를 반환."""
    log.debug(f"classify_question 호출 — query={query!r}")
    prompt = f"""다음 건설 현장 질문을 A 또는 B로 분류하세요.

질문 타입:
{_TYPE_DESCRIPTIONS}

[분류 규칙] — 반드시 아래 순서로 판단한다.

규칙 1. 질문의 핵심 의도가 비용 산정이면 → B
  - 장비 대기 비용, 추가 비용, 얼마인가요, 산정해주세요 등이 포함된 경우
  - 기상 원인이 언급되더라도 비용 계산이 목적이면 B
  - 예: "강풍으로 크레인이 2일 대기했는데 비용은요?" → B

규칙 2. 비용 산정 의도 없이 기상 원인만 언급된 경우 → A
  - 기상 영향 분석, 공정 지연 우려, 기상 리스크 평가가 목적인 경우
  - 예: "태풍으로 철골 공정이 지연될 것 같습니다" → A

규칙 3. 애매한 경우 기본값은 B

질문: {query}

JSON으로만 응답하세요:
{{"type": "A" or "B", "reason": "한 줄 이유"}}"""

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
        question_type = parsed["type"]
        if question_type not in QUESTION_TYPES:
            raise ValueError(f"알 수 없는 question_type: {question_type}")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        log.warning(f"분류 파싱 실패 ({e}), B로 기본 처리. 원본: {text!r}")
        return {
            "type": "B",
            "type_name": QUESTION_TYPES["B"]["name"],
            "reason": "파싱 실패, B(현장_변경)로 기본 처리",
        }

    log.info(f"분류 결과: {question_type} — 근거: {parsed.get('reason', '')}")
    return {
        "type": question_type,
        "type_name": QUESTION_TYPES[question_type]["name"],
        "reason": parsed.get("reason", ""),
    }


if __name__ == "__main__":
    # 분류 단독 테스트 (python router.py)
    samples = [
        "태풍으로 철골 세우기 공정이 3일 지연될 것 같습니다.",
        "굴착기 0.7㎥ 1대가 3일 공정이 지연되어 대기 중입니다. 장비 대기 추가 비용이 얼마인가요?",
    ]
    for q in samples:
        r = classify_question(q)
        print(f"[{r['type']}] {r['type_name']} — {r['reason']}")
        print(f"  질문: {q}\n")
