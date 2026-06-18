import os
import logging
import math
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_aws import BedrockEmbeddings
import psycopg2
from pgvector.psycopg2 import register_vector

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
 
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     os.getenv("DB_PORT", "5432"),
    "dbname":   os.getenv("DB_NAME", "material_cost"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# 상단에서 한 번만 초기화
embedder = BedrockEmbeddings(
    model_id='amazon.titan-embed-text-v2:0',
    region_name=os.getenv('AWS_BEDROCK_REGION'),
)


def _get_pg_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    register_vector(conn)
    return conn


# 1. 노임단가 DB 조회 툴
@tool
def get_labor_price(job_type: str) -> str:
    '''
    직종명으로 최신 노임단가를 조회한다.
    job_type은 노임단가 DB의 직종명 기준으로 입력해야 한다.
    예: 콘크리트공, 철근공, 보통인부, 형틀목공, 방수공, 철골공
    부분 일치 검색이 가능하므로 직종명 일부만 입력해도 된다.
    '''
    conn = _get_pg_connection()
    cur = conn.cursor()

    # 1순위: 정확히 일치하는 직종명
    cur.execute("""
        SELECT job_type, price, year
        FROM labor_cost.labor_cost
        WHERE job_type = %s
        ORDER BY year DESC
        LIMIT 1
    """, (job_type,))
    res = cur.fetchone()

    # 2순위: 정확 일치 없으면 LIKE 검색 후 이름 길이가 가장 짧은 것 (가장 구체적인 매칭)
    if res is None:
        cur.execute("""
            SELECT job_type, price, year
            FROM labor_cost.labor_cost
            WHERE job_type LIKE %s
            ORDER BY year DESC, LENGTH(job_type) ASC
            LIMIT 1
        """, (f'%{job_type}%',))
        res = cur.fetchone()

    cur.close()
    conn.close()

    if res is None:
        return f'DB에 없는 직종입니다: "{job_type}". 직종명을 다시 확인하세요.'

    logging.info(f'get_labor_price tool 실행: {res}')
    return f'노임단가 DB 조회 결과: {res[0]}: {res[1]:,}원 ({res[2]} 기준)'


# 2. 표준품셈 RAG 검색 툴
SIMILARITY_THRESHOLD = 0.45  # 코사인 거리 임계값 (0~2, 낮을수록 유사. 0.45 이하만 채택)

@tool
def search_standard_spec(query: str) -> str:
    '''
    2026년 건설공사 표준품셈 PDF에서 공종별 인부 투입 기준을 검색한다.
    공종명 또는 작업 내용을 query로 입력하면 관련 품셈 기준(직종별 투입 인부수/단위)을 반환한다.
    예: "레디믹스트콘크리트 타설", "철근 조립", "철골 세우기", "방수 공사"
    인부수 산출이 필요할 때 반드시 이 툴을 먼저 호출해야 한다.
    '''
    query_vector = embedder.embed_query(query)

    conn = _get_pg_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT content, embedding <=> %s::vector AS distance
        FROM rag.standard_spec
        ORDER BY distance
        LIMIT 5
    """, [query_vector])
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # 임계값 이하 청크만 채택
    filtered = [(content, dist) for content, dist in rows if dist <= SIMILARITY_THRESHOLD]

    if not filtered:
        # 임계값 초과 시 가장 유사한 1개만 경고와 함께 반환
        if rows:
            best_content, best_dist = rows[0]
            logging.warning(f'search_standard_spec: 임계값 초과 (최소 거리={best_dist:.3f}), 최상위 1개만 반환')
            return f'[주의: 검색 유사도가 낮습니다(거리={best_dist:.2f}). 아래 내용이 질문과 다를 수 있습니다.]\n\n{best_content}'
        return '표준품셈에서 관련 내용을 찾지 못했습니다.'

    chunks = [content for content, _ in filtered]
    distances = [dist for _, dist in filtered]
    logging.info(f'search_standard_spec: query={query}, {len(chunks)}개 채택 (거리: {[f"{d:.3f}" for d in distances]})')
    return '\n\n'.join(chunks)


# 3. 총 투입 인부수 계산 툴
@tool
def calculate_workers(quantity: float, unit_labor: float) -> str:
    '''
    공사 수량과 표준품셈 품량(인/단위)을 곱해 총 투입 인부수(man-day)를 계산한다.
    반드시 search_standard_spec으로 품량을 먼저 조회한 후 이 툴을 호출해야 한다.
    수량(ton, m³ 등)에 노임단가를 직접 곱하면 단위 오류이므로, 반드시 이 툴을 통해 인부수를 먼저 산출해야 한다.

    quantity  : 공사 수량 (예: 200ton, 150m³)
    unit_labor: 표준품셈 품량, 직종별 1단위당 투입 인부수 (인/ton, 인/m³ 등)
                예: 철골 세우기 철골공 0.33인/ton, 콘크리트 타설 콘크리트공 0.06인/m³

    계산 예시:
    - 철골 세우기 200ton, 철골공 0.33인/ton → 200 × 0.33 = 66인 → ceil → 66인
    - 콘크리트 타설 150m³, 콘크리트공 0.06인/m³ → 150 × 0.06 = 9인 → ceil → 9인
    - 소수점 예시: 130ton, 철골공 0.33인/ton → 42.9인 → ceil → 43인
    '''
    raw = round(quantity * unit_labor, 4)  # 부동소수점 오류 방지
    total_workers = math.ceil(raw)
    logging.info(f'calculate_workers: {quantity} × {unit_labor}인/단위 = {raw} → 올림 → {total_workers}인')
    return f'총 투입 인부수: {quantity} × {unit_labor}인/단위 = {raw:.2f} → 올림 처리 → {total_workers}인 (man-day)'


# 4. 인건비 계산 툴
@tool
def calculate_labor_cost(labor_price: int, workers: float) -> str:
    '''
    노임단가와 총 인부수(man-day)를 곱해 총 인건비를 계산한다.
    labor_price: 1인 1일 노임단가 (원), get_labor_price 툴로 조회한 값을 사용한다.
    workers: 총 투입 인부수 (man-day) = 단위당 인부수 × 공사량으로 산출한 값
    예: 콘크리트공 273,540원 × 450명 = 123,093,000원
    '''
    total = int(labor_price * workers)
    logging.info(f'calculate_labor_cost: {labor_price}원 × {workers}명 = {total}원')
    return f'총 인건비: {labor_price:,}원 × {workers}명 = {total:,}원'
