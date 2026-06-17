"""
합성(synthesize) 노드 — 여러 에이전트의 응답을 사용자에게 보여줄 하나의 최종 답변으로 정리한다.

라우팅 구조:
- A(기상_악화): weather → equipment/labor_cost(병렬) → synthesize
  (weather_response는 배경 설명용 JSON, equipment/labor_cost_response는 기상으로 인한 지연의 비용 산정 결과)
- B(현장_변경): equipment/material/labor_cost(병렬) → synthesize

LLM 호출이 실패하면(네트워크/Bedrock 문제 등) 규칙 기반 폴백으로 단순히 응답들을 이어붙여
최소한의 결과는 항상 반환한다.
"""
import json
import os
import re
import sys

import boto3
from langchain_core.messages import HumanMessage

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, '..')))

from config import MODEL_ID, SYNTHESIS_MAX_TOKENS, SYNTHESIS_TEMPERATURE
from logger import get_logger

log = get_logger(__name__)

_bedrock = boto3.client(
    "bedrock-runtime",
    region_name=os.getenv("AWS_BEDROCK_REGION", "us-east-1"),
)

# 폴백(규칙 기반)에서 "무관한 응답"으로 간주할 키워드
_IRRELEVANT_MARKERS = [
    "도메인이 아닙니다", "도메인 밖", "범위 밖", "산출 범위 밖",
    "역할입니다", "관련 없", "해당하지 않",
]

_LABELS = {
    'weather_response': '기상 에이전트',
    'equipment_response': '장비 에이전트',
    'material_response': '자재 에이전트',
    'labor_cost_response': '인건비 에이전트',
}


def _get_query(state: dict) -> str:
    return next(
        (m.content for m in reversed(state['messages']) if isinstance(m, HumanMessage)),
        '',
    )


def _looks_irrelevant(text: str) -> bool:
    return any(marker in text for marker in _IRRELEVANT_MARKERS)


def _collect_responses(state: dict) -> dict:
    return {
        _LABELS[key]: state.get(key)
        for key in ('weather_response', 'equipment_response', 'material_response', 'labor_cost_response')
        if state.get(key)
    }


def _call_llm(prompt: str) -> str:
    response = _bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": SYNTHESIS_MAX_TOKENS,
            "temperature": SYNTHESIS_TEMPERATURE,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )
    result = json.loads(response["body"].read())
    text = result["content"][0]["text"].strip()
    text = re.sub(r'^```(?:markdown)?\s*|\s*```$', '', text, flags=re.MULTILINE).strip()
    return text


def _synthesis_prompt(query: str, question_type: str, responses: dict) -> str:
    sections = "\n\n".join(f"[{label} 응답]\n{text}" for label, text in responses.items())

    weather_note = ""
    if question_type == 'A' and '기상 에이전트' in responses:
        weather_note = (
            "[기상 에이전트] 응답은 JSON 형식의 기상 리스크 분석 결과입니다. "
            "이를 위험도/작업 중단 필요 여부/지연일수 등을 풀어쓴 배경 설명으로 사용하고, "
            "장비/인건비 에이전트가 그 지연 때문에 산정한 비용 결과를 함께 안내하세요.\n\n"
        )

    return f"""당신은 건설 현장 리스크/비용 산정 요청에 대해 여러 전문 에이전트가 각자 답한 내용을
하나의 최종 답변으로 정리하는 역할입니다.

[사용자 질문]
{query}

{weather_note}{sections}

규칙:
- 사용자 질문과 실제로 관련된 답변만 골라 정리하세요.
- "이 질문은 제 도메인이 아닙니다" 류의 무관한 거절 응답은 결과에 포함하지 마세요.
- 관련 답변이 여러 개면(예: 장비+인건비 둘 다 관련) 모두 통합해서 하나의 답변으로 작성하세요.
- 모든 에이전트가 무관하다고 판단했다면, 어떤 종류의 질문이면 도움을 줄 수 있는지 간단히 안내하세요.
- JSON 필드명을 그대로 노출하지 말고 자연스러운 문장으로 작성하세요.
- 숫자/금액은 원본 그대로 정확히 인용하세요.
- 불필요한 서론 없이 바로 본문 작성하세요."""


def _fallback(responses: dict) -> str:
    """LLM 호출이 실패했을 때의 규칙 기반 합성."""
    relevant = {k: v for k, v in responses.items() if v and not _looks_irrelevant(v)}
    if not relevant:
        relevant = responses
    parts = [f"[{label}]\n{text}" for label, text in relevant.items() if text]
    return "\n\n".join(parts) if parts else "답변을 생성하지 못했습니다."


def synthesize_node(state: dict) -> dict:
    log.debug('synthesize_node 진입')
    query = _get_query(state)
    question_type = state.get('question_type')
    responses = _collect_responses(state)

    if not responses:
        return {'final_response': '에이전트 응답이 없습니다.'}

    try:
        final = _call_llm(_synthesis_prompt(query, question_type, responses))
        log.info('synthesize_node 완료')
        return {'final_response': final}
    except Exception as e:
        log.exception(f'synthesize_node LLM 호출 실패, 규칙 기반 폴백 사용: {e}')
        return {'final_response': _fallback(responses)}
