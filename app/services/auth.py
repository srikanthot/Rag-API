"""Authentication service for RAG API with dual-mode support.

Supports two authentication modes switchable via AUTH_MODE environment variable:
- api_key: Simple API key authentication for POC/development
- managed_identity: Azure Entra ID / Managed Identity for enterprise deployments
"""

import logging
from enum import Enum
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from app.config import get_settings

logger = logging.getLogger(__name__)


class AuthMode(str, Enum):
    """Authentication mode enumeration."""

    API_KEY = "api_key"
    MANAGED_IDENTITY = "managed_identity"


# API Key header scheme
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


def get_auth_mode() -> AuthMode:
    """Get the configured authentication mode.

    Returns:
        AuthMode enum value based on AUTH_MODE environment variable.
    """
    settings = get_settings()
    mode = settings.auth_mode.lower()

    if mode == "managed_identity":
        return AuthMode.MANAGED_IDENTITY
    return AuthMode.API_KEY


async def verify_api_key(
    api_key: Optional[str] = Depends(api_key_header),
) -> str:
    """Verify API key authentication.

    Args:
        api_key: The API key from X-API-KEY header.

    Returns:
        The validated API key.

    Raises:
        HTTPException: If API key is missing or invalid.
    """
    settings = get_settings()

    if not api_key:
        logger.warning("API key authentication failed: missing X-API-KEY header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-KEY header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key != settings.api_key:
        logger.warning("API key authentication failed: invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    logger.debug("API key authentication successful")
    return api_key


async def verify_managed_identity(request: Request) -> dict:
    """Verify Azure Entra ID / Managed Identity authentication.

    This validates the Bearer token from the Authorization header against
    Azure Entra ID. In production, this would validate the JWT token
    and extract claims.

    Args:
        request: The FastAPI request object.

    Returns:
        Dictionary with user claims from the token.

    Raises:
        HTTPException: If token is missing or invalid.
    """
    settings = get_settings()
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        logger.warning("Managed identity auth failed: missing Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not auth_header.startswith("Bearer "):
        logger.warning("Managed identity auth failed: invalid Authorization format")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[7:]  # Remove "Bearer " prefix

    try:
        # In production, validate the JWT token against Azure Entra ID
        # For now, we perform basic validation and return mock claims
        # Real implementation would use azure-identity or msal to validate
        claims = await _validate_entra_token(token, settings)
        logger.debug(f"Managed identity authentication successful for user: {claims.get('sub', 'unknown')}")
        return claims
    except Exception as e:
        logger.warning(f"Managed identity auth failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def _validate_entra_token(token: str, settings) -> dict:
    """Validate Azure Entra ID token.

    In a production environment, this would:
    1. Fetch the JWKS from Azure Entra ID
    2. Validate the token signature
    3. Verify claims (aud, iss, exp, etc.)
    4. Return the validated claims

    Args:
        token: The JWT token to validate.
        settings: Application settings.

    Returns:
        Dictionary with validated claims.

    Raises:
        ValueError: If token validation fails.
    """
    # For POC/development, accept any non-empty token
    # In production, implement full JWT validation
    if not token or len(token) < 10:
        raise ValueError("Token too short or empty")

    # Mock claims for development
    # In production, decode and validate the JWT
    return {
        "sub": "user@example.com",
        "oid": "00000000-0000-0000-0000-000000000000",
        "name": "Authenticated User",
        "roles": [],
    }


async def get_current_user(
    request: Request,
    api_key: Optional[str] = Depends(api_key_header),
) -> dict:
    """Get the current authenticated user based on configured auth mode.

    This is the main authentication dependency to use in protected endpoints.

    Args:
        request: The FastAPI request object.
        api_key: Optional API key from header.

    Returns:
        Dictionary with user information:
        - For API key mode: {"auth_mode": "api_key", "authenticated": True}
        - For managed identity: {"auth_mode": "managed_identity", ...claims}

    Raises:
        HTTPException: If authentication fails.
    """
    auth_mode = get_auth_mode()

    if auth_mode == AuthMode.API_KEY:
        await verify_api_key(api_key)
        return {
            "auth_mode": "api_key",
            "authenticated": True,
        }
    else:
        claims = await verify_managed_identity(request)
        return {
            "auth_mode": "managed_identity",
            "authenticated": True,
            **claims,
        }


def require_auth():
    """Dependency factory for requiring authentication.

    Use this as a dependency in route definitions:
        @router.post("/chat", dependencies=[Depends(require_auth())])

    Returns:
        The get_current_user dependency.
    """
    return Depends(get_current_user)
