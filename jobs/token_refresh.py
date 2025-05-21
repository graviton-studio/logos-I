from utils.auth import OAuthTokenData, TokenService
from utils.db import upsert_oauth_credentials, get_expiring_oauth_credentials


def refresh_oauth_credential(OAuthTokenData: OAuthTokenData):
    token_service = TokenService()
    token_service.refresh_token_if_needed(
        OAuthTokenData.user_id, OAuthTokenData.provider
    )
    upsert_oauth_credentials(
        OAuthTokenData.user_id, OAuthTokenData.provider, OAuthTokenData
    )


def refresh_all_oauth_credentials():
    credentials = get_expiring_oauth_credentials()
    for credential in credentials:
        refresh_oauth_credential(credential)


if __name__ == "__main__":
    refresh_all_oauth_credentials()
