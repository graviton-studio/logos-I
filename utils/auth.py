import base64
import os
import datetime
import random
from typing import Optional
from abc import ABC, abstractmethod
from pydantic import BaseModel
from cryptography.fernet import Fernet
from utils.db import supabase
import google.oauth2.credentials
from dotenv import load_dotenv
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

load_dotenv()


import base64
import os
import binascii
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENCRYPTION_KEY_BASE64 = os.getenv("OAUTH_ENCRYPTION_KEY")
if not ENCRYPTION_KEY_BASE64:
    raise ValueError("Missing OAUTH_ENCRYPTION_KEY environment variable")

ENCRYPTION_KEY = base64.b64decode(ENCRYPTION_KEY_BASE64)
if len(ENCRYPTION_KEY) != 32:
    raise ValueError("Encryption key must be exactly 32 bytes after base64 decoding")


def encrypt(plaintext: str) -> str:
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")

    iv = os.urandom(16)  # 16 bytes IV, like in your JS
    cipher = Cipher(algorithms.AES(ENCRYPTION_KEY), modes.GCM(iv))
    encryptor = cipher.encryptor()

    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    auth_tag = encryptor.tag

    # Return in format iv:authTag:ciphertext, all hex encoded
    return f"{binascii.hexlify(iv).decode()}:{binascii.hexlify(auth_tag).decode()}:{binascii.hexlify(ciphertext).decode()}"


def decrypt(encrypted_text: str) -> str:
    parts = encrypted_text.split(":")
    if len(parts) != 3:
        raise ValueError("Invalid encrypted text format")

    iv = binascii.unhexlify(parts[0])
    auth_tag = binascii.unhexlify(parts[1])
    ciphertext = binascii.unhexlify(parts[2])

    cipher = Cipher(algorithms.AES(ENCRYPTION_KEY), modes.GCM(iv, auth_tag))
    decryptor = cipher.decryptor()

    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    plaintext = plaintext.decode("utf-8")
    return plaintext


class OAuthTokenData(BaseModel):
    access_token: str
    refresh_token: Optional[str]
    token_type: str
    expires_at: Optional[datetime.datetime]
    scope: Optional[str]


class BaseOAuthProvider(ABC):
    @abstractmethod
    def refresh_access_token(self, credential: OAuthTokenData) -> OAuthTokenData:
        pass


class GoogleOAuthProvider(BaseOAuthProvider):
    def refresh_access_token(self, credential: OAuthTokenData) -> OAuthTokenData:
        credentials = google.oauth2.credentials.Credentials(
            token=credential.access_token,
            refresh_token=credential.refresh_token,
            token_uri=credential.token_uri,
            client_id=credential.client_id,
            client_secret=credential.client_secret,
        )
        return credentials


PROVIDERS = {
    "gcal": GoogleOAuthProvider(),
    "gmail": GoogleOAuthProvider(),
}


class TokenService:
    @staticmethod
    def get_provider(provider: str) -> BaseOAuthProvider:
        if provider in PROVIDERS:
            return PROVIDERS[provider]

        raise Exception(f"Unsupported provider: {provider}")

    @staticmethod
    def encrypt_token(token: str) -> str:
        return encrypt(token)

    @staticmethod
    def decrypt_token(token: str) -> str:
        return decrypt(token)

    @staticmethod
    def save_credentials(
        user_id: str, provider: str, token_data: OAuthTokenData
    ) -> None:
        # Encrypt sensitive data
        encrypted_access_token = TokenService.encrypt_token(token_data.access_token)
        encrypted_refresh_token = (
            TokenService.encrypt_token(token_data.refresh_token)
            if token_data.refresh_token
            else None
        )

        # Upsert (update if exists, insert if not)
        supabase.table("oauth_credentials").upsert(
            {
                "user_id": user_id,
                "provider": provider,
                "access_token": encrypted_access_token,
                "refresh_token": encrypted_refresh_token,
                "token_type": token_data.token_type,
                "expires_at": (
                    token_data.expires_at.isoformat() if token_data.expires_at else None
                ),
                "scope": token_data.scope,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
            on_conflict=["userId", "provider"],
        ).execute()

    @staticmethod
    def get_credentials(user_id: str, provider: str) -> Optional[OAuthTokenData]:
        result = (
            supabase.table("oauth_credentials")
            .select("*")
            .eq("user_id", user_id)
            .eq("provider", provider)
            .single()
            .execute()
        )
        if not result.data:
            return None

        data = result.data
        print(data)

        return OAuthTokenData(
            access_token=TokenService.decrypt_token(data["access_token"]),
            refresh_token=(
                TokenService.decrypt_token(data["refresh_token"])
                if data["refresh_token"]
                else None
            ),
            token_type=data["token_type"],
            expires_at=(
                datetime.datetime.fromisoformat(data["expires_at"])
                if data.get("expires_at")
                else None
            ),
            scope=data.get("scope"),
        )

    @staticmethod
    def refresh_token_if_needed(user_id: str, provider: str) -> OAuthTokenData:
        credential = TokenService.get_credentials(user_id, provider)
        if credential is None:
            raise Exception(
                f"No credential found for user {user_id} and provider {provider}"
            )

        if credential.expires_at and credential.expires_at > datetime.datetime.now(
            datetime.timezone.utc
        ):
            return credential  # still valid

        provider_client = TokenService.get_provider(provider)
        new_token_data = provider_client.refresh_access_token(credential)

        TokenService.save_credentials(user_id, provider, new_token_data)

        return new_token_data
