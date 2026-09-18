"""Password hashing + opaque token primitives. Pure functions, no domain."""

from neurolegal.core.security import generate_token, hash_password, hash_token, verify_password


def test_verify_accepts_correct_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)


def test_verify_rejects_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert not verify_password("wrong password", hashed)


def test_verify_rejects_garbage_hash() -> None:
    # A corrupted / non-argon2 DB value must fail closed, not raise.
    assert not verify_password("anything", "not-a-real-hash")


def test_hash_password_is_salted() -> None:
    assert hash_password("same input") != hash_password("same input")


def test_hash_password_uses_argon2id() -> None:
    assert hash_password("x").startswith("$argon2id$")


def test_generate_token_is_unique_and_urlsafe() -> None:
    tokens = {generate_token() for _ in range(50)}
    assert len(tokens) == 50
    for token in tokens:
        # URL-safe: goes into query strings of verify/reset links as-is.
        assert token == token.strip()
        assert all(c.isalnum() or c in "-_" for c in token)
        assert len(token) >= 32


def test_hash_token_is_deterministic_sha256_hex() -> None:
    token = generate_token()
    first, second = hash_token(token), hash_token(token)
    assert first == second
    assert len(first) == 64
    assert first != token
    assert hash_token("other") != first
