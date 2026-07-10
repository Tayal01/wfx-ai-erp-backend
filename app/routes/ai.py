from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.auth_service import get_current_user
from app.services.vanna_service import answer_erp_question, get_vanna_status, stream_erp_answer


router = APIRouter()


class AIChatRequest(BaseModel):
    question: str = Field(min_length=4, max_length=500)


class AIChatResponse(BaseModel):
    question: str
    sql: str
    row_count: int
    rows: list[dict]
    summary: str


@router.get("/status")
def ai_status() -> dict[str, str]:
    status_value = get_vanna_status()
    detail_map = {
        "configured": "AI SQL assistant is configured with OpenRouter and database access.",
        "llm_only": "OpenRouter is configured, but DATABASE_URL is still missing.",
        "not_configured": "OpenRouter and database access are not configured yet.",
    }
    return {
        "service": "ai",
        "status": status_value,
        "detail": detail_map[status_value],
    }


@router.post("/chat", response_model=AIChatResponse)
def ai_chat(
    payload: AIChatRequest,
    _current_user: dict = Depends(get_current_user),
) -> AIChatResponse:
    try:
        result = answer_erp_question(payload.question)
        return AIChatResponse(**result)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to answer ERP question: {exc}",
        ) from exc


@router.post("/chat/stream")
def ai_chat_stream(
    payload: AIChatRequest,
    _current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    def event_stream():
        try:
            for event, data in stream_erp_answer(payload.question):
                yield f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
        except ValueError as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
        except RuntimeError as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"event: error\ndata: {json.dumps({'detail': f'Unable to answer ERP question: {exc}'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
