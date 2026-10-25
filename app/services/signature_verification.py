"""Offline PDF/CMS validation. No issuer identity inferred from certificate text."""
from io import BytesIO
from cryptography.exceptions import UnsupportedAlgorithm
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.sign.validation.status import SignatureCoverageLevel
from pyhanko_certvalidator import ValidationContext
from pyhanko_certvalidator.policy_decl import (
    CertRevTrustPolicy, RevocationCheckingPolicy, RevocationCheckingRule,
)


def verify_pdf_signatures(content: bytes, *, trusted_certificates=()):
    result = {"status": "invalid_pdf", "signature_present": False, "signatures": [],
              "fns_authenticity": "not_established", "revocation_checked": False,
              "validation_mode": "local_offline"}
    if not content.startswith(b"%PDF-"):
        return result
    try:
        reader = PdfFileReader(BytesIO(content), strict=True)
        if reader.encrypted:
            result["status"] = "unsupported_pdf"
            return result
        if "/Pages" not in reader.root:
            return result
    except Exception:
        return result
    roots = tuple(trusted_certificates)
    no_check = RevocationCheckingRule.NO_CHECK
    context = ValidationContext(
        trust_roots=roots, allow_fetching=False, crls=(), ocsps=(),
        revinfo_policy=CertRevTrustPolicy(RevocationCheckingPolicy(no_check, no_check)),
    )
    try:
        signatures = reader.embedded_regular_signatures
    except (NotImplementedError, UnsupportedAlgorithm):
        result.update(status="unsupported_signature", signature_present=True)
        return result
    except Exception:
        result.update(status="invalid_signature", signature_present=True)
        return result
    if not signatures:
        result["status"] = "unsigned"
        return result
    result.update(status="signed", signature_present=True)
    for signature in signatures:
        item = {"field_name": signature.field_name, "cryptographic_valid": None,
                "signed_bytes_intact": None, "whole_document_covered": False,
                "trust": "unverified", "status": "unsupported_signature"}
        try:
            status = validate_pdf_signature(signature, signer_validation_context=context,
                                            ts_validation_context=context)
            item.update(cryptographic_valid=bool(status.valid), signed_bytes_intact=bool(status.intact),
                        whole_document_covered=status.coverage == SignatureCoverageLevel.ENTIRE_FILE,
                        trust=("trusted" if status.trusted else "untrusted") if roots else "unverified",
                        status="valid_signature" if status.valid and status.intact else "invalid_signature")
        except (NotImplementedError, UnsupportedAlgorithm):
            pass
        except Exception as exc:
            # Unsupported digest/signature OIDs must never be reported as valid.
            item["status"] = "unsupported_signature" if "algorithm" in str(exc).lower() else "invalid_signature"
        result["signatures"].append(item)
    return result
