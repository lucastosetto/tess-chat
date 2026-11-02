import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretDecryptError(Exception):
    pass


class FernetSecretBox:
    def __init__(self, key_material: str) -> None:
        digest = hashlib.sha256(b"tess-secret-box:" + key_material.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def seal(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def open(self, sealed: str) -> str:
        try:
            return self._fernet.decrypt(sealed.encode()).decode()
        except InvalidToken as exc:
            raise SecretDecryptError("stored secret cannot be decrypted") from exc
