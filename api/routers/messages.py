"""Messages 라우터"""

from fastapi import APIRouter, Depends, HTTPException, status

from api.database import get_db_cursor, dict_from_row
from api.models import MessageList
from api.security import get_current_user

router = APIRouter(tags=["messages"])


@router.get("/conversations/{conv_id}/messages", response_model=MessageList)
async def list_messages(conv_id: str, current_user: dict = Depends(get_current_user)):
    """메시지 목록 조회 (created_at 오름차순)"""
    with get_db_cursor() as (cursor, conn):
        # 대화 존재 확인 + 권한 체크
        cursor.execute("""
            SELECT id, project_id, owner_id FROM conversations WHERE id = %s
        """, (conv_id,))
        conv_row = cursor.fetchone()
        if not conv_row:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conv_dict = dict_from_row(conv_row)
        is_owner = str(conv_dict["owner_id"]) == current_user["user_id"]
        if not is_owner:
            cursor.execute(
                "SELECT id FROM project_members WHERE project_id = %s AND user_id = %s",
                (conv_dict["project_id"], current_user["user_id"]),
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="권한이 없습니다")

        # 메시지 조회
        cursor.execute("""
            SELECT id, conversation_id, role, content, structured_response, agent, created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at ASC
        """, (conv_id,))
        rows = cursor.fetchall()
        def to_msg(r):
            d = dict_from_row(r)
            created_at = d.get("created_at")
            if created_at and hasattr(created_at, "isoformat"):
                d["created_at"] = created_at.isoformat() + "Z"
            return {
                **d,
                "id": str(d["id"]),
                "conversation_id": str(d["conversation_id"]),
                "final_response": d["content"] if d.get("role") == "assistant" else None,
            }
        messages = [to_msg(r) for r in rows]
        return {"messages": messages}
