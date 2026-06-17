"""
사내 문서 RAG 검색 모듈
- PostgreSQL(pgvector) rag.company_docs 테이블에서 자재명으로 과거 계약단가 조회
- material_cost_agent에서 LangChain Tool로 직접 사용 가능

사용 예:
  from rag.company_docs.search import search_contract_price
  result = search_contract_price.invoke({"material_name": "철근 SD400"})
"""

import os
import re
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

import psycopg2
from pgvector.psycopg2 import register_vector
from langchain_aws import BedrockEmbeddings
from langchain_core.tools import tool

EMBED_MODEL = "amazon.titan-embed-text-v2:0"
N_RESULTS   = 15

PRICE_PATTERN = re.compile(
    r'([가-힣a-zA-Z0-9\s\-\(\)×./]+?)'
    r'[\s:：|]*'
    r'([\d,]+)'
    r'\s*원'
    r'(?:/\s*([a-zA-Zㄱ-힣㎥㎡㎣㎤]+))?',
    re.UNICODE
)

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     os.getenv("DB_PORT", "5432"),
    "dbname":   os.getenv("DB_NAME", "material_cost"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}


def get_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    register_vector(conn)
    return conn


def _get_embedder():
    return BedrockEmbeddings(
        model_id=EMBED_MODEL,
        region_name=os.getenv("AWS_BEDROCK_REGION", "us-east-1"),
    )


def _extract_prices(text: str) -> list[dict]:
    results = []
    for m in PRICE_PATTERN.finditer(text):
        name  = m.group(1).strip(" \t|")
        price = m.group(2).replace(",", "")
        unit  = m.group(3) or ""
        try:
            results.append({"자재명": name, "단가": int(price), "단위": unit})
        except ValueError:
            pass
    return results


def search_raw(
    query: str,
    n_results: int = N_RESULTS,
    doc_type: str | None = None,
    year: str | None = None,
    project_id: str | None = None,
) -> list[dict]:
    """
    PostgreSQL pgvector에서 쿼리와 유사한 청크를 검색하고 원본 결과 반환.
    """
    embedder        = _get_embedder()
    query_embedding = embedder.embed_query(query)

    conn = get_connection()
    cur  = conn.cursor()

    where_clauses = []
    filter_params = []

    if doc_type:
        where_clauses.append("doc_type = %s")
        filter_params.append(doc_type)
    if year:
        where_clauses.append("year = %s")
        filter_params.append(year)
    if project_id:
        where_clauses.append("project_id = %s")
        filter_params.append(project_id)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    cur.execute(f"""
        SELECT content, project_id, doc_type, year, file_name,
               embedding <=> %s::vector AS distance
        FROM rag.company_docs
        {where_sql}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, [query_embedding] + filter_params + [query_embedding, n_results])

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "document": row[0],
            "metadata": {
                "project_id": row[1],
                "doc_type":   row[2],
                "year":       row[3],
                "file_name":  row[4],
            },
            "distance": row[5],
        }
        for row in rows
    ]


@tool
def search_contract_price(material_name: str) -> str:
    """
    사내 문서(계약서, 견적서, 기성청구서)에서 특정 자재의 과거 계약단가를 전체 공사별로 조회합니다.
    모든 프로젝트의 계약단가를 반환하므로, 에이전트는 공사별 단가를 비교하고
    현재 조달청 단가 대비 절감률 등을 분석하여 리포트를 작성해야 합니다.

    Args:
        material_name: 조회할 자재명 (예: "철근 SD400", "합판", "레미콘", "H형강")
    """
    try:
        chunks  = search_raw(f"{material_name} 계약단가", n_results=N_RESULTS)
        keyword = material_name.split()[0]

        if not chunks:
            return json.dumps({
                "status":  "not_found",
                "query":   material_name,
                "message": "사내 문서에서 관련 계약단가를 찾을 수 없습니다. embed.py 실행 여부를 확인하세요.",
            }, ensure_ascii=False, indent=2)

        by_project: dict[str, dict] = {}

        for chunk in chunks:
            meta       = chunk["metadata"]
            project_id = meta.get("project_id", "unknown")
            year       = meta.get("year", "")
            file_name  = meta.get("file_name", "")
            doc_type   = meta.get("doc_type", "")
            proj_key   = f"{project_id}_{year}"

            prices   = _extract_prices(chunk["document"])
            relevant = [p for p in prices if keyword in p["자재명"]]

            if not relevant:
                if proj_key not in by_project:
                    by_project[proj_key] = {
                        "공사명": project_id, "연도": year,
                        "문서유형": doc_type, "출처파일": file_name,
                        "계약단가목록": [], "원문_참고": chunk["document"][:200],
                    }
                continue

            if proj_key not in by_project:
                by_project[proj_key] = {
                    "공사명": project_id, "연도": year,
                    "문서유형": doc_type, "출처파일": file_name,
                    "계약단가목록": [], "원문_참고": "",
                }

            for p in relevant:
                existing = [e["단가"] for e in by_project[proj_key]["계약단가목록"]]
                if p["단가"] not in existing:
                    by_project[proj_key]["계약단가목록"].append({
                        "자재명": p["자재명"], "단가": p["단가"], "단위": p["단위"],
                    })

        projects_with_price = {k: v for k, v in by_project.items() if v["계약단가목록"]}

        if not projects_with_price:
            return json.dumps({
                "status":  "found_context",
                "query":   material_name,
                "message": "관련 문서는 검색됐으나 단가 패턴을 자동 추출하지 못했습니다. 아래 원문을 참고하세요.",
                "context": [
                    {"원문": c["document"][:300], "출처파일": c["metadata"].get("file_name", ""),
                     "공사명": c["metadata"].get("project_id", ""), "연도": c["metadata"].get("year", "")}
                    for c in chunks[:3]
                ],
            }, ensure_ascii=False, indent=2)

        sorted_projects = sorted(projects_with_price.values(), key=lambda x: x["연도"])
        all_prices = [p["단가"] for proj in sorted_projects for p in proj["계약단가목록"]]

        return json.dumps({
            "status": "success",
            "query":  material_name,
            "안내":   "아래 공사별 계약단가를 현재 조달청 단가와 비교하여 절감률, 추이, 협상 근거를 리포트에 포함하세요.",
            "공사별_계약단가": sorted_projects,
            "통계": {
                "공사_수":       len(sorted_projects),
                "최저_계약단가": min(all_prices),
                "최고_계약단가": max(all_prices),
                "평균_계약단가": round(sum(all_prices) / len(all_prices)),
            },
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"status": "error", "message": f"검색 오류: {str(e)}"}, ensure_ascii=False)


@tool
def list_contract_documents() -> str:
    """
    사내 문서 DB에 저장된 문서 목록과 공사별 계약 현황을 반환합니다.
    어떤 프로젝트의 계약단가를 조회할 수 있는지 확인할 때 사용합니다.
    """
    try:
        conn = get_connection()
        cur  = conn.cursor()

        cur.execute("""
            SELECT file_name, doc_type, project_id, year, COUNT(*) AS chunk_count
            FROM rag.company_docs
            GROUP BY file_name, doc_type, project_id, year
            ORDER BY year, project_id
        """)
        rows = cur.fetchall()

        cur.execute("SELECT COUNT(*) FROM rag.company_docs")
        total_chunks = cur.fetchone()[0]

        cur.close()
        conn.close()

        docs = [
            {"문서유형": r[1], "공사명": r[2], "연도": r[3], "청크수": r[4]}
            for r in rows
        ]

        return json.dumps({
            "status":    "success",
            "총_문서수": len(docs),
            "총_청크수": total_chunks,
            "문서_목록": docs,
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"status": "error", "message": f"오류: {str(e)}"}, ensure_ascii=False)


# ── 직접 실행 테스트 ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=str, default="철근 SD400 계약단가")
    parser.add_argument("--list",  action="store_true", help="문서 목록 조회")
    args = parser.parse_args()

    if args.list:
        print(list_contract_documents.invoke({}))
    else:
        print(f"\n[검색] '{args.query}'")
        print(search_contract_price.invoke({"material_name": args.query}))
