"""Pruebas de privacidad con valores exclusivamente sintéticos."""

import pytest

from src.core.telemetry_privacy import TelemetryRejected, prepare_telemetry, redact_telemetry


@pytest.mark.parametrize(
    "payload,secret",
    [
        ("password=example-pass", "example-pass"),
        ('{"api_key": "synthetic-credential"}', "synthetic-credential"),
        ("Authorization: Bearer synthetic-bearer", "synthetic-bearer"),
        ("snmp-server community sample-community RO", "sample-community"),
        ("token: sample-token", "sample-token"),
        ('{"access_token":"sample-access"}', "sample-access"),
        ("client_secret=sample-client", "sample-client"),
        ("refreshToken=sample-refresh", "sample-refresh"),
        ("https://sample-user:sample-pass@router.example/path?auth=123", "sample-pass"),
        ("Contact example.person@example.test", "example.person@example.test"),
        ("source=192.0.2.15/24", "192.0.2.15"),
        ("source=2001:db8::12", "2001:db8::12"),
        ("source=fe80::1234%ether1", "fe80::1234"),
        ("mac=aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff"),
        ("mac=aabb.ccdd.eeff", "aabb.ccdd.eeff"),
        ("neighbor router.private.example", "router.private.example"),
        ("user example-admin logged in", "example-admin"),
        ('username="example admin" connected', "example admin"),
        ("hostname=private-node", "private-node"),
    ],
)
def test_recognized_sensitive_patterns(payload: str, secret: str) -> None:
    assert secret not in redact_telemetry(payload)


def test_preserves_operational_signal() -> None:
    assert redact_telemetry("interface ether1 link down") == "interface ether1 link down"


def test_known_values_redacted_case_insensitively() -> None:
    result = redact_telemetry("PRIVATE-NODE synthetic-value", ("private-node", "synthetic-value"))
    assert result == "[REDACTED] [REDACTED]"


def test_known_value_cannot_disable_sensitive_field_detection() -> None:
    assert "secret-value" not in redact_telemetry("password=secret-value", ("password",))


@pytest.mark.parametrize(
    "payload",
    [
        "-----BEGIN RSA PRIVATE KEY-----\nSYNTHETIC\n-----END RSA PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----\nUNFINISHED",
        "x" * 65537,
        "  \n\t",
    ],
    ids=["pem", "unfinished-pem", "oversize", "empty"],
)
def test_rejects_input_without_exposing_payload(payload: str) -> None:
    with pytest.raises(TelemetryRejected) as caught:
        prepare_telemetry(payload, (), 8000)
    assert payload not in str(caught.value)


def test_redacts_before_size_check() -> None:
    assert prepare_telemetry("password=" + "x" * 1000, (), 256) == "[SENSITIVE_LINE_REMOVED]"
    with pytest.raises(TelemetryRejected):
        prepare_telemetry("event=" + "x" * 300, (), 256)


def test_control_characters_removed() -> None:
    assert redact_telemetry("link\x00 down\u202e") == "link down"
