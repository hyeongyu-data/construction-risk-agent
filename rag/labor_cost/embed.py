"""
표준품셈 PDF → 텍스트 추출 → 청킹 → 임베딩 → ChromaDB 저장
pdfplumber 사용으로 테이블 구조 보존, (일당) 항목 → 인/단위 자동 환산
실행: python rag/labor_cost/embed.py
"""
import pdfplumber
from langchain_aws import BedrockEmbeddings
import chromadb
import os
import re
from dotenv import load_dotenv

load_dotenv()

PDF_PATH      = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'raw', '2026+건설공사표준품셈원문정오표1차+반영.PDF')
VECTORDB_PATH = os.path.join(os.path.dirname(__file__), 'vectordb')
EMBED_MODEL   = 'amazon.titan-embed-text-v2:0'
MIN_CHUNK_LEN = 80

CHAPTERS = [
    ('철근콘크리트공사', 185 - 1, 214 - 1),
    ('철골공사',        625 - 1, 634 - 1),
    ('방수공사',        659 - 1, 665 - 1),
]


# ─────────────────────────────────────────
# 1. 테이블 → 마크다운 문자열
# ─────────────────────────────────────────
def table_to_md(table: list) -> str:
    """pdfplumber 테이블 행 리스트를 읽기 쉬운 마크다운 표로 변환."""
    if not table:
        return ''
    lines = []
    for row in table:
        cells = [str(c).replace('\n', '/') if c is not None else '' for c in row]
        lines.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


# ─────────────────────────────────────────
# 2. (일당) 테이블 → 인/단위 환산
# ─────────────────────────────────────────
WORKER_KEYWORDS = ['콘크리트공', '보통인부', '철근공', '형틀목공', '방수공',
                   '특별인부', '철골공', '도장공', '미장공', '조적공']

def try_convert_daily(table: list, unit: str) -> str:
    """
    (일당) 테이블에서 직종별 인/일 ÷ 시공량/일 → 인/단위 환산 문자열 반환.
    테이블 행 구조: [..., '직종명\\n직종명', ..., '수량\\n수량', '시공량', ...]
    변환 불가 시 빈 문자열 반환.
    """
    results = []

    for row in table:
        if not row or not any(row):
            continue

        jobs = []
        workers_per_day = []
        daily_output = None
        found_workers_col = False

        for ci, cell in enumerate(row):
            if cell is None:
                continue
            s = str(cell).strip()

            # 직종명 셀 탐색
            if any(kw in s for kw in WORKER_KEYWORDS):
                jobs = [j.strip() for j in s.split('\n') if j.strip()]

            # 숫자 셀: 직종명 발견 이후에만 탐색
            if jobs and re.match(r'^[\d.]+(\n[\d.]+)*$', s):
                if not found_workers_col:
                    # 첫 번째 숫자 컬럼 = 인원수
                    workers_per_day = [float(v) for v in s.split('\n') if v.strip()]
                    found_workers_col = True
                else:
                    # 두 번째 이후 단일 숫자 = 시공량 후보
                    try:
                        v = float(s)
                        if v >= 1.0 and daily_output is None:
                            daily_output = v
                    except ValueError:
                        pass

        if jobs and workers_per_day and daily_output and daily_output > 0:
            for job, wpd in zip(jobs, workers_per_day):
                rate = wpd / daily_output
                results.append(
                    f'  {job}: {wpd}인/일 ÷ {daily_output}{unit}/일 = {rate:.4f}인/{unit}'
                )

    return '\n'.join(results)


# ─────────────────────────────────────────
# 3. 챕터 전체 텍스트 추출 → 청킹 → (일당) 환산 주석 삽입
# ─────────────────────────────────────────
def extract_and_chunk(pdf_path: str, start_page: int, end_page: int) -> list:
    """
    2단계 파이프라인:
    1단계) pdfplumber 텍스트만 추출 → 줄 시작 품셈 번호로 청킹
    2단계) (일당) 페이지의 테이블에서 환산 데이터 추출 →
           섹션 코드로 올바른 청크에 주석 삽입
    """
    # ── 1단계: 텍스트 추출 + 청킹 ──
    text_parts = []
    page_meta = []   # (pno, is_daily, unit, tables)

    with pdfplumber.open(pdf_path) as pdf:
        for pno in range(start_page, end_page + 1):
            pg = pdf.pages[pno]
            txt = pg.extract_text() or ''
            tables = pg.extract_tables() or []

            if txt.strip():
                text_parts.append(txt.strip())

            is_daily = '(일당)' in txt
            unit = 'ton' if ('ton' in txt or '(ton)' in txt) and '㎥' not in txt else '㎥'
            page_meta.append((pno, is_daily, unit, tables))

    full_text = '\n'.join(text_parts)

    # 줄 시작 품셈 번호로 분리 (본문 내 참조 "[공통부문] 6-1-3" 등은 분리 안 함)
    raw = re.split(r'(?m)^(?=\d+-\d+-\d+)', full_text)
    chunks = [c.strip() for c in raw if len(c.strip()) >= MIN_CHUNK_LEN]

    # 섹션 코드 → 청크 인덱스 매핑
    chunk_map: dict[str, int] = {}
    for ci, chunk in enumerate(chunks):
        m = re.match(r'(\d+-\d+-\d+)', chunk)
        if m:
            chunk_map[m.group(1)] = ci

    # ── 2단계: (일당) 테이블 환산 주석을 올바른 청크에 삽입 ──
    for pno, is_daily, unit, tables in page_meta:
        if not is_daily:
            continue

        # 이 페이지 텍스트에 등장하는 섹션 코드 순서대로
        pg_text = text_parts[pno - start_page] if (pno - start_page) < len(text_parts) else ''
        section_codes = [sc for sc in re.findall(r'\d+-\d+-\d+', pg_text)
                         if sc in chunk_map]

        for t in tables:
            conv = try_convert_daily(t, unit)
            if not conv:
                continue

            # 아직 환산 주석이 없는 첫 번째 해당 청크에 삽입
            for sc in section_codes:
                ci = chunk_map[sc]
                if '[※ 일당' not in chunks[ci]:
                    chunks[ci] += f'\n\n[※ 일당→{unit}당 환산]\n{conv}'
                    break

    return chunks


# ─────────────────────────────────────────
# 5. 임베딩 + ChromaDB 저장
# ─────────────────────────────────────────
def embed_and_store():
    embedder = BedrockEmbeddings(
        model_id=EMBED_MODEL,
        region_name=os.getenv('AWS_BEDROCK_REGION'),
    )

    client = chromadb.PersistentClient(path=VECTORDB_PATH)
    try:
        client.delete_collection('standard_spec')
        print('기존 컬렉션 삭제 완료')
    except Exception:
        pass
    collection = client.create_collection('standard_spec')

    for chapter_name, start, end in CHAPTERS:
        print(f'처리 중: {chapter_name} ({start + 1}~{end + 1}p)')

        chunks = extract_and_chunk(PDF_PATH, start, end)
        print(f'  청크 수: {len(chunks)}개')

        embeddings = embedder.embed_documents(chunks)

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            m = re.match(r'(\d+-\d+-\d+)', chunk)
            section_code = m.group(1) if m else ''

            collection.add(
                ids=[f'{chapter_name}_{i}'],
                embeddings=[emb],
                documents=[chunk],
                metadatas=[{'chapter': chapter_name, 'section_code': section_code}],
            )

        print(f'  → {len(chunks)}개 청크 저장 완료')

    print('\n임베딩 완료')


if __name__ == '__main__':
    embed_and_store()
