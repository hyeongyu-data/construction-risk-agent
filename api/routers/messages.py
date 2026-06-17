"""Messages 라우터"""

from fastapi import APIRouter, HTTPException, status

from api.database import get_db_cursor, dict_from_row
from api.models import MessageList

router = APIRouter(tags=["messages"])


@router.get("/conversations/{conv_id}/messages", response_model=MessageList)
async def list_messages(conv_id: str):
    """메시지 목록 조회 (created_at 오름차순)"""
    with get_db_cursor() as (cursor, conn):
        # 대화 존재 확인
        cursor.execute("SELECT id FROM conversations WHERE id = %s", (conv_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Conversation not found")

        # 메시지 조회
        cursor.execute("""
            SELECT role, content, created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at ASC
        """, (conv_id,))
        rows = cursor.fetchall()
        messages = [dict_from_row(r) for r in rows]
        return {"messages": messages}
