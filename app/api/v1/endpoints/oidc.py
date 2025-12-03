"""
OIDC authentication endpoints.
"""
import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuthError
from sqlmodel import Session, select

from app.core.config import settings
from app.core.database import get_session
from app.core.oidc import oauth, build_pkce
from app.core.security import create_access_token, create_refresh_token
from app.core.logging_config import log_info, log_error, log_user_action, log_warning
from app.schemas.auth import LoginResponse
from app.services.user_service import UserService
from app.models.external_identity import ExternalIdentity

router = APIRouter(prefix="/auth/oidc")


def register_oidc_provider():
    """Register OIDC provider from discovery metadata."""
    if settings.oidc_enabled:
        try:
            client_kwargs = {"scope": settings.oidc_scopes}

            # Disable SSL verification for local development with self-signed certificates
            # SECURITY WARNING: Never disable SSL verification in production!
            if settings.oidc_disable_ssl_verify:
                if settings.environment == "production":
                    raise ValueError(
                        "OIDC_DISABLE_SSL_VERIFY cannot be enabled in production. "
                        "SSL verification must be enabled for security."
                    )

                import ssl
                # Create unverified SSL context for httpx
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                client_kwargs["verify"] = ssl_context
                log_warning(
                    f"OIDC: SSL verification disabled for {settings.oidc_issuer} "
                    "(development only - never use in production!)"
                )

            oauth.register(
                name="journiv_oidc",
                server_metadata_url=f"{settings.oidc_issuer}/.well-known/openid-configuration",
                client_id=settings.oidc_client_id,
                client_secret=settings.oidc_client_secret,
                client_kwargs=client_kwargs,
            )
            log_info(f"OIDC provider registered: {settings.oidc_issuer}")
        except Exception as exc:
            log_error(f"Failed to register OIDC provider: {exc}")
    else:
        log_info("OIDC authentication is disabled")


# Register provider immediately when module is imported
register_oidc_provider()


@router.get(
    "/login",
    responses={
        404: {"description": "OIDC authentication is not enabled"},
    }
)
async def oidc_login(request: Request):
    """
    Initiate OIDC login flow.

    Redirects to the OIDC provider's authorization endpoint with PKCE challenge.
    """
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="OIDC authentication is not enabled")

    # Generate state, nonce, and PKCE challenge
    state = uuid.uuid4().hex
    nonce = uuid.uuid4().hex
    verifier, challenge = build_pkce()

    # Store state, nonce, and verifier in cache with 180 second TTL
    request.app.state.cache.set(
        f"oidc:{state}",
        {"nonce": nonce, "verifier": verifier},
        ex=180
    )

    # Build redirect and authorize
    redirect_uri = settings.oidc_redirect_uri
    log_info(f"Initiating OIDC login with state={state}, redirect_uri={redirect_uri}")

    return await oauth.journiv_oidc.authorize_redirect(
        request,
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=challenge,
        code_challenge_method="S256",
        nonce=nonce,
    )


@router.get(
    "/callback",
    responses={
        400: {"description": "Invalid or expired state parameter, token exchange failed, invalid nonce, or missing OIDC claims"},
        403: {"description": "User provisioning failed"},
        404: {"description": "OIDC authentication is not enabled"},
    }
)
async def oidc_callback(
    request: Request,
    session: Annotated[Session, Depends(get_session)]
):
    """
    OIDC callback endpoint.

    Handles the redirect from the OIDC provider, exchanges the authorization code for tokens,
    validates the ID token, and creates a Journiv session with access and refresh tokens.
    """
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="OIDC authentication is not enabled")

    # Verify state parameter
    state = request.query_params.get("state")
    cached_data = request.app.state.cache.get(f"oidc:{state}") if state else None

    if not state or not cached_data:
        log_error(f"Invalid or expired OIDC state: {state}")
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")

    try:
        # Exchange authorization code for tokens
        token = await oauth.journiv_oidc.authorize_access_token(
            request,
            code_verifier=cached_data["verifier"],
        )
    except OAuthError as exc:
        log_error(f"OIDC token exchange failed: {exc.error}")
        raise HTTPException(status_code=400, detail=f"OIDC authentication failed: {exc.error}")

    # Extract claims from ID token or userinfo
    id_token = token.get("id_token")
    claims = token.get("userinfo") or token.get("id_token_claims") or {}

    # Some providers require an explicit userinfo call
    if not claims:
        try:
            claims = await oauth.journiv_oidc.userinfo(token=token)
        except Exception as exc:
            log_error(f"Failed to fetch OIDC userinfo: {exc}")
            raise HTTPException(status_code=400, detail="Failed to retrieve user information")

    # Verify nonce if present
    if claims.get("nonce") and claims["nonce"] != cached_data["nonce"]:
        log_error(f"OIDC nonce mismatch: expected {cached_data['nonce']}, got {claims.get('nonce')}")
        raise HTTPException(status_code=400, detail="Invalid nonce")

    # Extract user information
    issuer = claims.get("iss") or oauth.journiv_oidc.server_metadata["issuer"]
    subject = claims.get("sub")
    email = claims.get("email")
    name = claims.get("name") or claims.get("preferred_username")
    picture = claims.get("picture")

    if not subject:
        log_error("OIDC claims missing 'sub' field")
        raise HTTPException(status_code=400, detail="Invalid OIDC claims: missing subject")
        
    # Require email to be verified by the IDP before allowing account linking/login
    if email and not claims.get('email_verified', False):
        log_error(f"OIDC login failed: Email {email} not verified by identity provider.", subject=subject)
        raise HTTPException(
            status_code=403, 
            detail="Email not verified by identity provider"
        )
        
    # Normalize email to lowercase for reliable case-insensitive comparison
    if email:
        email = email.lower()

    # Get or create user from external identity
    user_service = UserService(session)

    # Check if this is the first user (bootstrap override)
    is_first = user_service.is_first_user()

    # If not first user, check signup/auto-provision settings
    if not is_first and settings.disable_signup:
        # Check if external identity already exists (User is already OIDC-linked)
        statement = select(ExternalIdentity).where(
            ExternalIdentity.issuer == issuer,
            ExternalIdentity.subject == subject
        )
        external_identity = session.exec(statement).first()

        # Check if a local user (admin-created) exists with the same email.
        # This allows existing users to log in/link SSO even if signup is disabled,
        # ensuring the admin's user management action is respected.
        local_user_by_email = None
        if email:
            local_user_by_email = user_service.get_user_by_email(email)

        # Block login ONLY if neither an external identity nor a local user exists.
        if not external_identity and not local_user_by_email:
            log_warning(
                "OIDC login rejected because signup is disabled",
                issuer=issuer,
                subject=subject,
                user_email=email
            )
            raise HTTPException(status_code=403, detail="Sign up is disabled")

    try:
        # First user always gets provisioned as admin (bootstrap override)
        # Otherwise, respect oidc_auto_provision setting
        # This function handles linking the ExternalIdentity to an existing local user if found.
        user = user_service.get_or_create_user_from_oidc(
            issuer=issuer,
            subject=subject,
            email=email,
            name=name,
            picture=picture,
            auto_provision=is_first or settings.oidc_auto_provision
        )
    except Exception as exc:
        log_error(f"Failed to provision user from OIDC: {exc}")
        raise HTTPException(status_code=403, detail=str(exc))

    # Create Journiv access and refresh tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    # Get user timezone
    timezone = user_service.get_user_timezone(user.id)

    # Build user payload with OIDC flag
    user_payload = {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "is_active": user.is_active,
        "time_zone": timezone,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "is_oidc_user": True  # Flag to indicate this user logged in via OIDC
    }

    # Create one-time login ticket (60 second TTL)
    ticket = uuid.uuid4().hex
    request.app.state.cache.set(
        f"ticket:{ticket}",
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user_payload
        },
        ex=60
    )

    log_user_action(
        user.email,
        "logged in via OIDC",
        request_id=getattr(request.state, 'request_id', None)
    )

    # Redirect to SPA with ticket
    # Use DOMAIN_SCHEME and DOMAIN_NAME from settings instead of request.base_url
    # This ensures correct scheme (https) when running behind reverse proxy
    # Uses path-based routing (no hash) to keep navigation in same browser tab
    if not settings.domain_name:
        # Fallback to request.base_url if domain_name not configured
        base_url = str(request.base_url).rstrip("/")
        finish_url = f"{base_url}/oidc-finish?ticket={ticket}"
    else:
        finish_url = f"{settings.domain_scheme}://{settings.domain_name}/oidc-finish?ticket={ticket}"

    log_info(f"OIDC login successful for {user.email}, redirecting to {finish_url}")

    return RedirectResponse(url=finish_url)


@router.post(
    "/exchange",
    response_model=LoginResponse,
    responses={
        400: {"description": "Invalid request body, missing ticket parameter, or invalid/expired ticket"},
        404: {"description": "OIDC authentication is not enabled"},
    }
)
async def oidc_exchange(request: Request):
    """
    Exchange one-time ticket for access/refresh tokens.

    The SPA calls this endpoint with the ticket received from the callback redirect.
    Tickets are single-use and expire after 60 seconds.
    """
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="OIDC authentication is not enabled")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    ticket = body.get("ticket")

    if not ticket:
        raise HTTPException(status_code=400, detail="Missing ticket parameter")

    # Retrieve ticket data from cache
    ticket_data = request.app.state.cache.get(f"ticket:{ticket}")

    if not ticket_data:
        log_error(f"Invalid or expired OIDC ticket: {ticket}")
        raise HTTPException(status_code=400, detail="Invalid or expired ticket")

    # Delete ticket after first use (one-time use)
    request.app.state.cache.delete(f"ticket:{ticket}")

    return LoginResponse(
        access_token=ticket_data["access_token"],
        refresh_token=ticket_data["refresh_token"],
        token_type="bearer",
        user=ticket_data["user"]
    )


@router.get(
    "/logout",
    responses={
        404: {"description": "OIDC authentication is not enabled"},
        500: {"description": "OIDC logout failed"},
    }
)
async def oidc_logout(request: Request):
    """
    OIDC logout endpoint with Single Sign-Out (SSO).

    Redirects to the OIDC provider's end_session_endpoint to clear the provider's session,
    then redirects back to Journiv's post-logout page.
    """
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="OIDC authentication is not enabled")

    try:
        # Get provider metadata
        metadata = oauth.journiv_oidc.server_metadata
        end_session_endpoint = metadata.get("end_session_endpoint")

        # Build post-logout redirect URI (where provider redirects back after logout)
        # Use DOMAIN_SCHEME and DOMAIN_NAME from settings instead of request.base_url
        # This ensures correct scheme (https) when running behind reverse proxy
        # Uses path-based routing (no hash) to keep navigation in same browser tab
        if not settings.domain_name:
            # Fallback to request.base_url if domain_name not configured
            base_url = str(request.base_url).rstrip("/")
            post_logout_redirect_uri = f"{base_url}/login?logout=success"
        else:
            post_logout_redirect_uri = f"{settings.domain_scheme}://{settings.domain_name}/login?logout=success"

        if end_session_endpoint:
            # Properly encode query parameters for OIDC logout URL
            # Include client_id for proper OIDC logout flow (required by some providers)
            logout_params = urlencode({
                "post_logout_redirect_uri": post_logout_redirect_uri,
                "client_id": settings.oidc_client_id
            })
            logout_url = f"{end_session_endpoint}?{logout_params}"

            log_info(f"Redirecting to OIDC provider logout: {logout_url}")
            return RedirectResponse(url=logout_url)
        else:
            # Provider doesn't support end_session_endpoint, just redirect to login
            log_info("OIDC provider doesn't support end_session_endpoint, performing local logout")
            return RedirectResponse(url=post_logout_redirect_uri)

    except Exception as exc:
        log_error(f"OIDC logout failed: {exc}")
        raise HTTPException(status_code=500, detail="OIDC logout failed")
