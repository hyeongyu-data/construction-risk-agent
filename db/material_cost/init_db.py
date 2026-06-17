"""
자재 단가 SQLite DB 초기화 스크립트
- data/processed/materials_db.csv 를 읽어 SQLite DB에 저장
- 실행 전 preprocess_materials.py 를 먼저 실행해야 합니다
"""

import sqlite3
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CSV_PATH = BASE_DIR / "data" / "processed" / "materials_db.csv"
DB_PATH = BASE_DIR / "db" / "material_cost.db"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS material_prices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    자재명           TEXT    NOT NULL,
    단위             TEXT,
    현재단가          INTEGER NOT NULL,
    자재분류          TEXT,
    품목분류          TEXT,
    공시일자          TEXT,
    시황성자재         INTEGER DEFAULT 0,   -- 0: False, 1: True
    부가세여부         TEXT
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_material_name ON material_prices (자재명);
"""


def init_db():
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"전처리 CSV가 없습니다. 먼저 scripts/preprocess_materials.py 를 실행하세요.\n경로: {CSV_PATH}"
        )

    print(f"CSV 로드 중: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")

    # 시황성자재 bool → int 변환 (SQLite는 bool 미지원)
    if "시황성자재" in df.columns:
        df["시황성자재"] = df["시황성자재"].astype(int)

    # 공시일자 문자열 변환
    if "공시일자" in df.columns:
        df["공시일자"] = df["공시일자"].astype(str)

    print(f"DB 초기화 중: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 테이블 생성
    cursor.execute(CREATE_TABLE_SQL)
    cursor.execute(CREATE_INDEX_SQL)

    # 기존 데이터 삭제 후 재삽입 (재실행 안전)
    cursor.execute("DELETE FROM material_prices")

    # 데이터 삽입
    columns = ["자재명", "단위", "현재단가", "자재분류", "품목분류", "공시일자", "시황성자재", "부가세여부"]
    existing_cols = [c for c in columns if c in df.columns]
    df[existing_cols].to_sql("material_prices", conn, if_exists="append", index=False)

    conn.commit()
    count = cursor.execute("SELECT COUNT(*) FROM material_prices").fetchone()[0]
    conn.close()

    print(f"✅ DB 저장 완료: {count:,}개 자재")


if __name__ == "__main__":
    init_db()
