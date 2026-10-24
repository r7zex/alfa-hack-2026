from hashlib import sha256
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

    async def upload(self, application_id, owner, upload):
        await ApplicationService(self.session).get(application_id, owner)
        try:
            if upload.content_type != "application/pdf":
                raise HTTPException(415, "Only application/pdf is supported")
            content = await upload.read(MAX_PDF_BYTES + 1)
            if len(content) > MAX_PDF_BYTES:
                raise HTTPException(413, "PDF exceeds 10 MiB")
            signature = await run_in_threadpool(verify_pdf_signatures, content)
            if signature["status"] == "invalid_pdf":
                raise HTTPException(422, "Invalid PDF")
            if signature["status"] == "unsupported_pdf":
                raise HTTPException(422, "Encrypted PDF is unsupported")
            filename = PurePosixPath((upload.filename or "document.pdf").replace(chr(92), "/")).name
            filename = "".join(c for c in filename if c.isprintable())[:255] or "document.pdf"
            return await self.repo.add(Document(
                application_id=application_id, filename=filename, content_type="application/pdf",
                size=len(content), sha256=sha256(content).hexdigest(), content=content, signature=signature))
        except OSError as exc:
            raise HTTPException(503, "Cannot read uploaded PDF") from exc
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise HTTPException(503, "Cannot persist document") from exc
        finally:
            await upload.close()

    async def get(self, document_id, owner, *, with_content=False):
        try:
            row = await self.repo.get_owned(document_id, owner, with_content=with_content)
        except SQLAlchemyError as exc:
            raise HTTPException(503, "Cannot read document") from exc
        if row is None:
            raise HTTPException(404, "Document not found")
        return row
