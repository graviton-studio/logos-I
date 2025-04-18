import base64
import os
import datetime
from typing import Optional
from abc import ABC, abstractmethod
from pydantic import BaseModel
from cryptography.fernet import Fernet
from utils.db import supabase
import google.oauth2.credentials
from dotenv import load_dotenv

load_dotenv()


def generate_encryption_key(length: int = 32) -> str:
    """Generates a secure random key for development."""
    return base64.urlsafe_b64encode(os.urandom(length)).decode("utf-8")[:length]


OAUTH_ENCRYPTION_KEY = os.getenv("OAUTH_ENCRYPTION_KEY")  # set this in your environment
fernet = Fernet(OAUTH_ENCRYPTION_KEY)


def encrypt(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()


def decrypt(token: str) -> str:
    return fernet.decrypt(token.encode()).decode()


class OAuthTokenData(BaseModel):
    def __init__(
        self,
        access_token: str,
        refresh_token: Optional[str],
        token_type: str,
        expires_at: Optional[datetime.datetime],
        scope: Optional[str],
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_type = token_type
        self.expires_at = expires_at
        self.scope = scope


class BaseOAuthProvider(ABC):
    @abstractmethod
    def refresh_access_token(self, credential: OAuthTokenData) -> OAuthTokenData:
        pass


class GoogleCalendarOAuthProvider(BaseOAuthProvider):
    def refresh_access_token(self, credential: OAuthTokenData) -> OAuthTokenData:
        credentials = google.oauth2.credentials.Credentials(
            token=credential.access_token,
            refresh_token=credential.refresh_token,
            token_uri=credential.token_uri,
            client_id=credential.client_id,
            client_secret=credential.client_secret,
        )
        return credentials


class TokenService:
    @staticmethod
    def get_provider(provider: str) -> BaseOAuthProvider:
        if provider == "gcal":
            return GoogleCalendarOAuthProvider()
        raise Exception(f"Unsupported provider: {provider}")

    @staticmethod
    def encrypt_token(token: str) -> str:
        return encrypt(token)

    @staticmethod
    def decrypt_token(token: str) -> str:
        return decrypt(token)

    @staticmethod
    def save_credential(
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
    def get_credential(user_id: str, provider: str) -> Optional[OAuthTokenData]:
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
        credential = TokenService.get_credential(user_id, provider)
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

        TokenService.save_credential(user_id, provider, new_token_data)

        return new_token_data
