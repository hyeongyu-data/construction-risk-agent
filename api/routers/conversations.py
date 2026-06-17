"""Conversations 라우터"""

from fastapi import APIRouter, HTTPException, status
from datetime import datetime
import uuid

from api.database import get_db_cursor, dict_from_row
from api.models import ConversationCreate, ConversationUpdate, Conversation

router = APIRouter(tags=["conversations"])


# ── Quick Conversations (기본 프로젝트) ──────────────────────────

@router.get("/conversations/quick", response_model=list[Conversation])
async def list_quick_conversations():
    """빠른 질문 대화 목록 (프로젝트 ID: 00000000-...001)"""
    default_project_id = "00000000-0000-0000-0000-000000000001"

    with get_db_cursor() as (cursor, conn):
        cursor.execute("""
            SELECT id, project_id, title, created_at
            FROM conversations
            WHERE project_id = %s
            ORDER BY created_at DESC
        """, (default_project_id,))
        rows = cursor.fetchall()
        return [dict_from_row(r) for r in rows]


@router.post("/conversations/quick", response_model=Conversation, status_code=status.HTTP_201_CREATED)
async def create_quick_conversation(req: ConversationCreate):
    """빠른 질문 대화 생성"""
    default_project_id = "00000000-0000-0000-0000-000000000001"
    conv_id = str(uuid.uuid4())
    now = datetime.utcnow()

    with get_db_cursor() as (cursor, conn):
        cursor.execute("""
            INSERT INTO conversations (id, project_id, title, created_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id, project_id, title, created_at
        """, (conv_id, default_project_id, req.title, now))
        conn.commit()
        row = cursor.fetchone()
        return dict_from_row(row)


# ── Project Conversations ────────────────────────────────────────

@router.get("/projects/{project_id}/conversations", response_model=list[Conversation])
async def list_project_conversations(project_id: str):
    """프로젝트의 대화 목록"""
    with get_db_cursor() as (cursor, conn):
        # 프로젝트 존재 확인
        cursor.execute("SELECT id FROM projects WHERE id = %s", (project_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Project not found")

        # 대화 조회
        cursor.execute("""
            SELECT id, project_id, title, created_at
            FROM conversations
            WHERE project_id = %s
            ORDER BY created_at DESC
        """, (project_id,))
        rows = cursor.fetchall()
        return [dict_from_row(r) for r in rows]


@router.post("/projects/{project_id}/conversations", response_model=Conversation, status_code=status.HTTP_201_CREATED)
async def create_project_conversation(project_id: str, req: ConversationCreate):
    """프로젝트 대화 생성"""
    with get_db_cursor() as (cursor, conn):
        # 프로젝트 존재 확인
        cursor.execute("SELECT id FROM projects WHERE id = %s", (project_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Project not found")

        # 대화 생성
        conv_id = str(uuid.uuid4())
        now = datetime.utcnow()
        cursor.execute("""
            INSERT INTO conversations (id, project_id, title, created_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id, project_id, title, created_at
        """, (conv_id, project_id, req.title, now))
        conn.commit()
        row = cursor.fetchone()
        return dict_from_row(row)


# ── Conversation Update / Delete ─────────────────────────────────

@router.patch("/conversations/{conv_id}", response_model=dict)
async def update_conversation(conv_id: str, req: ConversationUpdate):
    """대화 제목 수정"""
    with get_db_cursor() as (cursor, conn):
        # 존재 확인
        cursor.execute("SELECT id FROM conversations WHERE id = %s", (conv_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Conversation not found")

        # 수정
        cursor.execute("""
            UPDATE conversations SET title = %s WHERE id = %s
            RETURNING id, title
        """, (req.title, conv_id))
        conn.commit()
        row = cursor.fetchone()
        return dict_from_row(row)


@router.delete("/conversations/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conv_id: str):
    """대화 삭제"""
    with get_db_cursor() as (cursor, conn):
        # 존재 확인
        cursor.execute("SELECT id FROM conversations WHERE id = %s", (conv_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Conversation not found")

        # 삭제
        cursor.execute("DELETE FROM conversations WHERE id = %s", (conv_id,))
        conn.commit()

    return None
