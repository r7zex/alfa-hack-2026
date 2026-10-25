from hashlib import sha256
from uuid import uuid4
import pytest
from ml_fixtures import scoring_env, signup, csrf, application, pdf_bytes
from app.services.document_service import MAX_PDF_BYTES


def test_pdf_upload_metadata_content_and_ownership(scoring_env):
    data = pdf_bytes()
    with scoring_env.client() as first, scoring_env.client() as other, scoring_env.client() as guest:
        signup(first)
        signup(other, kind="ip", email="document-other@example.com")
        app_id = application(first)
        url = "/api/documents/" + app_id
        assert guest.post(url, files={"file": ("a.pdf", data, "application/pdf")}).status_code == 401
        assert first.post(url, files={"file": ("a.pdf", data, "application/pdf")}).status_code == 403
        assert other.post(url, headers=csrf(other), files={"file": ("a.pdf", data, "application/pdf")}).status_code == 404
        response = first.post(url, headers=csrf(first), files={"file": ("../../a.pdf", data, "application/pdf")})
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["filename"] == "a.pdf" and body["size"] == len(data)
        assert body["sha256"] == sha256(data).hexdigest()
        assert body["signature"]["status"] == "unsigned"
        doc_url = "/api/documents/" + body["id"]
        assert first.get(doc_url).json() == body
        assert first.get(doc_url + "/content").content == data
        assert "content" not in body
        assert other.get(doc_url).status_code == 404
        assert other.get(doc_url + "/content").status_code == 404
        assert guest.get(doc_url).status_code == 401
        assert first.get("/api/documents/" + str(uuid4())).status_code == 404


@pytest.mark.parametrize("data,mime,status", [
    (b"not PDF", "application/pdf", 422),
    (b"%PDF-1.7 broken", "application/pdf", 422),
    (b"hello", "text/plain", 415),
    (b"%PDF-" + b"x" * MAX_PDF_BYTES, "application/pdf", 413),
])
def test_upload_validation(scoring_env, data, mime, status):
    with scoring_env.client() as client:
        signup(client)
        response = client.post("/api/documents/" + application(client), headers=csrf(client),
                               files={"file": ("test.pdf", data, mime)})
        assert response.status_code == status, response.text


def test_document_read_failure_is_controlled(monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from sqlalchemy.exc import OperationalError
    from app.services.document_service import DocumentService
    service = DocumentService(None)
    async def failed(*args, **kwargs):
        raise OperationalError("fixture", {}, Exception("unavailable"))
    monkeypatch.setattr(service.repo, "get_owned", failed)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(service.get(uuid4(), "user-fixture"))
    assert caught.value.status_code == 503
