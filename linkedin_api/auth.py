import os
import warnings
from typing import Optional

import dotenv
import requests
import keyring


def get_access_token(
    token_var: str = "LINKEDIN_ACCESS_TOKEN",
    account_var: str = "LINKEDIN_ACCOUNT",
) -> Optional[str]:
    """
    Retrieve the LinkedIn access token.

    Preference order:
    1) System keyring (if available)
    2) Environment variable

    Raises:
        ImportError: If keyring is not installed
    """
    dotenv.load_dotenv()
    token: Optional[str] = None

    try:
        token = keyring.get_password(token_var, os.getenv(account_var))
    except Exception as e:
        warnings.warn(
            f"Failed to retrieve token from keyring: {e}. "
            f"Falling back to environment variable {token_var}. "
            "Consider fixing your keyring setup or use an environment variable.",
            UserWarning,
        )

    if token:
        return token

    return os.getenv(token_var)


def build_linkedin_session(access_token: str, version: str = "202312"):
    """Return a requests.Session preloaded with LinkedIn API headers."""

    if not access_token:
        raise ValueError("Missing LinkedIn access token")

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": version,
        }
    )
    return session
