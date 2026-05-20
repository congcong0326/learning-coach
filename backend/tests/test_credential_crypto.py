import pytest
from cryptography.fernet import Fernet

from backend.app.services.credential_crypto import (
    CredentialEncryptionError,
    decrypt_api_key,
    encrypt_api_key,
    mask_api_key,
)


def test_api_key_round_trip_with_fernet_key() -> None:
    key = Fernet.generate_key().decode()

    ciphertext = encrypt_api_key("sk-test-secret", key)

    assert ciphertext != "sk-test-secret"
    assert decrypt_api_key(ciphertext, key) == "sk-test-secret"


def test_mask_api_key_keeps_prefix_and_suffix_only() -> None:
    assert mask_api_key("sk-abcdefghijklmnopqrstuvwxyz") == "sk-...wxyz"


def test_missing_encryption_key_raises_clear_error() -> None:
    with pytest.raises(
        CredentialEncryptionError,
        match="credential_encryption_key_missing",
    ):
        encrypt_api_key("sk-test-secret", "")
