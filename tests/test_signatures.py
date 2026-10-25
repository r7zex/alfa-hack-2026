from datetime import datetime, timezone
from io import BytesIO
import re
import pytest
from asn1crypto import x509 as asn1_x509, keys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from pyhanko.sign import signers
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko_certvalidator.registry import SimpleCertificateStore
from app.services.signature_verification import verify_pdf_signatures
from ml_fixtures import pdf_bytes


@pytest.fixture
def signed_pdf():
    # Fixed test key and certificate; never represents a real FNS certificate.
    private_key = ec.derive_private_key(42, ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MOCK TEST SIGNER")])
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(private_key.public_key()).serial_number(1)
        .not_valid_before(datetime(2020, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime(2040, 1, 1, tzinfo=timezone.utc))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True,
             key_encipherment=False, data_encipherment=False, key_agreement=False,
             key_cert_sign=True, crl_sign=True, encipher_only=None, decipher_only=None), critical=True)
        .sign(private_key, hashes.SHA256()))
    cert = asn1_x509.Certificate.load(certificate.public_bytes(serialization.Encoding.DER))
    key = keys.PrivateKeyInfo.load(private_key.private_bytes(serialization.Encoding.DER,
                    serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    signer = signers.SimpleSigner(signing_cert=cert, signing_key=key, cert_registry=SimpleCertificateStore())
    output = BytesIO()
    signers.sign_pdf(IncrementalPdfFileWriter(BytesIO(pdf_bytes())),
                     signers.PdfSignatureMetadata(field_name="FixtureSignature"), signer=signer, output=output)
    return output.getvalue(), cert


def test_unsigned_and_malformed_pdf():
    result = verify_pdf_signatures(pdf_bytes())
    assert result["status"] == "unsigned" and not result["signature_present"]
    assert result["fns_authenticity"] == "not_established"
    assert verify_pdf_signatures(b"invalid")["status"] == "invalid_pdf"
    assert verify_pdf_signatures(b"%PDF-1.7 invalid")["status"] == "invalid_pdf"


def test_crypto_valid_but_trust_incomplete_without_roots(signed_pdf, monkeypatch):
    import socket
    def forbidden(*args, **kwargs):
        pytest.fail("Offline signature validation attempted network I/O")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    result = verify_pdf_signatures(signed_pdf[0])
    assert result["signature_present"] and result["status"] == "signed"
    signature = result["signatures"][0]
    assert signature["cryptographic_valid"] and signature["signed_bytes_intact"]
    assert signature["whole_document_covered"] and signature["trust"] == "unverified"
    assert not result["revocation_checked"] and result["fns_authenticity"] == "not_established"


def test_explicit_trust_is_distinct_from_fns_authenticity(signed_pdf):
    result = verify_pdf_signatures(signed_pdf[0], trusted_certificates=[signed_pdf[1]])
    assert result["signatures"][0]["trust"] == "trusted"
    assert result["fns_authenticity"] == "not_established"


def test_tampered_signed_bytes(signed_pdf):
    data = signed_pdf[0]
    tampered = data.replace(b"200 200", b"201 200", 1)
    assert tampered != data
    result = verify_pdf_signatures(tampered)
    assert result["signature_present"]
    assert result["signatures"][0]["status"] == "invalid_signature"
    assert result["signatures"][0]["signed_bytes_intact"] is False


def test_corrupted_cms(signed_pdf):
    data = signed_pdf[0]
    match = re.search(rb"/Contents\s*<([0-9a-fA-F]+)>", data)
    assert match
    position = match.start(1)
    broken = data[:position] + b"00" + data[position + 2:]
    result = verify_pdf_signatures(broken)
    assert result["signature_present"] and result["status"] == "invalid_signature"


def test_unsupported_algorithm_is_not_valid(signed_pdf, monkeypatch):
    def unsupported(*args, **kwargs):
        raise NotImplementedError("Unsupported signature algorithm")
    monkeypatch.setattr("app.services.signature_verification.validate_pdf_signature", unsupported)
    result = verify_pdf_signatures(signed_pdf[0])
    assert result["signatures"][0]["status"] == "unsupported_signature"
    assert result["signatures"][0]["cryptographic_valid"] is None


def test_encrypted_pdf_has_separate_unsupported_status():
    from pyhanko.pdf_utils.writer import PdfFileWriter
    writer = PdfFileWriter()
    writer.encrypt("owner-test-only", "user-test-only")
    output = BytesIO()
    writer.write(output)
    result = verify_pdf_signatures(output.getvalue())
    assert result["status"] == "unsupported_pdf"
    assert result["fns_authenticity"] == "not_established"
