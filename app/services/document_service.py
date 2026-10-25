from hashlib import sha256
from uuid import uuid4
from sqlalchemy import func, select
from app.models.pipeline import ApplicationDocument
from app.services.pipeline import locked, event, EDITABLE
from pathlib import PurePosixPath
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.services.application_service import ApplicationService
from app.services.signature_verification import verify_pdf_signatures

MAX_PDF_BYTES = 10 * 1024 * 1024


class DocumentService:
    def __init__(self, session):
        self.session = session
        self.repo = DocumentRepository(session)

    async def upload(self, application_id, owner, upload, document_type="statement", user_id=None):
        row = await locked(self.session, application_id, owner) if application_id else None
        if row and row.status not in EDITABLE:
            raise HTTPException(409, "Документы отправленной заявки менять нельзя")
        count = await self.session.scalar(select(func.count()).select_from(Document).where(Document.business_id == owner))
        if count >= 100:
            raise HTTPException(422, "Лимит: 100 документов на организацию")
        try:
            if upload.content_type != "application/pdf":
                raise HTTPException(415, "Only application/pdf is supported")
            content = await upload.read(MAX_PDF_BYTES + 1)
            if len(content) > MAX_PDF_BYTES:
                raise HTTPException(413, "PDF exceeds 10 MiB")
            signature = await run_in_threadpool(verify_pdf_signatures, content)
            if signature["status"] == "invalid_pdf":
                raise HTTPException(422, "Invalid PDF")
            if signature["status"] == "invalid_signature" or any(item.get("status") == "invalid_signature" for item in signature.get("signatures", [])):
                raise HTTPException(422, "PDF signature is invalid")
            if signature["status"] == "unsupported_pdf":
                raise HTTPException(422, "Encrypted PDF is unsupported")
            filename = PurePosixPath((upload.filename or "document.pdf").replace(chr(92), "/")).name
            filename = "".join(c for c in filename if c.isprintable())[:255] or "document.pdf"
            doc_id = uuid4()
            if row:
                await event(self.session, row, user_id, row.status, "Прикреплён документ", {"document_id": str(doc_id)})
                self.session.add(ApplicationDocument(application_id=row.id, document_id=doc_id))
            return await self.repo.add(Document(
                id=doc_id, business_id=owner, document_type=document_type, application_id=application_id, filename=filename, content_type="application/pdf",
                size=len(content), sha256=sha256(content).hexdigest(), content=content, signature=signature))
        except OSError as exc:
            raise HTTPException(503, "Cannot read uploaded PDF") from exc
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise HTTPException(503, "Cannot persist document") from exc
        finally:
            await upload.close()

    async def get(self, document_id, owner, *, with_content=False, admin=False):
        try:
            row = await self.repo.get_owned(document_id, owner, with_content=with_content, admin=admin)
        except SQLAlchemyError as exc:
            raise HTTPException(503, "Cannot read document") from exc
        if row is None:
            raise HTTPException(404, "Document not found")
        return row
