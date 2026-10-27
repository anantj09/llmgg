import asyncio

import app.guards  # noqa: F401
from app.core.context import RequestContext
from app.core.types import Action, Stage
from app.guards._checksums import luhn_valid, verhoeff_check_digit, verhoeff_valid
from app.guards.pii import ALL_ENTITIES, PIIGuard, find_pii


def labels(text):
    return [s.label for s in find_pii(text, set(ALL_ENTITIES))]


def test_detects_common_entities():
    assert labels("mail a.b@example.co.in") == ["EMAIL"]
    assert labels("call +91 98765 43210") == ["PHONE"]
    assert labels("call (415) 555-0132") == ["PHONE"]
    assert labels("PAN: ABCDE1234F") == ["PAN"]
    assert labels("ssn 123-45-6789") == ["SSN"]
    assert labels("host 192.168.1.20") == ["IP_ADDRESS"]


def test_checksums_reduce_false_positives():
    assert luhn_valid("4111111111111111")
    assert not luhn_valid("4111111111111112")
    assert labels("card 4111 1111 1111 1111") == ["CREDIT_CARD"]
    assert "CREDIT_CARD" not in labels("order 4111 1111 1111 1112")

    aadhaar = "23456789012" + verhoeff_check_digit("23456789012")
    assert verhoeff_valid(aadhaar)
    assert labels(f"aadhaar {aadhaar}") == ["AADHAAR"]
    assert "AADHAAR" not in labels("ref 2345 6789 0120")


def test_invalid_ip_ignored():
    assert labels("version 999.1.1.1") == []


def test_input_redaction_is_reversible_and_stable():
    guard = PIIGuard(action=Action.REDACT)
    ctx = RequestContext("t", stage=Stage.INPUT)
    text = "x@y.com wrote to x@y.com again"
    r = asyncio.run(guard.run(text, ctx))
    assert r.output_text == "<EMAIL_1> wrote to <EMAIL_1> again"
    assert ctx.restore(r.output_text) == text


def test_output_redaction_is_permanent():
    guard = PIIGuard(action=Action.REDACT)
    ctx = RequestContext("t", stage=Stage.OUTPUT)
    r = asyncio.run(guard.run("contact ops@corp.com", ctx))
    assert r.output_text == "contact [EMAIL]"
    assert ctx.vault == {}


def test_findings_never_contain_raw_values():
    guard = PIIGuard(action=Action.REDACT)
    r = asyncio.run(guard.run("mail secret.person@example.com", RequestContext("t")))
    assert "secret.person" not in str(r.to_dict())
