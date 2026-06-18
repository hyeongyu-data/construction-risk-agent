import os
from dotenv import load_dotenv

load_dotenv()

# 라우터 분류용 모델 (단순 A/B 분류 — Haiku로 충분, MODEL_ID env var로 오버라이드 가능)
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
# 분류 응답은 {"type","reason"} JSON. reason이 한글로 길어지면 100토큰에서 잘려
# JSON이 깨지고 B로 폴백되는 문제가 있어 넉넉히 256으로 둔다.
MAX_TOKENS = 256
TEMPERATURE = 0.1

# 최종 응답 합성(synthesize)용 — 분류보다 긴 출력이 필요
SYNTHESIS_MAX_TOKENS = 1500
SYNTHESIS_TEMPERATURE = 0.3

# 질문 타입: A = 기상 악화, B = 현장 변경
QUESTION_TYPES = {
    "A": {
        "name": "기상_악화",
        "description": (
            "비·눈·바람·태풍·한파·폭염 등 기상 원인이 질문에 명시된 공정 지연. "
            "예: '우천으로 타설 지연', '태풍으로 철골 작업 중단'"
        ),
    },
    "B": {
        "name": "현장_변경",
        "description": (
            "기상 원인이 없는 공정 지연·장비 대기·물량 변경·자재 단가 변동 등 모든 현장 변경. "
            "예: '공종이 3일 지연됐어요', '장비 대기 비용 산정', '물량이 늘었어요', '굴착기가 대기 중'"
        ),
    },
}
