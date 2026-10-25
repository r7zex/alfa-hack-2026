"""Server PDF storage with shared session, CSRF and business access checks."""
from uuid import UUID
from typing import Annotated, Literal
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import select, or_
from app.api.applications import Client, Session, get_business_id
from app.dependencies import Auth
from app.models.auth import UserRole
from app.models.document import Document
from app.schemas.document import DocumentRead
from app.services.document_service import DocumentService

router = APIRouter(prefix='/api/documents', tags=['Documents'])
DocumentType = Literal['statement', 'accounts', 'tax', 'invoice']


@router.get('', response_model=list[DocumentRead])
async def list_documents(db: Session, user: Client):
    return list((await db.scalars(select(Document).where(Document.business_id == get_business_id(user))
                                  .order_by(Document.created_at.desc()).limit(100))).all())


@router.post('', response_model=DocumentRead, status_code=201)
async def upload_profile_document(db: Session, user: Client, file: Annotated[UploadFile, File()],
                                  document_type: Annotated[DocumentType, Form()] = 'statement'):
    return await DocumentService(db).upload(None, get_business_id(user), file, document_type, user.id)


@router.post('/{application_id}', response_model=DocumentRead, status_code=201)
async def upload_document(application_id: UUID, db: Session, user: Client,
                          file: Annotated[UploadFile, File()],
                          document_type: Annotated[DocumentType, Form()] = 'statement'):
    return await DocumentService(db).upload(application_id, get_business_id(user), file, document_type, user.id)


@router.get('/{document_id}', response_model=DocumentRead)
async def get_document(document_id: UUID, db: Session, auth: Auth):
    return await DocumentService(db).get(document_id, auth.user.business_id, admin=auth.user.role == UserRole.ADMIN)


@router.get('/{document_id}/content')
async def read_document(document_id: UUID, db: Session, auth: Auth):
    row = await DocumentService(db).get(document_id, auth.user.business_id, with_content=True,
                                        admin=auth.user.role == UserRole.ADMIN)
    return Response(row.content, media_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="{row.id}.pdf"',
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
    })
