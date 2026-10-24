from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response
from app.api.applications import Owner, Session
from app.schemas.document import DocumentRead
from app.services.document_service import DocumentService

router = APIRouter(prefix="/api/documents", tags=["Documents"])


@router.post("/{application_id}", response_model=DocumentRead, status_code=201)
async def upload_document(application_id: UUID, db: Session, owner: Owner,
                          file: Annotated[UploadFile, File()]):
    return await DocumentService(db).upload(application_id, owner, file)


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: UUID, db: Session, owner: Owner):
    return await DocumentService(db).get(document_id, owner)


@router.get("/{document_id}/content")
async def read_document(document_id: UUID, db: Session, owner: Owner):
    row = await DocumentService(db).get(document_id, owner, with_content=True)
    return Response(row.content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{row.id}.pdf"',
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
    })
