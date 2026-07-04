from app.kube import PUBLIC_KEY_ANNOTATION, generate_age_keypair


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
