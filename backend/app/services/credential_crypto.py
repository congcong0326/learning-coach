from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class CredentialEncryptionError(RuntimeError):
    pass


def _fernet(encryption_key: str) -> Fernet:
    if not encryption_key:
        raise CredentialEncryptionError("credential_encryption_key_missing")
    try:
        return Fernet(encryption_key.encode())
    except (ValueError, TypeError) as exc:
        raise CredentialEncryptionError("credential_encryption_key_invalid") from exc


def encrypt_api_key(api_key: str, encryption_key: str) -> str:
    return _fernet(encryption_key).encrypt(api_key.encode()).decode()


def decrypt_api_key(ciphertext: str, encryption_key: str) -> str:
    try:
        return _fernet(encryption_key).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CredentialEncryptionError("credential_decryption_failed") from exc


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "****"
    prefix = api_key[:3]
    suffix = api_key[-4:]
    return f"{prefix}...{suffix}"
