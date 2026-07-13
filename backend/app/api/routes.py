from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from backend.app.rag.engine import rag_engine
from backend.app.services.document_service import save_upload


router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)


class AskResponse(BaseModel):
    answer: str
    sources: list[str]


class StudyNotesRequest(BaseModel):
    topic: str | None = Field(
        default=None,
        description="Optional topic or chapter focus. Leave empty for broad notes.",
    )


class StudyNotesResponse(BaseModel):
    notes: str
    sources: list[str]


@router.post("/upload")
async def upload_textbook(file: UploadFile = File(...)) -> dict[str, str | int]:
    filename = file.filename or ""
    is_pdf = file.content_type == "application/pdf" or filename.lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    saved_path = await save_upload(file)
    indexed_nodes = rag_engine.ingest_pdf(saved_path)

    return {
        "filename": file.filename or saved_path.name,
        "saved_as": saved_path.name,
        "indexed_nodes": indexed_nodes,
    }


@router.post("/ask", response_model=AskResponse)
def ask_question(payload: AskRequest) -> AskResponse:
    answer, sources = rag_engine.answer_question(payload.question)
    return AskResponse(answer=answer, sources=sources)


@router.post("/study-notes", response_model=StudyNotesResponse)
def create_study_notes(payload: StudyNotesRequest) -> StudyNotesResponse:
    notes, sources = rag_engine.generate_study_notes(payload.topic)
    return StudyNotesResponse(notes=notes, sources=sources)
