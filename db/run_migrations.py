#!/usr/bin/env python3
"""
DB 마이그레이션 실행 스크립트
- migrations/ 폴더의 SQL 파일들을 순서대로 실행
"""
import os
import sys
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "construction_risk_agent")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def run_migrations():
    """마이그레이션 파일 실행"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        cursor = conn.cursor()

        # 마이그레이션 파일 정렬 (001, 002, ... 순서)
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

        if not migration_files:
            print("❌ 마이그레이션 파일을 찾을 수 없습니다.")
            sys.exit(1)

        for migration_file in migration_files:
            print(f"실행 중: {migration_file.name}...")
            with open(migration_file, 'r', encoding='utf-8') as f:
                sql = f.read()

            try:
                cursor.execute(sql)
                conn.commit()
                print(f"✅ {migration_file.name} 완료")
            except Exception as e:
                conn.rollback()
                print(f"❌ {migration_file.name} 실패: {e}")
                raise

        cursor.close()
        conn.close()
        print("\n✅ 모든 마이그레이션이 완료되었습니다!")

    except Exception as e:
        print(f"❌ DB 연결 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_migrations()
