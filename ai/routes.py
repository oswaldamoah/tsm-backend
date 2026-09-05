"""AI assistant endpoints: /ai/status, /ai/chat, /ai/presentation.pptx"""

from typing import List, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_active_user
from database import get_db
from models import CompanySetting

from .agent import answer_question
from .provider import LLMError, get_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


# ========== SCHEMAS ==========

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: Optional[List[ChatMessage]] = None


class ChartSeries(BaseModel):
    name: str
    values: List[float]


class ChartSpec(BaseModel):
    title: str
    type: str
    categories: List[str]
    series: List[ChartSeries]
    xLabel: Optional[str] = ""
    yLabel: Optional[str] = ""


class SlideSpec(BaseModel):
    title: str
    bullets: List[str] = []
    chartIndex: Optional[int] = None
    notes: Optional[str] = ""


class PresentationSpec(BaseModel):
    title: str
    subtitle: Optional[str] = ""
    slides: List[SlideSpec]


class PresentationRequest(BaseModel):
    presentation: PresentationSpec
    charts: List[ChartSpec] = []


# ========== HELPERS ==========

def _company_name(db: Session) -> Optional[str]:
    settings = db.query(CompanySetting).filter(CompanySetting.id == "company").first()
    return settings.name if settings else None


# ========== ROUTES ==========

@router.get("/status")
def ai_status(current_user=Depends(get_current_active_user)):
    """Whether the assistant is usable, so the UI can hide or explain itself."""
    try:
        provider = get_provider()
    except LLMError as exc:
        return {"enabled": False, "reason": str(exc)}

    # Show the whole failover chain so it's obvious what will cover a rate limit.
    chain = getattr(provider, "providers", [provider])
    return {
        "enabled": True,
        "provider": provider.name,
        "model": provider.model,
        "fallbacks": [f"{p.name}:{p.model}" for p in chain[1:]],
    }


@router.post("/chat")
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Ask a question about the data. May return charts and a slide deck."""
    history = [{"role": m.role, "content": m.content} for m in (request.history or [])]
    role = getattr(current_user.role, "value", current_user.role)

    try:
        return answer_question(
            db=db,
            question=request.message,
            history=history,
            company_name=_company_name(db),
            user_role=str(role) if role else None,
        )
    except LLMError as exc:
        # Provider misconfiguration, rate limits and refusals are the user's problem
        # to act on, so pass the message through rather than a generic 500.
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("AI chat failed")
        raise HTTPException(status_code=500, detail=f"Assistant failed: {exc}")


@router.post("/presentation.pptx")
def download_presentation(
    request: PresentationRequest,
    current_user=Depends(get_current_active_user),
):
    """Render a deck the assistant produced as a downloadable PowerPoint file."""
    try:
        from .slides import build_pptx, safe_filename
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="PowerPoint export needs the python-pptx package. Run: pip install python-pptx",
        )

    try:
        stream = build_pptx(
            request.presentation.model_dump(),
            [chart.model_dump() for chart in request.charts],
        )
    except Exception as exc:
        logger.exception("PPTX build failed")
        raise HTTPException(status_code=500, detail=f"Could not build the deck: {exc}")

    filename = safe_filename(request.presentation.title)
    return StreamingResponse(
        stream,
        media_type=PPTX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
