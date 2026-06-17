"""
Material Price Tool
- PostgreSQL DB에서 자재명으로 단가를 조회하는 LangChain Tool
- 퍼지 검색(유사 자재명 매칭) 지원
"""

import os
import json
import difflib
from pathlib import Path
from dotenv import load_dotenv

import psycopg2
import psycopg2.extras
from langchain_core.tools import tool

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

# ── DB 접속 정보 ──────────────────────────────────────────────────
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_NAME     = os.getenv("DB_NAME", "material_cost")
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")


def _get_connection() -> psycopg2.extensions.connection:
    try:
        return psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    except psycopg2.OperationalError as e:
        raise ConnectionError(
            f"DB 접속 실패. .env의 DB_* 환경변수를 확인하세요.\n원인: {e}"
        )


def _fuzzy_search(query: str, top_n: int = 5) -> list[dict]:
    """
    자재명 퍼지 검색.
    1) SQL LIKE로 포함 검색 우선
    2) 부족하면 전체 자재명 목록에서 difflib 유사도 검색으로 보완
    """
    conn = _get_connection()
    cursor = conn.cursor()

    # 1단계: LIKE 검색 (psycopg2는 %s 플레이스홀더 사용)
    cursor.execute(
        "SELECT * FROM material_prices WHERE 자재명 LIKE %s LIMIT %s",
        (f"%{query}%", top_n),
    )
    rows = [dict(row) for row in cursor.fetchall()]

    if len(rows) >= top_n:
        conn.close()
        return rows

    # 2단계: difflib 유사도 검색으로 보완
    cursor.execute("SELECT DISTINCT 자재명 FROM material_prices")
    all_names = [r["자재명"] for r in cursor.fetchall()]
    close_matches = difflib.get_close_matches(query, all_names, n=top_n, cutoff=0.3)

    if close_matches:
        placeholders = ",".join(["%s"] * len(close_matches))
        cursor.execute(
            f"SELECT * FROM material_prices WHERE 자재명 IN ({placeholders}) LIMIT %s",
            (*close_matches, top_n),
        )
        fuzzy_rows = [dict(row) for row in cursor.fetchall()]
        existing_names = {r["자재명"] for r in rows}
        rows += [r for r in fuzzy_rows if r["자재명"] not in existing_names]

    conn.close()
    return rows[:top_n]


@tool
def search_material_price(material_name: str) -> str:
    """
    자재명으로 조달청 단가를 조회합니다.

    Args:
        material_name: 조회할 자재명 (예: "H파일", "시멘트", "철근")

    Returns:
        자재 단가 정보 (현재단가, 계약단가, 단위, 시황성 여부 등)
    """
    try:
        rows = _fuzzy_search(material_name, top_n=5)

        if not rows:
            return json.dumps(
                {
                    "status": "not_found",
                    "query": material_name,
                    "message": f"'{material_name}'에 해당하는 자재를 찾을 수 없습니다.",
                },
                ensure_ascii=False,
                indent=2,
            )

        # 계약단가 조회 (contract DB가 있을 때)
        contract_map = {}
        try:
            contract_conn = psycopg2.connect(
                host=DB_HOST, port=DB_PORT,
                dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
            cc = contract_conn.cursor()
            for row in rows:
                cc.execute(
                    "SELECT 계약단가, 계약유형 FROM contract_prices WHERE 자재명 LIKE %s LIMIT 1",
                    (f"%{row['자재명'][:5]}%",),
                )
                r = cc.fetchone()
                if r:
                    contract_map[row["자재명"]] = dict(r)
            contract_conn.close()
        except Exception:
            pass  # contract_prices 테이블 없으면 무시

        items = []
        for row in rows:
            item = {
                "자재명": row["자재명"],
                "단위": row.get("단위", "-"),
                "현재단가_원": row["현재단가"],
                "자재분류": row.get("자재분류", "-"),
                "품목분류": row.get("품목분류", "-"),
                "공시일자": row.get("공시일자", "-"),
                "시황성자재": bool(row.get("시황성자재", False)),
                "부가세여부": row.get("부가세여부", "부가가치세별도"),
            }
            if row["자재명"] in contract_map:
                item["계약단가_원"] = contract_map[row["자재명"]]["계약단가"]
                item["계약유형"] = contract_map[row["자재명"]]["계약유형"]
            else:
                item["계약단가_원"] = None
                item["계약유형"] = "계약 DB 미연동 (팀원 B 샘플 DB 필요)"

            items.append(item)

        return json.dumps(
            {
                "status": "success",
                "query": material_name,
                "result_count": len(items),
                "results": items,
            },
            ensure_ascii=False,
            indent=2,
        )

    except ConnectionError as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"조회 중 오류: {str(e)}"}, ensure_ascii=False
        )


@tool
def list_material_categories() -> str:
    """
    DB에 있는 자재 분류 목록과 자재 수를 반환합니다.
    어떤 자재를 조회할 수 있는지 확인할 때 사용합니다.
    """
    try:
        conn = _get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 자재분류, COUNT(*) as 자재수 FROM material_prices GROUP BY 자재분류 ORDER BY 자재수 DESC"
        )
        categories = {row["자재분류"]: row["자재수"] for row in cursor.fetchall()}

        sample_materials = {}
        for cat in categories:
            cursor.execute(
                "SELECT 자재명 FROM material_prices WHERE 자재분류 = %s LIMIT 3", (cat,)
            )
            sample_materials[cat] = [r["자재명"] for r in cursor.fetchall()]

        cursor.execute("SELECT COUNT(*) as cnt FROM material_prices")
        total = cursor.fetchone()["cnt"]
        conn.close()

        return json.dumps(
            {
                "status": "success",
                "total_materials": total,
                "categories": categories,
                "sample_materials": sample_materials,
            },
            ensure_ascii=False,
            indent=2,
        )
    except ConnectionError as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"조회 오류: {str(e)}"}, ensure_ascii=False)
