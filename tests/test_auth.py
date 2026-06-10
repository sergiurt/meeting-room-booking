# tests/test_auth.py
from app.auth import hash_password, verify_password


def test_hash_is_not_plaintext_and_verifies():
    hashed = hash_password("hunter2")
    assert hashed != "hunter2"
    assert verify_password("hunter2", hashed) is True


def test_verify_rejects_wrong_password():
    hashed = hash_password("hunter2")
    assert verify_password("wrong", hashed) is False
