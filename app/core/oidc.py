"""
OIDC client configuration and utilities.

Provides OAuth2/OIDC client setup using Authlib and PKCE helpers.
"""
import os
import base64
import hashlib
import secrets
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

# Initialize Authlib OAuth client
config = Config(environ=os.environ)
oauth = OAuth(config)


def build_pkce() -> tuple[str, str]:
    """
    Build PKCE (Proof Key for Code Exchange) verifier and challenge.

    PKCE adds security for the authorization code flow by ensuring that
    the entity that requested the authorization code is the same entity
    that exchanges it for tokens.

    Returns:
        Tuple of (code_verifier, code_challenge)
    """
    # Generate a cryptographically random verifier (43-128 characters)
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")

    # Create SHA256 challenge from the verifier
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")

    return verifier, challenge
