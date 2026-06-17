"""Projects 라우터"""

from fastapi import APIRouter, HTTPException, status
from datetime import datetime
import uuid

from api.database import get_db_cursor, dict_from_row
from api.models import ProjectCreate, Project

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[Project])
async def list_projects():
    """프로젝트 목록 조회 (__quick__ 제외, created_at 내림차순)"""
    with get_db_cursor() as (cursor, conn):
        cursor.execute("""
            SELECT id, name, description, created_at
            FROM projects
            WHERE id != '00000000-0000-0000-0000-000000000001'
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        return [dict_from_row(r) for r in rows]


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(req: ProjectCreate):
    """프로젝트 생성"""
    project_id = str(uuid.uuid4())
    now = datetime.utcnow()

    with get_db_cursor() as (cursor, conn):
        cursor.execute("""
            INSERT INTO projects (id, name, description, created_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, description, created_at
        """, (project_id, req.name, req.description or "", now))
        conn.commit()
        row = cursor.fetchone()
        return dict_from_row(row)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str):
    """프로젝트 삭제 (기본 프로젝트 제외)"""
    # 기본 프로젝트 보호
    if project_id == "00000000-0000-0000-0000-000000000001":
        raise HTTPException(status_code=400, detail="Cannot delete default project")

    with get_db_cursor() as (cursor, conn):
        # 존재 확인
        cursor.execute("SELECT id FROM projects WHERE id = %s", (project_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Project not found")

        # 삭제
        cursor.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        conn.commit()

    return None
