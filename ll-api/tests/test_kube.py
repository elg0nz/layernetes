import pytest

from app.kube import (
    PUBLIC_KEY_ANNOTATION,
    generate_age_keypair,
    is_valid_k8s_name,
    k8s_name,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("learninglayer_glo", "learninglayer-glo"),
        ("baybuilders_guest1", "baybuilders-guest1"),
        ("layernetes-admin", "layernetes-admin"),  # already valid, unchanged
        ("Mixed_Case", "mixed-case"),  # uppercase folded
        ("_edge_", "edge"),  # leading/trailing separators stripped
        ("first.last", "first-last"),  # dots are invalid in a label
        ("a@b#c$d", "a-b-c-d"),  # any non [a-z0-9-] char -> '-'
        ("foo___bar", "foo-bar"),  # runs collapse
        ("--foo--", "foo"),  # trimmed
    ],
)
def test_k8s_name(raw, expected):
    result = k8s_name(raw)
    assert result == expected
    assert is_valid_k8s_name(result)


def test_k8s_name_all_invalid_gets_stable_fallback():
    # Nothing survives sanitization -> stable, valid, deterministic name.
    a = k8s_name("@@@")
    b = k8s_name("@@@")
    assert a == b
    assert a.startswith("u-")
    assert is_valid_k8s_name(a)


def test_k8s_name_truncates_long_names_with_hash():
    long_user = "x" * 200
    result = k8s_name(long_user)
    assert len(result) <= 63
    assert is_valid_k8s_name(result)
    # Distinct long inputs stay distinct via the hash suffix.
    assert k8s_name("x" * 200 + "a") != result


@pytest.mark.parametrize(
    "value,valid",
    [
        ("learninglayer-glo", True),
        ("a", True),
        ("learninglayer_glo", False),  # underscore
        ("First", False),  # uppercase
        ("-lead", False),  # leading hyphen
        ("trail-", False),  # trailing hyphen
        ("has.dot", False),  # dot not allowed in a label
        ("", False),  # empty
        ("x" * 64, False),  # too long
    ],
)
def test_is_valid_k8s_name(value, valid):
    assert is_valid_k8s_name(value) is valid


def test_ensure_age_key_sanitizes_underscore_username(kube, secret_store):
    kube.ensure_age_key("learninglayer_glo")
    assert "age-key-learninglayer-glo" in secret_store
    assert "age-key-learninglayer_glo" not in secret_store
    # lookup by the raw username still resolves to the sanitized Secret
    assert kube.get_age_public_key("learninglayer_glo") is not None


def test_generate_age_keypair():
    public, identity_file = generate_age_keypair()
    assert public.startswith("age1")
    assert f"# public key: {public}" in identity_file
    assert "AGE-SECRET-KEY-" in identity_file


def test_ensure_age_key_idempotent(kube, secret_store):
    first = kube.ensure_age_key("gonz")
    second = kube.ensure_age_key("gonz")
    assert first == second
    assert secret_store["age-key-gonz"].metadata.annotations[PUBLIC_KEY_ANNOTATION] == first


def test_ensure_age_key_recovers_public_key_without_annotation(kube):
    kube.create_secret("age-key-old", {"age.key": "# public key: age1recovered\nAGE-SECRET-KEY-1A\n"})
    assert kube.get_age_public_key("old") == "age1recovered"
